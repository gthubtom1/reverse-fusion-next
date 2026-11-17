"""Explicit relocation of a copied outcome project; never rewrite its source."""
from contextlib import ExitStack
from pathlib import Path, PureWindowsPath
import json
import time
import uuid

from reverse_fusion.file_updates import file_transaction
from .storage import digest, inside, locked, read, write
from . import disk


def relocate(project, from_root, reason, inactive=False):
    project = project.resolve()
    if (not project.is_dir() or not isinstance(from_root, str)
            or not (Path(from_root).is_absolute() or PureWindowsPath(from_root).is_absolute())
            or not isinstance(reason, str) or not reason.strip() or inactive is not True):
        raise ValueError('Relocation needs an existing project, explicit old absolute root, reason and inactive=true after all users stop')
    if str(project) == from_root:
        raise ValueError('Select the copied project, not its original location')
    index_path = project/'.rea-enhanced/cases.json'
    disk_path = project/'.rea-enhanced/disk.json'
    disk.no_links(project/'.rea-enhanced', project)
    with ExitStack() as locks:
        locks.enter_context(locked(index_path))
        locks.enter_context(locked(disk_path))
        index = read(index_path) if index_path.exists() else {'case_roots': []}
        cases = {}
        for name in index['case_roots']:
            path = inside(project, name+'/case-v2.json')
            disk.no_links(path, project)
            locks.enter_context(locked(inside(project, name+'/operation-run'), timeout=0))
            locks.enter_context(locked(path))
            case = read(path)
            if (case.get('schema_version') != 2 or case.get('project_root') != from_root
                    or case.get('case_root') != name):
                raise ValueError('Copied case identity does not match the explicit old root')
            for check_id, check in case.get('checks', {}).items():
                locks.enter_context(locked(inside(project, name+'/checks/'+check_id+'.json'), timeout=0))
                if check.get('path') and digest(inside(project, check['path'])) != check['sha256']:
                    raise ValueError('Copied comparison receipt changed')
            for evidence in case['evidence'].values():
                if digest(inside(project, evidence['path'])) != evidence['sha256']:
                    raise ValueError('Copied evidence is missing or changed')
            for operation in case.get('operations', {}).values():
                if digest(inside(project, operation['receipt'])) != operation['sha256']:
                    raise ValueError('Copied operation receipt changed')
            for key in ('candidate_files', 'reference_files'):
                for file, checksum in case.get('product', {}).get(key, {}).items():
                    if digest(inside(project, file)) != checksum:
                        raise ValueError('Copied product identity changed')
            cases[path] = case
        registry = read(disk_path) if disk_path.exists() else None
        markers = {}
        if registry:
            if registry.get('schema_version') != 1 or registry.get('project_root') != from_root:
                raise ValueError('Copied disk identity does not match the explicit old root')
            if any(disk._busy(token) for token in registry.get('uses', {})):
                raise ValueError('An operation still holds a project path lease')
            for token, entry in registry['entries'].items():
                if disk._busy(token):
                    raise ValueError('A storage operation still holds its lease')
                area = disk.no_links(project/entry['path'], project)
                tier = entry.get('tier', 'disposable')
                if (len(token) != 32 or any(c not in '0123456789abcdef' for c in token)
                        or tier not in disk.TIERS or entry['path'] != '.rea-enhanced/'+disk.TIERS[tier]+'/'+token
                        or entry.get('state') not in {'active', 'completed'}
                        or entry.get('mode') not in {'manual', 'managed'}
                        or type(entry.get('reserve_bytes')) is not int or entry['reserve_bytes'] <= 0):
                    raise ValueError('Copied storage identity changed')
                disk.size(area)
                marker = disk.no_links(area/disk.MARKER, project)
                if read(marker) != {'owner': 'reverse-fusion-next', 'token': token, 'project_root': from_root}:
                    raise ValueError('Copied storage marker changed')
                markers[marker] = {'owner': 'reverse-fusion-next', 'token': token, 'project_root': str(project)}
        if not cases and registry is None:
            raise ValueError('No managed project state to relocate')
        receipt = project/'.rea-enhanced/relocations'/(uuid.uuid4().hex+'.json')
        # Preserve the compact on-disk case and its existing sidecar references.
        # Expanding large supplements/events here duplicates them into one bounded receipt.
        backups = {p.relative_to(project).as_posix(): json.loads(p.read_text(encoding='utf-8-sig')) for p in cases}
        if registry:
            backups[str(disk_path.relative_to(project))] = copy.deepcopy(registry)
        backups.update({str(p.relative_to(project)): read(p) for p in markers})
        write(receipt, {'status': 'prepared', 'from_root': from_root, 'project_root': str(project),
                        'reason': reason, 'originals': backups})
        global_path = disk._global_path(project)
        locks.enter_context(locked(global_path))
        with file_transaction([*cases, *markers, disk_path, global_path, receipt]):
            for path, case in cases.items():
                case['project_root'] = str(project)
                case['checks'] = {key: {'status': 'interrupted', 'reason': 'Project relocated; compare again'}
                                  for key in case['checks']}
                for key in ('coverage', 'delivery', 'stage_delivery', 'reviewed_delivery', 'analysis_report', 'operations'):
                    case.pop(key, None)
                for assessment in case.get('assessments', {}).values():
                    assessment['invalidated'] = 'Project relocated; review observations and new environment before reassessment'
                from .workflow import _event
                _event(case, 'relocate', {'from_root': from_root, 'reason': reason,
                                         'originals': receipt.relative_to(project).as_posix()})
                write(path, case)
            for path, marker in markers.items():
                write(path, marker)
            if registry:
                registry.update(project_root=str(project), uses={})
                for entry in registry['entries'].values():
                    entry.update(state='completed', mode='manual', completed_at=time.time())
                    if entry.get('tier') == 'reusable':
                        entry['reuse_invalid'] = 'Project relocated; rebuild against the new environment'
                write(disk_path, registry)
            coordinator = disk._global(project)
            coordinator['projects'] = sorted(set(coordinator['projects']) | {str(project)})
            write(global_path, coordinator)
            saved = read(receipt)
            saved['status'] = 'relocated'
            write(receipt, saved)
        return {'status': 'relocated', 'cases': len(cases), 'receipt': str(receipt),
                'checks': 'invalidated; recheck runtime and compare',
                'source': 'untouched; only the selected copy was rebound'}
