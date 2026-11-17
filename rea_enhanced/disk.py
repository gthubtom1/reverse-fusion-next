"""Owned scratch lifecycle. Never adopt arbitrary folders as disposable data.

Project metadata is authoritative; per-volume reservations coordinate independent
CLI/MCP processes. OS locks protect running work, including against PID reuse.
No model-written acceptance or reference evidence is deleted by this module.
"""
from contextlib import contextmanager
from hashlib import sha256
import os
from pathlib import Path
import shutil
import threading
import time
import uuid

from .storage import inside, locked, read, write

MiB = 1024 ** 2
GiB = 1024 ** 3
DEFAULTS = {'max_temporary_bytes': 4 * GiB, 'minimum_free_bytes': 2 * GiB,
            'minimum_free_fraction': .02, 'completed_ttl_seconds': 3600,
            'interrupted_ttl_seconds': 86400}
MARKER = '.rf-owned.json'


def coordinator():
    return Path(os.environ.get('RF_NEXT_DISK_STATE',
        str(Path.home() / '.codex/state/reverse-fusion-disk'))).resolve()


def no_links(path, root):
    """Check every ancestor too: resolve() alone hides a junction within root."""
    root = root.resolve()
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        raise ValueError('Disk path leaves its owned root')
    for item in [root, *reversed(list(path.parents)[:len(path.relative_to(root).parts)]), path]:
        if item.exists() or item.is_symlink():
            st = item.lstat()
            if item.is_symlink() or getattr(st, 'st_file_attributes', 0) & 1024:
                raise ValueError('Links and reparse points are retained')
    return path


def size(path, live=False):
    """Bounded, no-link scan. An incomplete scan is never used to delete data."""
    total, count = 0, 0
    if not path.exists():
        return 0
    no_links(path, path.parent)
    def scan_error(exc):
        if live and isinstance(exc, FileNotFoundError):
            return
        raise exc
    for base, dirs, files in os.walk(path, followlinks=False, onerror=scan_error):
        for name in [*dirs, *files]:
            try:
                item = no_links(Path(base) / name, path)
                if name == '.git':
                    raise ValueError('Git data is retained')
                count += 1
                if count > 100000:
                    raise ValueError('Scratch inventory exceeded 100000 entries; inspect manually')
                if item.is_file():
                    total += item.stat().st_size
            except FileNotFoundError:
                if not live:
                    raise
    return total


def _path(project):
    no_links(project / '.rea-enhanced', project)
    return project / '.rea-enhanced/disk.json'


def _load(project):
    path = _path(project)
    value = read(path) if path.exists() else {'schema_version': 1, 'project_root': str(project),
        'policy': dict(DEFAULTS), 'entries': {}, 'protected': [], 'reclaimed_bytes': 0, 'recent': []}
    if value.get('schema_version') != 1 or value.get('project_root') != str(project):
        raise ValueError('Disk registry identity changed; preserve and inspect it')
    return value


def _save(project, value):
    write(_path(project), value)


def _volume(project):
    return str(project.stat().st_dev) + ':' + project.anchor.casefold()


def _global_path(project):
    return coordinator() / ('volume-' + sha256(_volume(project).encode()).hexdigest()[:24] + '.json')


def _global(project):
    path = _global_path(project)
    return read(path) if path.exists() else {'volume': _volume(project), 'projects': [], 'reservations': {}}


def _lease_path(token):
    return coordinator() / 'leases' / token


def _retire_lease(token):
    # Unique IDs are never reused. Called only after retiring the owned registry
    # entry/reservation, when no future operation may acquire this lease.
    try:
        _lease_path(token).with_suffix('.lock').unlink(missing_ok=True)
    except OSError:
        pass


def _busy(token):
    try:
        with locked(_lease_path(token), timeout=0):
            return False
    except ValueError:
        return True


def _prune(value):
    for token, entry in list(value['reservations'].items()):
        if entry['mode'] == 'managed':
            if not _busy(token):
                del value['reservations'][token]
        else:
            try:
                project = Path(entry['project'])
                if not project.exists():
                    del value['reservations'][token]
                    continue
                saved = _load(project)['entries'][token]
                if saved['state'] != 'active':
                    del value['reservations'][token]
            except (OSError, ValueError, KeyError):
                # Ambiguous manual work keeps its reservation, not a guessed PID.
                pass


