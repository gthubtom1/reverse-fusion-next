"""Owned index of an actual public REA verification, never an Evidence producer."""
from hashlib import sha256
import json
from pathlib import Path
import time

from reverse_fusion.mcp_probe import StdioMcp
from reverse_fusion.runtime import node_runtime
from .providers import environment
from .storage import digest, inside, read, read_snapshot, write

ROOT = Path(__file__).resolve().parents[1]
OPERATION = 'rea-verified-claims'


def runtime_identity():
    node, _ = node_runtime(ROOT)
    if not node:
        raise ValueError('Install the pinned REA runtime first')
    package = ROOT/'vendor/rea/package'
    files = sorted([*package.glob('dist/**/*.js'), *package.glob('dist/**/*.json'),
                    *package.glob('scripts/**/*.mjs'), package/'package.json',
                    *(p for p in (package/'node_modules').rglob('*')
                      if p.is_file() and p.suffix in {'.js', '.mjs', '.cjs', '.json', '.node', '.wasm'})])
    identity = sha256()
    for path in files:
        identity.update((path.relative_to(package).as_posix()+'\0'+digest(path)+'\n').encode())
    # Pure verification imports observations; it does not start their providers.
    env = environment(ROOT)
    from .comparison import launch_environment
    inherited = launch_environment({})
    inherited.update({k: v for k, v in env.items() if k.startswith('REA_')})
    return {'node': str(node), 'node_sha256': digest(Path(node)),
            'official_code_sha256': identity.hexdigest(), 'official_code_files': len(files),
            'transport': {n: digest(ROOT/n) for n in ('reverse_fusion/mcp_probe.py', 'reverse_fusion/mcp_process.py')},
            'environment_sha256': sha256(json.dumps(inherited, sort_keys=True).encode()).hexdigest()}


def source_bindings(project, plan, destination=None):
    sides = {}
    for side in ('original', 'candidate'):
        conf = plan[side]
        if (not isinstance(conf, dict) or set(conf) != {'cwd', 'sources'}
                or not isinstance(conf['sources'], list) or not 1 <= len(conf['sources']) <= 500):
            raise ValueError('Native verification needs cwd and 1..500 actual source files per side')
        cwd = inside(project, conf['cwd'])
        if not cwd.is_dir() or (destination is not None and destination.is_relative_to(cwd)):
            raise ValueError('Keep verification outputs outside both source directories')
        files = {}
        for name in conf['sources']:
            path = inside(project, name)
            if not path.is_file() or not path.is_relative_to(cwd):
                raise ValueError('Every declared native subject must exist under its side cwd')
            files[path.relative_to(cwd).as_posix()] = digest(path)
        if len(files) != len(conf['sources']):
            raise ValueError('Duplicate native source paths')
        sides[side] = {'cwd': conf['cwd'], 'files': files}
    left, right = (inside(project, sides[s]['cwd']) for s in ('original', 'candidate'))
    if left.is_relative_to(right) or right.is_relative_to(left):
        raise ValueError('Native reference and candidate need independent paths')
    return sides


