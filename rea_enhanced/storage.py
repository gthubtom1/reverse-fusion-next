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


MAX_RECORD_BYTES = 16 * 1024 * 1024


def _encoded(value):
    data = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError('Record exceeds 16 MiB; save large material as separate evidence')
    return data


def read(path: Path) -> dict:
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise ValueError('Record exceeds 16 MiB')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    if path.name == 'case-v2.json' and value.get('schema_version') == 2:
        def expand(item):
            if isinstance(item, dict):
                if set(item) == {'$rf_record', 'sha256', 'kind'}:
                    name = item['$rf_record']
                    if not isinstance(name, str) or not name.startswith('case-records/'):
                        raise ValueError('Invalid case record reference')
                    target = inside(path.parent, name)
                    if target.stat().st_size > 64 * 1024 * 1024:
                        raise ValueError('Case record exceeds 64 MiB')
                    data = target.read_bytes()
                    if sha256(data).hexdigest() != item['sha256']:
                        raise ValueError('Case record reference changed')
                    if item['kind'] == 'text':
                        return data.decode('utf-8')
                    if item['kind'] != 'event' or len(data) > MAX_RECORD_BYTES:
                        raise ValueError('Invalid case record kind or size')
                    return expand(json.loads(data))
                return {key: expand(child) for key, child in item.items()}
            if isinstance(item, list):
                return [expand(child) for child in item]
            return item
        value = expand(value)
    return value


def write(path: Path, value: dict) -> None:
    pending = {}
    if path.name == 'case-v2.json' and value.get('schema_version') == 2:
        def reference(data, kind):
            if len(data) > 64 * 1024 * 1024:
                raise ValueError('Case material exceeds 64 MiB; save it as explicit evidence')
            checksum = sha256(data).hexdigest()
            name = 'case-records/' + checksum + ('.txt' if kind == 'text' else '.json')
            pending[name] = data
            return {'$rf_record': name, 'sha256': checksum, 'kind': kind}
        def compact(item):
            if isinstance(item, str) and len(item.encode('utf-8')) > 65536:
                return reference(item.encode('utf-8'), 'text')
            if isinstance(item, dict):
                return {key: compact(child) for key, child in item.items()}
            if isinstance(item, list):
                return [compact(child) for child in item]
            return item
        value = {key: ([reference(_encoded(compact(e)), 'event') for e in child]
                       if key == 'events' else compact(child)) for key, child in value.items()}
    # Preflight the entire main record before touching the previous readable state.
    data = _encoded(value)
    for name, payload in pending.items():
        target = inside(path.parent, name)
        if target.exists():
            if target.read_bytes() != payload:
                raise ValueError('Stored case record changed; preserve and investigate it')
        else:
            atomic_write(target, payload)
    atomic_write(path, data)


@contextmanager
def locked(path: Path, timeout=5):
    lock = path.with_suffix('.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a+b') as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b'\0'); stream.flush()
        until = time.monotonic() + timeout
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
