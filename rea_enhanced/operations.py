"""Optional measured host commands; successful execution is never acceptance."""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time

from reverse_fusion.owned_process import run_owned
from .comparison import launch_environment
from .storage import digest, inside, locked, read, write


def identifier(value):
    if (not isinstance(value, str) or not value or len(value) > 80
            or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in value)):
        raise ValueError('Use a portable operation identifier')
    return value


def file_identities(project, names):
    if (not isinstance(names, list) or len(names) > 500
            or any(not isinstance(n, str) for n in names) or len(set(names)) != len(names)):
        raise ValueError('Declare at most 500 distinct project-relative files')
    values = {}
    for name in names:
        path = inside(project, name)
        if not path.is_file():
            raise ValueError('Declared file is missing: ' + name)
        values[name] = digest(path)
    return values


def frozen_evidence(project, case_root, name):
    """Freeze a bounded observation, retaining the original working path separately."""
    source = inside(project, name)
    if not source.is_file() or source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Snapshot needs a file up to 64 MiB; use explicit live retention for a large dependency')
    data = source.read_bytes()
    if len(data) > 64 * 1024 * 1024:
        raise ValueError('Evidence grew beyond the snapshot limit')
    checksum = sha256(data).hexdigest()
    suffix = source.suffix if source.suffix[1:].isalnum() and len(source.suffix) <= 16 else '.bin'
    relative = case_root + '/evidence/' + checksum + suffix
    target = inside(project, relative)
    if target.exists():
        if digest(target) != checksum:
            raise ValueError('Stored evidence snapshot changed; preserve and investigate it')
    else:
        from reverse_fusion.file_updates import atomic_write
        atomic_write(target, data)
    return {'path': relative, 'sha256': checksum, 'source_path': name, 'retention': 'snapshot'}


def product_record(project, change):
    candidates = file_identities(project, change.get('candidate_files'))
    references = file_identities(project, change.get('reference_files'))
    kind = change.get('kind', 'independent-reimplementation')
    if kind not in {'independent-reimplementation', 'specification-implementation', 'modified-original'}:
        raise ValueError('Product kind must distinguish independent, specification or modified-original output')
    if not candidates or not references and kind != 'specification-implementation':
        raise ValueError('Product identity needs candidate and reference files; specification implementation may omit the reference')
    if set(candidates) & set(references) or set(candidates.values()) & set(references.values()):
        raise ValueError('The reference identity cannot substitute for the candidate product')
    review = change.get('review')
    if not isinstance(review, str) or not review.strip():
        raise ValueError('Explain which files identify the candidate product and its reference')
    return {'candidate_files': candidates, 'reference_files': references, 'review': review, 'kind': kind,
            'qualification': 'Declared product files only; runtime launch and update identity require actual checks'}


def product_status(project, case):
    product = case.get('product')
    if not product:
        return {'status': 'not-declared'}
    try:
        current = product_record(project, {**product,
            'candidate_files': list(product['candidate_files']),
            'reference_files': list(product['reference_files'])})
        valid = all(current[k] == product[k] for k in ('candidate_files', 'reference_files'))
        return {'status': 'current' if valid else 'stale', 'candidate_files': list(product['candidate_files']),
                'reference_files': list(product['reference_files']), 'kind': product.get('kind', 'independent-reimplementation')}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {'status': 'stale', 'reason': str(exc)}


