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
MAX_TEXT_BYTES = 64 * 1024 * 1024
CASE_NAME = 'case-v2.json'  # Keep the discovery path; schema_version selects the format.
CASE_SCHEMAS = (2, 3)
REFERENCE_KEYS = {'$rf_record', 'sha256', 'kind'}


def _encoded(value):
    data = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode('ascii')
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError('Record exceeds 16 MiB; save large material as separate evidence')
    return data


def _read_object(path: Path):
    with path.open('rb') as stream:
        data = stream.read(MAX_RECORD_BYTES + 1)
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError('Record exceeds 16 MiB')
    value = json.loads(data.decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value, data


def read_snapshot(path: Path):
    """Parse a plan or receipt and hash those same bytes."""
    value, data = _read_object(path)
    return value, sha256(data).hexdigest()


def _preview_compact(value):
    # The preview put a reference in every event, including the open event.
    events = value.get('events')
    return (value.get('schema_version') == 2 and isinstance(events, list)
            and any(isinstance(e, dict) and '$rf_record' in e for e in events))


def read(path: Path, *, writable=False) -> dict:
    value, _ = _read_object(path)
    if path.name != CASE_NAME:
        return value
    preview = _preview_compact(value)
    if preview and writable:
        raise ValueError('Preview ledger is read-only; export-case --format compact-v3 before resuming writes')
    if not preview and value.get('schema_version') != 3:
        return value

    def expand(item):
        if isinstance(item, dict):
            if item.keys() == REFERENCE_KEYS:
                kind, checksum = item['kind'], item['sha256']
                extensions = {'text': '.txt', 'event': '.json'}
                if not preview:
                    extensions['literal'] = '.literal.json'
                if (not isinstance(checksum, str) or len(checksum) != 64
                        or any(c not in '0123456789abcdef' for c in checksum)
                        or not isinstance(kind, str) or kind not in extensions):
                    raise ValueError('Invalid case record reference')
                name = 'case-records/' + checksum + extensions[kind]
                if item['$rf_record'] != name:
                    raise ValueError('Invalid case record path')
                limit = MAX_TEXT_BYTES if kind == 'text' else MAX_RECORD_BYTES
                with inside(path.parent, name).open('rb') as stream:
                    data = stream.read(limit + 1)
                if len(data) > limit or sha256(data).hexdigest() != checksum:
                    raise ValueError('Case record reference changed or exceeds its size limit')
                if kind == 'text':
                    return data.decode('utf-8')
                child = json.loads(data)
                return child if kind == 'literal' else expand(child)
            return {key: expand(child) for key, child in item.items()}
        if isinstance(item, list):
            return [expand(child) for child in item]
        return item

    expanded = expand(value)
    events = expanded.get('events')
    if not isinstance(events, list) or any(not isinstance(e, dict) or not isinstance(e.get('operation'), str) for e in events):
        raise ValueError('Compact ledger contains an unreadable event')
    return expanded


def _compact_case(value):
    pending = {}

    def reference(data, kind, extension):
        checksum = sha256(data).hexdigest()
        name = 'case-records/' + checksum + extension
        pending[name] = data
        return {'$rf_record': name, 'sha256': checksum, 'kind': kind}

    def compact(item):
        if isinstance(item, str):
            data = item.encode('utf-8')
            if len(data) > MAX_TEXT_BYTES:
                raise ValueError('Case material exceeds 64 MiB; save it as explicit evidence')
            if len(data) > 65536:
                return reference(data, 'text', '.txt')
        if isinstance(item, dict):
            if item.keys() == REFERENCE_KEYS:
                return reference(_encoded(item), 'literal', '.literal.json')
            return {key: compact(child) for key, child in item.items()}
        if isinstance(item, list):
            return [compact(child) for child in item]
        return item

    compacted = {key: ([reference(_encoded(compact(e)), 'event', '.json') for e in child]
                       if key == 'events' else compact(child)) for key, child in value.items()}
    return _encoded(compacted), pending


def _write_case_parts(path, data, pending):
    for name, payload in pending.items():
        target = inside(path.parent, name)
        if target.exists():
            if digest(target) != sha256(payload).hexdigest():
                raise ValueError('Stored case record changed; preserve and investigate it')
        else:
            atomic_write(target, payload)
    atomic_write(path, data)


def write(path: Path, value: dict) -> None:
    if path.name == CASE_NAME and value.get('schema_version') == 3:
        _write_case_parts(path, *_compact_case(value))
    else:
        atomic_write(path, _encoded(value))


def export_case(project, case_root, output, *, schema_version):
    """Prepare a format conversion without changing the source case or evidence."""
    project = project.resolve()
    value = read(inside(project, case_root + '/' + CASE_NAME))
    if (value.get('schema_version') not in CASE_SCHEMAS or value.get('case_root') != case_root
            or Path(value.get('project_root', '')).resolve() != project):
        raise ValueError('Select the original project and its case to export the ledger')
    converted = {**value, 'schema_version': schema_version}
    if schema_version == 2:
        data, pending = _encoded(converted), {}
    elif schema_version == 3:
        data, pending = _compact_case(converted)
    else:
        raise ValueError('Select inline-v2 or compact-v3')
    destination = inside(project, output)
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / CASE_NAME
    _write_case_parts(path, data, pending)
    return {'status': 'exported', 'schema_version': schema_version, 'path': str(path),
            'sha256': sha256(data).hexdigest(), 'sidecars': len(pending),
            'scope': 'Ledger copy only; original project, external evidence and installation are unchanged'}


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