def bind_claims(project, bundle, claims, bindings):
    """Bind the verifier-selected sources, not arbitrary records elsewhere in a bundle."""
    records = {r['evidence_id']: r for r in bundle['records']}
    subjects = []
    used = {'original': set(), 'candidate': set()}
    expected_by_side = {side: {str(inside(project, conf['cwd']+'/'+name)): (conf['cwd']+'/'+name, checksum)
                              for name, checksum in conf['files'].items()}
                        for side, conf in bindings.items()}
    for claim in claims:
        selected = {'original': {}, 'candidate': {}}
        for side, field in (('original', 'left_evidence_ids'), ('candidate', 'right_evidence_ids')):
            ids = claim[field]
            if not ids:
                raise ValueError('Native claim omitted a source side')
            expected = expected_by_side[side]
            for identity in ids:
                record = records[identity]
                if claim['kind'] == 'behavioral':
                    if record['operation'] != 'capture_process_scenario':
                        raise ValueError('Behavioral source must be an official process capture')
                    manifest = record['normalized_result']['manifest']
                    scenario = manifest['scenario']
                    executable = Path(scenario['executable'])
                    # Capture commits its executable bytes, not arbitrary script,
                    # module or dependency files. Do not bless such extra sources.
                    if not executable.is_absolute() or len(expected) != 1:
                        raise ValueError('Behavioral binding supports one absolute captured executable per side; other source dependencies need independent observations')
                    path = str(executable.resolve())
                    entry = expected.get(path)
                    if not entry:
                        raise ValueError('Native capture executable is outside the declared '+side)
                    _, checksum = entry
                    if (manifest['selected_executable_sha256'] != checksum
                            or manifest['executable_sha256'] != checksum
                            or scenario.get('executable_sha256') != checksum
                            or manifest['executable_identity']['state'] != 'path_metadata_unchanged'
                            or not manifest['full_scenario_sha256'] or not manifest['comparison_contract_sha256']):
                        raise ValueError('Native capture executable identity is missing, changed or outside the declared '+side)
                    if executable.stem.lower() in {'python', 'python3', 'pythonw', 'node', 'nodejs', 'java', 'dotnet', 'cmd', 'powershell', 'pwsh', 'sh', 'bash'}:
                        raise ValueError('Interpreter capture does not authenticate its script/module inputs; use independently bound observations')
                else:
                    subject = record.get('subject')
                    if not isinstance(subject, dict):
                        raise ValueError('Structural source needs a native artifact subject')
                    path = str(Path(subject['local_path']).resolve())
                    entry = expected.get(path)
                    if not entry or entry[1] != subject['digest']['sha256']:
                        raise ValueError('Native claim subject is not the current '+side+' identity')
                name, checksum = entry
                selected[side][name] = checksum
                used[side].add(path)
        subjects.append(selected)
    for side, conf in bindings.items():
        if used[side] != {str(inside(project, conf['cwd']+'/'+name)) for name in conf['files']}:
            raise ValueError('Declared native source has no selected comparison claim')
    return subjects