def execute(project, case_root, change, expected_revision, cancel_event=None):
    """Record and run one expensive operation without owning the host's reasoning."""
    from .workflow import _load, _record_path, _event, status
    project = project.resolve()
    identity = identifier(change.get('id'))
    kind = change.get('kind')
    if kind not in {'investigate', 'verify', 'visual', 'package'}:
        raise ValueError('Operation kind must be investigate, verify, visual or package')
    features, argv = change.get('features'), change.get('argv')
    if (not isinstance(features, list) or not features or any(not isinstance(f, str) for f in features)
            or not isinstance(argv, list) or not argv or len(argv) > 100
            or any(not isinstance(a, str) or not a or '\0' in a for a in argv)):
        raise ValueError('Declare affected features and an argv array')
    purpose = change.get('purpose')
    reason = change.get('retry_reason')
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError('State the concrete question or behavior this operation verifies')
    if reason is not None and (not isinstance(reason, str) or not reason.strip() or len(reason) > 2000):
        raise ValueError('A retry reason must identify new information')
    timeout = change.get('timeout_seconds', 120)
    if type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise ValueError('Operation timeout must be in (0, 600]')
    scratch_bytes = change.get('scratch_bytes', 256 * 1024 ** 2)
    if type(scratch_bytes) is not int or scratch_bytes < 1024 ** 2:
        raise ValueError('Declare at least 1 MiB of temporary working capacity')
    cwd_name = change.get('cwd', '.')
    cwd = project if cwd_name == '.' else inside(project, cwd_name)
    if not cwd.is_dir():
        raise ValueError('Operation working directory is missing')
    names = change.get('inputs')
    inputs = file_identities(project, names)
    if not inputs:
        raise ValueError('Declare the script, configuration and relevant code inputs')
    artifacts = change.get('artifacts', [])
    if (not isinstance(artifacts, list) or any(not isinstance(a, str) for a in artifacts)
            or len(set(artifacts)) != len(artifacts) or len(artifacts) > 100):
        raise ValueError('Declare at most 100 artifact files')
    for name in artifacts:
        inside(project, name)
    # A script may depend on external services or GUI state; reuse is explicit, never inferred.
    reusable = change.get('reusable', False)
    if type(reusable) is not bool or reusable and (not artifacts or kind not in {'verify', 'package'}):
        raise ValueError('Reusable verify/package operations need declared artifact files')
    keys = change.get('environment_keys', [])
    if not isinstance(keys, list) or any(not isinstance(k, str) or not k or '=' in k or '\0' in k for k in keys):
        raise ValueError('environment_keys must name application environment keys')
    env = launch_environment({'environment_keys': keys})
    local = cwd / argv[0]
    binary = Path(argv[0]) if Path(argv[0]).is_absolute() else local if local.is_file() else Path(shutil.which(argv[0]) or '')
    if not binary.is_file():
        raise ValueError('Operation executable is missing')
    # Resolve the same executable we hash, independent of PATH in the child cwd.
    binary = binary.resolve()
    run_argv = [str(binary), *argv[1:]]
    if any(arg in {'-c', '-e', '--eval', '/c', '/C', '-Command', '-EncodedCommand'} for arg in argv[1:]):
        raise ValueError('Save operation code in a declared script instead of inline shell code')
    invoked = []
    for arg in run_argv:
        candidate = Path(arg) if Path(arg).is_absolute() else cwd / arg
        if candidate.is_file() and candidate.resolve().is_relative_to(project):
            name = candidate.resolve().relative_to(project).as_posix()
            if name not in inputs:
                raise ValueError('Invoked project files must be declared inputs: ' + name)
            invoked.append(name)
    if not invoked:
        raise ValueError('Invoke a declared project script or executable; external tool/module dependencies need explicit input review')
    binding = {'kind': kind, 'features': sorted(set(features)), 'argv': run_argv, 'cwd': cwd_name,
        'scratch_bytes': scratch_bytes,
        'inputs': inputs, 'artifacts': artifacts, 'runtime': {'path': str(binary), 'sha256': digest(binary)},
        'environment_sha256': sha256(repr(sorted(env.items())).encode()).hexdigest()}
    signature = sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
    path = _record_path(project, case_root)
    from .disk import using_paths
    with locked(inside(project, case_root + '/operation-run')), using_paths(project, [*inputs, *artifacts]):
        with locked(path):
            case = _load(project, case_root)
            if type(expected_revision) is not int or expected_revision != case['revision']:
                raise ValueError('Stale case revision; reload before starting an operation')
            if any(f not in case['features'] for f in features):
                raise ValueError('Operation features must already exist')
            previous = [e for e in case['events'] if e['operation'] == 'operation-start'
                        and e['detail'].get('signature') == signature]
            latest = case.get('operations', {}).get(identity)
            if latest and latest.get('signature') == signature:
                try:
                    old = read(inside(project, latest['receipt']))
                    if (reusable and old.get('reusable') and digest(inside(project, latest['receipt'])) == latest['sha256']
                            and old['status'] == 'observed' and old['exit_code'] == 0
                            and file_identities(project, artifacts) == old['artifacts']):
                        return {'reused': True, 'receipt': latest['receipt'], 'operation': old,
                                'workflow': status(project, case_root)}
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            failed = 0
            for event in reversed(previous):
                try:
                    old = read(inside(project, event['detail']['output']+'/operation.json'))
                    if old.get('status') == 'observed' and old.get('exit_code') == 0:
                        break
                    failed += 1
                except (OSError, ValueError):
                    failed += 1
            limit = case.get('limits', {}).get('max_operation_failures', 3)
            if failed >= limit:
                raise ValueError('Three identical unsuccessful operations or configured failure budget exhausted; investigate or record a justified budget change')
            if failed and not reason:
                raise ValueError('Unchanged unsuccessful operation needs concrete new information or corrected inputs')
            attempt = sum(e['operation'] == 'operation-start' for e in case['events']) + 1
            output = case_root + '/operations/' + str(attempt) + '-' + identity
            destination = inside(project, output)
            if destination.exists():
                raise ValueError('Preserve earlier operation output')
            destination.mkdir(parents=True)
            _event(case, 'operation-start', {'id': identity, 'signature': signature, 'kind': kind,
                'features': features, 'purpose': purpose, 'output': output, 'retry_reason': reason})
            write(path, case)
        started = time.monotonic()
        from .disk import workspace
        scratch_cleanup = {}
        try:
            with workspace(project, purpose, 'Rerun the recorded script with its bound inputs', scratch_bytes,
                           cancel_event=cancel_event) as scratch:
                run_env = {**env, 'TEMP': str(scratch['path']), 'TMP': str(scratch['path']),
                           'TMPDIR': str(scratch['path']), 'RF_NEXT_SCRATCH': str(scratch['path'])}
                result = run_owned(run_argv, cwd=cwd, stdin=b'', timeout=timeout, memory_mb=2048,
                                   max_output_bytes=4 * 1024 * 1024, env=run_env, cancel_event=scratch['cancel_event'])
                if scratch['failure']:
                    result.update(status='unknown', reason=scratch['failure'][0])
            scratch_cleanup = scratch['cleanup']
            if scratch['failure']:
                result.update(status='unknown', reason=scratch['failure'][0])
        except (OSError, ValueError) as exc:
            result = {'status': 'unknown', 'exit_code': None, 'reason': str(exc),
                      'stdout': b'', 'stderr': b'', 'cleanup': 'no process established'}
        (destination / 'stdout.log').write_bytes(result.pop('stdout'))
        (destination / 'stderr.log').write_bytes(result.pop('stderr'))
        changed = []
        for name, checksum in inputs.items():
            try:
                if digest(inside(project, name)) != checksum:
                    changed.append(name)
            except OSError:
                changed.append(name)
        try:
            if digest(binary) != binding['runtime']['sha256']:
                changed.append('operation-runtime')
        except OSError:
            changed.append('operation-runtime')
        produced = {}
        for name in artifacts:
            artifact = inside(project, name)
            if artifact.is_file():
                produced[name] = digest(artifact)
        receipt = {**result, 'id': identity, 'kind': kind, 'features': features, 'purpose': purpose,
            'temporary_storage': scratch_cleanup,
            'binding': binding, 'reusable': reusable, 'artifacts': produced, 'changed_inputs': changed,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'acceptance': 'not-established; execution and artifacts only',
            'logs': [output + '/stdout.log', output + '/stderr.log']}
        if changed or len(produced) != len(artifacts):
            receipt['status'] = 'unknown'
            receipt['reason'] = 'Inputs changed or declared artifacts are missing'
        name = output + '/operation.json'
        write(inside(project, name), receipt)
        with locked(path):
            case = _load(project, case_root)
            case.setdefault('operations', {})[identity] = {'receipt': name, 'sha256': digest(inside(project, name)),
                'signature': signature, 'status': receipt['status'], 'exit_code': receipt.get('exit_code'),
                'kind': kind, 'features': features, 'elapsed_seconds': receipt['elapsed_seconds']}
            _event(case, 'operation', {'id': identity, 'receipt': name, 'status': receipt['status'],
                                     'exit_code': receipt.get('exit_code'), 'elapsed_seconds': receipt['elapsed_seconds']})
            write(path, case)
        return {'reused': False, 'receipt': name, 'operation': receipt, 'workflow': status(project, case_root)}