def _reserve(project, token, amount, mode, policy):
    path = _global_path(project)
    with locked(path):
        value = _global(project)
        _prune(value)
        usage = shutil.disk_usage(project)
        reserve = max(policy['minimum_free_bytes'], int(usage.total * policy['minimum_free_fraction']))
        other = sum(e['bytes'] for e in value['reservations'].values())
        if usage.free - other - amount < reserve:
            raise ValueError('Insufficient unreserved disk space; temporary work paused before copying or execution')
        value['projects'] = sorted(set([p for p in value['projects'] if Path(p).is_dir()] + [str(project)]))
        value['reservations'][token] = {'project': str(project), 'bytes': amount, 'mode': mode}
        write(path, value)


def _release(project, token):
    path = _global_path(project)
    with locked(path):
        value = _global(project)
        value['reservations'].pop(token, None)
        write(path, value)


@contextmanager
def reserved_space(project, amount):
    """For an independently owned temporary installer checkout; does not delete it."""
    project = project.resolve()
    if type(amount) is not int or amount <= 0:
        raise ValueError('Declare positive installation capacity')
    token = uuid.uuid4().hex
    with locked(_lease_path(token)):
        _reserve(project, token, amount, 'managed', _load(project)['policy'])
        try:
            yield
        finally:
            _release(project, token)
    _retire_lease(token)


def protected_paths(project, value):
    names = list(value['protected'])
    verified = {}
    def references(obj):
        if isinstance(obj, dict):
            frozen = False
            if obj.get('retention') == 'snapshot' and obj.get('source_path'):
                key = (obj.get('path'), obj.get('sha256'))
                if key not in verified:
                    try:
                        from .storage import digest
                        verified[key] = digest(inside(project, key[0])) == key[1]
                    except (OSError, ValueError, TypeError):
                        verified[key] = False
                frozen = verified[key]
            for key, item in obj.items():
                # Events are an audit trail, not active file dependencies. A
                # verified immutable snapshot replaces its disposable origin;
                # retain that origin when the snapshot is missing or corrupt.
                if key == 'events' or key == 'source_path' and frozen:
                    continue
                yield key
                yield from references(item)
        elif isinstance(obj, list):
            for item in obj:
                yield from references(item)
        elif isinstance(obj, str):
            yield obj
    index_path = project / '.rea-enhanced/cases.json'
    if index_path.exists():
        index = read(index_path)
        for case_root in index['case_roots']:
            case_path = inside(project, case_root + '/case-v2.json')
            names.append(case_root)
            case = read(case_path)
            names.extend(references(case))
            for check in case.get('checks', {}).values():
                if check.get('path'):
                    receipt = inside(project, check['path'])
                    if receipt.exists():
                        names.extend(references(read(receipt)))
    result = set()
    for name in names:
        try:
            result.add(inside(project, name))
        except (ValueError, TypeError):
            continue
    return result


def protect(project, names):
    project = project.resolve()
    for name in names:
        inside(project, name)
    with locked(_path(project)):
        value = _load(project)
        value['protected'] = sorted(set(value['protected']) | set(names))
        _save(project, value)


def _owned(project, token, entry):
    if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Invalid scratch identity')
    expected = '.rea-enhanced/scratch/' + token
    if entry['path'] != expected:
        raise ValueError('Scratch registry path changed')
    area = no_links(project / expected, project)
    if not area.exists():
        return area
    marker = no_links(area / MARKER, project)
    if read(marker) != {'owner': 'reverse-fusion-next', 'token': token, 'project_root': str(project)}:
        raise ValueError('Scratch ownership marker changed; retaining files')
    return area


def _remove(area, project):
    """Only prevalidated, marker-owned scratch, with a fresh check on each entry."""
    size(area)  # refuse entire tree on a link/error before the first mutation
    for base, dirs, files in os.walk(area, topdown=False, followlinks=False):
        for name in files:
            if Path(base) == area and name == MARKER:
                continue
            no_links(Path(base) / name, project).unlink()
        for name in dirs:
            no_links(Path(base) / name, project).rmdir()
    no_links(area / MARKER, project).unlink()
    no_links(area, project).rmdir()