def compare_native(project, plan_name, output, cancel_event=None, *, snapshot=None):
    plan_path, destination = inside(project, plan_name), inside(project, output)
    plan, plan_sha = read_snapshot(plan_path) if snapshot is None else snapshot
    required = {'version', 'kind', 'scope', 'bundle', 'specification', 'original', 'candidate', 'timeout_seconds'}
    if (set(plan) != required or type(plan['version']) is not int or plan['version'] != 2
            or plan['kind'] != 'rea' or not isinstance(plan['scope'], str) or not plan['scope'].strip()
            or type(plan['timeout_seconds']) not in (int, float) or not 0 < plan['timeout_seconds'] <= 120):
        raise ValueError('Native plan v2 requires scope, bundle, public specification, two source sides and 0..120 second deadline')
    if destination.exists():
        raise ValueError('Preserve previous runs; choose a new output path')
    bindings = source_bindings(project, plan, destination)
    bundle_path = inside(project, plan['bundle'])
    bundle_sha = digest(bundle_path)
    if bundle_path.is_relative_to(destination) or plan_path.is_relative_to(destination):
        raise ValueError('Input records must be outside the output directory')
    runtime = runtime_identity()
    adapter = digest(Path(__file__))
    destination.mkdir(parents=True)
    started = time.monotonic()
    result = {'schema_version': 2, 'operation': OPERATION, 'producer': 'owned-result-index',
        'status': 'unknown', 'scope': plan['scope'], 'plan': plan_name, 'plan_sha256': plan_sha,
        'bundle': plan['bundle'], 'bundle_sha256': bundle_sha, 'adapter_sha256': adapter,
        'native_runtime': runtime, 'input_trees': bindings,
        'sources': {conf['cwd']+'/'+name: checksum for conf in bindings.values() for name, checksum in conf['files'].items()},
        'cases': [], 'observation_files': {}, 'changed_inputs': [], 'failure': None,
        'rea_native_proof': 'not-performed', 'whole_product_acceptance': 'not-established',
        'limitations': ['Only the declared native claim kinds/dimensions are verified; no global equivalence.',
            'Imported Evidence identity is checked by REA; source provenance and the host goal mapping still need review.',
            'File freshness does not establish current external-service state or replace new runtime observations.']}
    client = None
    try:
        client = StdioMcp([runtime['node'], str(ROOT/'vendor/rea/package/scripts/rea.mjs'), 'mcp'],
                          cwd=ROOT, env=environment(ROOT), timeout=plan['timeout_seconds'])
        with client:
            def request(method, args=None):
                remaining = plan['timeout_seconds']-(time.monotonic()-started)
                if remaining <= 0:
                    raise TimeoutError('Native verification deadline')
                client.timeout = remaining
                return client.request(method, args, cancel_event=cancel_event)
            initialized = request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                'clientInfo': {'name': 'owned-rea-result-index', 'version': '1'}})
            client.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            def call(name, arguments):
                response = request('tools/call', {'name': name, 'arguments': arguments})
                if response.get('isError'):
                    raise ValueError('Official REA '+name+': '+json.dumps(response.get('content', [])))
                return response
            imported = call('import_evidence_bundle', {'path': str(bundle_path)})
            verified = call('verify_reconstruction', {'specification': plan['specification']})
            payload = verified['structuredContent']
            if payload['operation'] != 'verify_reconstruction' or payload['normalized_result']['status'] not in {'pass', 'fail', 'unknown'}:
                raise ValueError('Unexpected official verification response')
            native_output = destination/'native-bundle.json'
            call('export_evidence_bundle', {'path': str(native_output), 'overwrite': False})
            output_bundle = read(native_output)
            if not any(record == payload for record in output_bundle['records']):
                raise ValueError('Native verification result absent from the exported original bundle')
            claims = payload['normalized_result']['claims']['items']
            requested = plan['specification']['claims']
            if len(claims) != len(requested) or {c['claim_id'] for c in claims} != {c['claim_id'] for c in requested}:
                raise ValueError('Native verification omitted requested claims')
            subjects = bind_claims(project, output_bundle, claims, bindings)
            result['cases'] = [{'scenario': c['claim_id'], 'step': 0, 'status': c['status'],
                'dimension': c['kind']+':'+c['dimension'], 'differences': c['limitations'],
                'native_unknown_ids': c['unknown_ids'], 'evidence_id': c['comparison_evidence_id'],
                'subjects': selected}
                for c, selected in zip(claims, subjects, strict=True)]
            write(destination/'native-response.json', {'initialize': initialized, 'import': imported, 'verify': verified})
            result['observation_files'] = {p.relative_to(project).as_posix(): digest(p)
                for p in (native_output, destination/'native-response.json')}
            result['rea_native_proof'] = {'bundle': native_output.relative_to(project).as_posix(),
                'evidence_id': payload['evidence_id'], 'operation': payload['operation']}
            result['status'] = payload['normalized_result']['status']
        if client.cleanup['status'] not in {'verified', 'observed'}:
            raise ValueError('Native verification cleanup unverified')
        if (source_bindings(project, plan, destination) != bindings or digest(bundle_path) != bundle_sha
                or digest(plan_path) != plan_sha or runtime_identity() != runtime or digest(Path(__file__)) != adapter):
            result['changed_inputs'].append('inputs/runtime changed during verification')
            result['status'] = 'unknown'
    except (OSError, ValueError, KeyError, TypeError, EOFError) as exc:
        result.update(status='unknown', failure=str(exc))
    result['storage'] = {'cleanup': client.cleanup if client else None,
        'working_copies': 'none; pure verifier consumes original Evidence, no analysis provider started'}
    result['elapsed_ms'] = round((time.monotonic()-started)*1000, 3)
    write(destination/'comparison.json', result)
    return result


def fresh_native(project, result):
    if result['adapter_sha256'] != digest(Path(__file__)) or result['native_runtime'] != runtime_identity():
        return False
    plan, plan_sha = read_snapshot(inside(project, result['plan']))
    if plan_sha != result['plan_sha256'] or digest(inside(project, result['bundle'])) != result['bundle_sha256']:
        return False
    if source_bindings(project, plan) != result['input_trees']:
        return False
    proof = result['rea_native_proof']
    if not isinstance(proof, dict) or proof['bundle'] not in result['observation_files']:
        return False
    return all(digest(inside(project, name)) == checksum for name, checksum in result['observation_files'].items())


def dimensions(result):
    """Scope labels are derived by the producing adapter, never from a claimed pass."""
    operation = result.get('operation')
    if operation == OPERATION:
        return sorted({row['dimension'] for row in result['cases']})
    if operation == 'independent-finite-replay':
        return ['process:bounded']
    if operation == 'independent-web-replay':
        return ['web:declared-behavior', 'web:pixels']
    return []
