"""Project-bound records and atomic, OS-locked updates."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from reverse_fusion.file_updates import atomic_write


def inside(root: Path, name: str) -> Path:
    root = root.resolve()
    if (not isinstance(name, str) or not name or ':' in name or '\\' in name
            or name.startswith('/') or any(p in {'', '.', '..'} for p in name.split('/'))):
        raise ValueError('Expected a portable project-relative path')
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path leaves the selected project')
    return path


def digest(path: Path) -> str:
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path: Path) -> dict:
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Record exceeds 16 MiB')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def write(path: Path, value: dict) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('ascii'))


@contextmanager
def locked(path: Path):
    lock = path.with_suffix('.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a+b') as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b'\0'); stream.flush()
        until = time.monotonic() + 5
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= until:
                    raise ValueError('Record is being updated; retry after the writer finishes')
                time.sleep(.02)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