def maintain(project, apply=True, force_completed=False, force_ids=()):
    project = project.resolve()
    if not _path(project).exists():
        return {'status': 'unmanaged', 'reclaimed_bytes': 0, 'entries': []}
    released = []
    with locked(_path(project)):
        value = _load(project)
        protections = protected_paths(project, value)
        now = time.time()
        rows, reclaimed = [], 0
        for token, entry in list(value['entries'].items()):
            row = {'id': token, 'path': entry['path'], 'purpose': entry['purpose'], 'bytes': 0}
            try:
                area = _owned(project, token, entry)
                busy = _busy(token) or entry['state'] == 'active' and entry['mode'] == 'manual'
                row['bytes'] = size(area, live=busy)
                if any(p.is_relative_to(area) or area.is_relative_to(p) for p in protections):
                    row['state'] = 'protected'
                elif busy:
                    row['state'] = 'active'
                else:
                    interrupted = entry['state'] == 'active'
                    ttl = value['policy']['interrupted_ttl_seconds' if interrupted else 'completed_ttl_seconds']
                    expired = now - entry.get('completed_at', entry['created_at']) >= ttl
                    row['state'] = ('reclaimable' if expired or (force_completed or token in force_ids) and not interrupted
                                    else 'interrupted-retained' if interrupted else 'retained')
                    if apply and row['state'] == 'reclaimable':
                        if area.exists():
                            _remove(area, project)
                        row['state'] = 'reclaimed'
                        reclaimed += row['bytes']
                        del value['entries'][token]
                        released.append(token)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                row.update(state='retained-error', reason=str(exc))
            rows.append(row)
        if apply:
            value['reclaimed_bytes'] += reclaimed
            value['last_maintenance_at'] = now
            value['last_inventory'] = {state: sum(r['bytes'] for r in rows if r['state'] == state)
                for state in {r['state'] for r in rows}}
            value['recent'] = (value['recent'] + [r for r in rows if r['state'] == 'reclaimed'])[-20:]
            _save(project, value)
        usage = shutil.disk_usage(project)
        result = {'status': 'ok', 'project_root': str(project), 'policy': value['policy'],
            'free_bytes': usage.free, 'reclaimed_bytes': reclaimed, 'total_reclaimed_bytes': value['reclaimed_bytes'],
            'managed_temporary_bytes': sum(r['bytes'] for r in rows if r['state'] != 'reclaimed'),
            'entries': rows, 'scope': 'Registered scratch only. Evidence, products and unregistered folders are retained.'}
    for token in released:
        _release(project, token)
        _retire_lease(token)
    return result


def allocate(project, purpose, rebuild, reserve_bytes=256 * MiB, mode='manual', token=None):
    project = project.resolve()
    if (not isinstance(purpose, str) or not purpose.strip() or not isinstance(rebuild, str) or not rebuild.strip()
            or type(reserve_bytes) is not int or reserve_bytes <= 0):
        raise ValueError('Temporary work requires a purpose, reconstruction instructions and a positive byte budget')
    maintain(project, apply=True)
    token = token or uuid.uuid4().hex
    with locked(_path(project)):
        value = _load(project)
        if len(value['entries']) >= 256:
            raise ValueError('256 temporary areas already registered; inspect retained or active work before allocating more')
        occupied = 0
        for old_token, entry in value['entries'].items():
            area = _owned(project, old_token, entry)
            occupied += max(size(area, live=entry['state'] == 'active'),
                            entry['reserve_bytes'] if entry['state'] == 'active' else 0)
        if occupied + reserve_bytes > value['policy']['max_temporary_bytes']:
            raise ValueError('Project temporary budget reached; inspect retained or active scratch before more work')
        if mode == 'manual':
            _reserve(project, token, reserve_bytes, mode, value['policy'])
        area = project / '.rea-enhanced/scratch' / token
        no_links(area, project)
        try:
            area.mkdir(parents=True)
            write(area / MARKER, {'owner': 'reverse-fusion-next', 'token': token, 'project_root': str(project)})
            value['entries'][token] = {'path': area.relative_to(project).as_posix(), 'purpose': purpose,
                'rebuild': rebuild, 'reserve_bytes': reserve_bytes, 'mode': mode, 'state': 'active', 'created_at': time.time()}
            _save(project, value)
        except BaseException:
            if mode == 'manual':
                _release(project, token)
            raise
    return {'id': token, 'path': str(area), 'relative_path': area.relative_to(project).as_posix(),
            'reserve_bytes': reserve_bytes, 'state': 'active'}


def complete(project, token, cleanup=True):
    project = project.resolve()
    with locked(_path(project)):
        value = _load(project)
        if token not in value['entries']:
            raise ValueError('Unknown scratch identity')
        _owned(project, token, value['entries'][token])
        if _busy(token):
            raise ValueError('Scratch has a running operation lease; retain until it finishes')
        value['entries'][token].update(state='completed', completed_at=time.time())
        _save(project, value)
    _release(project, token)
    return maintain(project, apply=True, force_ids={token} if cleanup else ())


@contextmanager
def workspace(project, purpose, rebuild, reserve_bytes, cancel_event=None):
    """Own one operation lifetime. Scratch limits are monitored, not OS quotas."""
    project = project.resolve()
    token = uuid.uuid4().hex
    allocated = None
    stopped, cancelled = threading.Event(), threading.Event()
    failure = []
    cleanup = {}
    try:
        with locked(_lease_path(token)):
            allocated = allocate(project, purpose, rebuild, reserve_bytes, mode='managed', token=token)
            area = Path(allocated['path'])
            policy = _load(project)['policy']
            _reserve(project, token, reserve_bytes, 'managed', policy)
            def watch():
                while not stopped.wait(.5):
                    if cancel_event and cancel_event.is_set():
                        cancelled.set()
                    try:
                        usage = shutil.disk_usage(project)
                        floor = max(policy['minimum_free_bytes'], int(usage.total * policy['minimum_free_fraction']))
                        if size(area, live=True) > reserve_bytes or usage.free < floor:
                            failure.append('Temporary byte budget or free-space reserve reached')
                            cancelled.set()
                            break
                    except (OSError, ValueError) as exc:
                        failure.append(str(exc)); cancelled.set(); break
            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()
            if cancel_event and cancel_event.is_set():
                cancelled.set()
            try:
                yield {'path': area, 'cancel_event': cancelled, 'failure': failure, 'cleanup': cleanup}
            finally:
                stopped.set(); watcher.join(timeout=2)
                try:
                    if size(area) > reserve_bytes and not failure:
                        failure.append('Temporary byte budget reached at operation completion')
                except (OSError, ValueError) as exc:
                    failure.append(str(exc))
    finally:
        if allocated is not None:
            cleanup.update(complete(project, token))


def policy(project, changes):
    if not isinstance(changes, dict) or not changes or set(changes) - set(DEFAULTS):
        raise ValueError('Unknown or empty disk policy')
    for key, value in changes.items():
        if key == 'minimum_free_fraction':
            if type(value) not in (int, float) or not 0 <= value <= .5:
                raise ValueError('Free-space fraction must be between zero and .5')
        elif type(value) is not int or value < (1 if key == 'max_temporary_bytes' else 0):
            raise ValueError('Disk byte limits and retention seconds must be nonnegative integers')
    project = project.resolve()
    with locked(_path(project)):
        value = _load(project); value['policy'].update(changes); _save(project, value)
    return maintain(project, apply=False)


def dispatch(project, action='status', **args):
    if action == 'status':
        return maintain(project, apply=False)
    if action == 'sweep':
        return maintain(project, apply=True)
    if action == 'allocate':
        return allocate(project, args.get('purpose'), args.get('rebuild'), args.get('reserve_bytes', 256 * MiB))
    if action == 'complete':
        return complete(project, args.get('id'))
    if action == 'policy':
        return policy(project, args.get('policy'))
    if action == 'protect':
        names = args.get('paths')
        if not isinstance(names, list) or not names or any(not isinstance(p, str) for p in names):
            raise ValueError('Declare protected project-relative paths')
        protect(project, names)
        return maintain(project, apply=False)
    raise ValueError('Unknown storage action')


def summary(project):
    project = project.resolve()
    try:
        value = _load(project)
        return {'policy': value['policy'], 'registered_areas': len(value['entries']),
            'total_reclaimed_bytes': value['reclaimed_bytes'], 'free_bytes': shutil.disk_usage(project).free,
            'last_inventory': value.get('last_inventory'), 'measured_at': value.get('last_maintenance_at'),
            'details_tool': 'rf_next_storage'}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'retained-error', 'reason': str(exc), 'details_tool': 'rf_next_storage'}


def maintenance_loop(stop, interval=60, guard=None):
    """Connection-owned periodic maintenance; no scheduled task or hidden daemon."""
    while not stop.wait(interval):
        if guard is not None and not guard():
            return
        projects = set()
        for path in coordinator().glob('volume-*.json'):
            try:
                projects.update(read(path)['projects'])
            except (OSError, ValueError, KeyError):
                continue
        for name in sorted(projects):
            if stop.is_set():
                return
            try:
                maintain(Path(name))
            except (OSError, ValueError, KeyError, TypeError):
                # Detailed failures remain visible in an explicit project report.
                continue
