"""Validate run-scoped evidence for a fixed Windows engineering candidate."""
from collections import Counter
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import tomllib

from . import __version__
from .storage import digest, inside, read
from reverse_fusion.provider_runtime import PATH_KEYS, _existing

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'https://github.com/gthubtom1/reverse-fusion-next.git'
RUNS = 'work/qualification'
SCHEMA = 2
REMOTE_OUTPUTS = (
    'remote-clone.log', 'remote-install.log', 'remote-install.execution.json',
    'remote-tests.log', 'remote-tests.execution.json', 'remote-rollback.log',
    'remote-rollback.execution.json',
)
ROUTE_IDS = {f'R{i}' for i in (*range(42), 44, 45, 46)}
HELPERS = ('case_bridge', 'contracts', 'runtime', 'owned_process', 'global_adapter', 'mcp_adapter',
           'file_updates', 'mcp_process', 'mcp_probe', 'provider_runtime', '__init__', '__main__', 'cli')
LOCKS = (
    'pyproject.toml', 'vendor/node/manifest.json', 'vendor/rea/manifest.json',
    'components/rea-enhanced/provider-package.json',
    'components/rea-enhanced/provider-package-lock.json',
    'components/rea-enhanced/provider-bindings.json', 'vendor/wabt/1.0.42/manifest.json',
    'vendor/jadx-headless-mcp/0.7.1/manifest.json',
)
NATIVE_PROVIDER = 'test_mcp.LiveMCP.test_actual_native_provider_and_new_server_bundle_roundtrip'
NATIVE_RESTART = 'test_mcp.LiveMCP.test_native_bundle_survives_new_server'
NATIVE_BUNDLE = 'work/final-native-provider/native-bundle.json'
OPERATIONS = {
    NATIVE_PROVIDER: 'final-audit/native-provider.json',
    NATIVE_RESTART: 's2/native-restart-qualified.json',
    'test_mcp.LiveMCP.test_original_catalog_preserved_and_frida_actually_enumerates': 's2/protocol-qualified.json',
    'test_storage_tiers.StorageTiers.test_live_stdio_catalog_and_tier_lifecycle_preserve_actual_payload': 'tiered-storage/live-proof.json',
    **{'test_web.WebComparison.test_' + test: 'final-audit/web-' + name + '.json'
       for test, name in (
           ('same_visual_and_behavior', 'equal'),
           ('wrong_behavior_is_not_hidden_by_initial_look', 'wrong-behavior'),
           ('wrong_color_does_not_claim_behavior_failure', 'wrong-look'),
           ('missing_reference_observation_is_unknown', 'missing-observation'),
           ('dropdown_checkbox_storage_and_both_dialog_outcomes', 'controls'),
       )},
}
WEB_OUTCOMES = {'web-equal.json': 'pass', 'web-wrong-behavior.json': 'fail',
                'web-wrong-look.json': 'fail', 'web-missing-observation.json': 'unknown',
                'web-controls.json': 'pass'}
REQUIRED_TESTS = set(OPERATIONS) | {
    'test_domains.DomainMethods.test_all_domain_descriptors_and_support_are_available',
    'test_domains.DomainMethods.test_fixed_domain_files_and_recorded_adaptations',
    'test_deployment.Deployment.test_real_registered_server_and_owned_rollback',
}
HOST_ENV = {
    'PATH', 'PATHEXT', 'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'OS',
    'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMW6432', 'COMMONPROGRAMFILES',
    'COMMONPROGRAMFILES(X86)', 'COMMONPROGRAMW6432', 'PROCESSOR_ARCHITECTURE',
    'NUMBER_OF_PROCESSORS', 'LANG', 'LC_ALL', 'TZ',
}
PROVIDER_ENV = PATH_KEYS.keys() - {'REA_IDA_MCP_CONFIG', 'REA_PWNDBG_GDBINIT'}


def content_hash(path):
    data = path.read_bytes()
    if path.suffix not in {'.jar', '.exe', '.wasm', '.png'}:
        data = data.replace(b'\r\n', b'\n')
    return sha256(data).hexdigest()


def source_identity(root=ROOT):
    routes = read(root/'components/reverse-core/routing.json')['routes']
    if set(routes) != ROUTE_IDS:
        raise ValueError('Expected the 45 Reverse route IDs in routing.json')
    names = {f'components/reverse-core/routes/{route}.md' for route in routes}
    for directory in ('rea_enhanced', 'tests_next'):
        names.update(p.relative_to(root).as_posix() for p in (root/directory).glob('*.py'))
    names.update(f'reverse_fusion/{name}.py' for name in HELPERS)
    names.update(p.relative_to(root).as_posix() for p in (root/'fixtures/owned-native').glob('*.c'))
    names.update(LOCKS)
    names.update((
        'components/reverse-core/router.py', 'components/reverse-core/routing.json',
        'components/reverse-core/runtime.json', 'components/reverse-core/preservation.json',
        'components/rea-enhanced/web-replay.mjs', 'scripts/install.ps1', 'VERSION',
        'AGENTS.md', 'RULES.md', 'README.md', 'docs/ACTIVE-DOCUMENTS.json',
        'docs/NEXT/REQUIREMENTS.md', 'scripts/next-clean-install.py', 'scripts/next-cli.py',
        'scripts/next-remote-install.py', 'scripts/next-qualify.py', 'scripts/next-qualification-suite.py',
        'release/manifest.json', 'components/official/manifest.json', 'SOURCE-MANIFEST.json',
        'skills/tests/routing-benchmark.json', 'fixtures/owned-native/guarded.c',
    ))
    names.update(n for n in read(root/'docs/ACTIVE-DOCUMENTS.json')['active']
                 if n != 'docs/CURRENT-STATE.md')
    return {name: content_hash(inside(root, name)) for name in sorted(names)}


def domain_failures(root):
    pin = read(root/'components/reverse-core/preservation.json')
    return ['Domain origin changed: ' + name for name, entry in pin['files'].items()
            if content_hash(inside(root, name)) != entry['sha256']]


def qualification_environment(root, temporary):
    """Give each qualification process its own host directories and disk registry."""
    env = {key.upper(): value for key, value in os.environ.items() if key.upper() in HOST_ENV}
    # Keep system tools available without searching the development/retired project or cwd.
    blocked = (root, root.parent/'reverse')
    directories = []
    for item in env.get('PATH', '').split(os.pathsep):
        if item and Path(item).is_absolute():
            path = Path(item).resolve()
            if not any(path.is_relative_to(project) for project in blocked):
                directories.append(item)
    env['PATH'] = os.pathsep.join(directories)
    git_command = shutil.which('git', path=env['PATH'])
    if os.name == 'nt' and git_command and not shutil.which('bash', path=env['PATH']):
        git_bash = Path(git_command).resolve().parent.parent/'bin/bash.exe'
        if git_bash.is_file():
            env['PATH'] = os.pathsep.join([*directories, str(git_bash.parent)])
    home = temporary/'host'
    paths = {'HOME': home, 'USERPROFILE': home, 'CODEX_HOME': home/'.codex',
             'APPDATA': home/'AppData/Roaming', 'LOCALAPPDATA': home/'AppData/Local',
             'PROGRAMDATA': home/'ProgramData', 'XDG_CONFIG_HOME': home/'config',
             'XDG_CACHE_HOME': home/'cache', 'XDG_DATA_HOME': home/'data',
             'XDG_STATE_HOME': home/'state', 'TEMP': temporary/'tmp',
             'RF_NEXT_DISK_STATE': temporary/'coordinator'}
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env.update(TMP=env['TEMP'], TMPDIR=env['TEMP'], GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_GLOBAL=str(home/'.gitconfig'))
    if home.drive:
        env.update(HOMEDRIVE=home.drive, HOMEPATH=str(home)[len(home.drive):])
    return env


def qualification_providers(root, checkout=None):
    """Carry selected tool paths, excluding startup scripts and client registrations."""
    paths = {key: os.environ[key] for key in PROVIDER_ENV if os.environ.get(key)}
    saved = root/'state/rea-providers.json'
    if saved.is_file():
        receipt = read(saved)
        if Path(receipt['repository_root']).resolve() != root:
            raise ValueError('Provider selection belongs to another checkout')
        paths.update({key: value for key, value in receipt['paths'].items() if key in PROVIDER_ENV})
    selected = {}
    for key, value in paths.items():
        path = Path(value)
        if not path.is_absolute():
            continue
        path = path.resolve()
        if path.is_relative_to(root.parent/'reverse'):
            continue
        if path.is_relative_to(root):
            if checkout is None:
                continue
            path = checkout/path.relative_to(root)
        try:
            selected[key] = str(_existing(key, str(path)))
        except (ValueError, OSError):
            continue  # An unavailable optional provider will be diagnosed by the dependent test.
    return selected


def git(root, *args, env=None, timeout=30):
    result = subprocess.run(['git', *args], cwd=root, env=env, capture_output=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Git command failed: ' + args[0] + ': ' + result.stderr.decode(errors='replace').strip())
    return result.stdout


def fixed_commit(root, requested=None, *, env=None):
    repository = Path(git(root, 'rev-parse', '--show-toplevel', env=env).decode('utf-8').strip())
    if repository.resolve() != root.resolve():
        raise ValueError('Qualification source must be the root of the selected Git checkout')
    head = git(root, 'rev-parse', '--verify', 'HEAD', env=env).decode().strip()
    if requested is not None and (not re.fullmatch(r'[a-f0-9]{40}', requested) or head != requested):
        raise ValueError('Use the full 40-character commit checked out at HEAD')
    if git(root, 'status', '--porcelain=v1', '--untracked-files=all', env=env):
        if requested is None:
            return None
        raise ValueError('Fixed-candidate qualification requires a clean source checkout')
    return head


def new_run(parent, kind):
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f'{kind}-{time.time_ns():020d}-', dir=parent)).resolve()


def latest_run(root, kind):
    return max((p for p in (root/RUNS).glob(kind + '-*') if p.is_dir()), default=None)


def test_failures(plan, results):
    if not plan:
        return ['No tests discovered']
    failures = []
    if len(set(plan)) != len(plan):
        failures.append('Duplicate planned test IDs')
    missing = (set(plan) | REQUIRED_TESTS) - results.keys()
    failures.extend('Required test did not run: ' + test for test in sorted(missing))
    failures.extend('Required test was not discovered: ' + test for test in sorted(REQUIRED_TESTS - set(plan)))
    failures.extend(f'{entry["status"]}: {test}' for test, entry in results.items()
                    if entry['status'] != 'pass')
    failures.extend('Unplanned test result: ' + test for test in sorted(results.keys() - set(plan)))
    return failures


def operation_passes(path):
    record = read(path)
    return record.get('status') == 'pass' and (
        path.name not in WEB_OUTCOMES or record.get('observed_comparison_status') == WEB_OUTCOMES[path.name])


def operation_failures(run, report):
    failures = []
    operations = report.get('operations', {})
    for test, name in OPERATIONS.items():
        item = operations.get(name, {})
        path = inside(run, 'operations/' + name)
        if (item.get('run_id') != run.name or item.get('test_id') != test or not path.is_file()
                or item.get('sha256') != digest(path) or not operation_passes(path)):
            failures.append('Missing or changed current operation: ' + name)
    for name in ('native-bundle.json', 'restored-bundle.json'):
        bundle = inside(run, 'operations/native/' + name)
        if not bundle.is_file() or report.get('native_bundles', {}).get(name) != digest(bundle):
            failures.append('Missing or changed current native bundle: ' + name)
    return failures


def engineering_failures(run, source, commit):
    report = read(run/'engineering-tests.json')
    failures = []
    if (not commit or report.get('candidate_kind') != 'git-commit'
            or report.get('schema_version') != SCHEMA or report.get('run_id') != run.name
            or report.get('source_identity') != source or report.get('source_commit') != commit
            or report.get('dependency_locks') != {name: source[name] for name in LOCKS}):
        failures.append('Engineering run identity differs from the candidate: ' + run.name)
    if (report.get('status') != 'pass' or report.get('exit_code') != 0
            or report.get('execution_status') != 'observed' or not report.get('runtime')
            or report.get('source_unchanged_during_tests') is not True):
        failures.append('Engineering run did not pass: ' + run.name)
    plan, results = report.get('planned_tests', []), report.get('test_results', {})
    failures.extend(test_failures(plan, results))
    counts = dict(Counter(item['status'] for item in results.values()))
    if report.get('tests') != len(results) or report.get('test_counts') != counts:
        failures.append('Engineering test totals disagree with individual results')
    if digest(run/'engineering-tests.txt') != report.get('test_log_sha256'):
        failures.append('Engineering test log changed')
    failures.extend(operation_failures(run, report))
    return failures


def installed_runtime_failures(probe_runtime, engineering_runtime):
    """Match the bytes observed over installed stdio to the staged engineering runtime."""
    failures = []
    for field, label in (('node_sha256', 'Node'), ('official_entry_sha256', 'official REA entry')):
        observed = probe_runtime.get(field) if isinstance(probe_runtime, dict) else None
        expected = engineering_runtime.get(field) if isinstance(engineering_runtime, dict) else None
        if any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value)
               for value in (observed, expected)):
            failures.append(f'Independent install {label} fingerprint is missing or invalid')
        elif observed != expected:
            failures.append(f'Independent install {label} fingerprint differs from installed engineering')
    return failures


def remote_failures(run, source, commit):
    report = read(run/'remote-install.json')
    if (report.get('schema_version') != SCHEMA or report.get('run_id') != run.name
            or report.get('status') != 'pass' or report.get('source_identity') != source
            or report.get('repository') != REPOSITORY or report.get('source_commit') != commit
            or report.get('source_method') != 'git-clone-remote-detached'
            or report.get('destination_retained') is not False
            or report.get('temporary_user_rollback') != 'exact'
            or report.get('mcp_check', {}).get('status') != 'pass'):
        return ['Independent fixed-candidate clone/install qualification is missing or stale']
    child = inside(run, 'installed-engineering/' + report['engineering_run_id'])
    failures = []
    evidence = report.get('outputs_sha256', {})
    for name in REMOTE_OUTPUTS:
        path = inside(run, name)
        if not path.is_file() or evidence.get(name) != digest(path):
            failures.append('Missing or changed independent install output: ' + name)
    engineering_path = child/'engineering-tests.json'
    if digest(engineering_path) != report.get('engineering_report_sha256'):
        return failures + ['Independent install engineering report changed']
    failures.extend(installed_runtime_failures(report['mcp_check'].get('runtime'),
                                               read(engineering_path).get('runtime')))
    return failures + engineering_failures(child, source, commit)


def historical_status(root):
    """Describe unchanged legacy records without promoting them to current qualification."""
    try:
        local = read(root/'evidence/next/s6/engineering-tests.json')
        remote = read(root/'evidence/next/final-audit/remote-install.json')
        return {'scope': 'historical-only', 'source_commit': remote.get('source_commit'),
                'engineering_status': local.get('status'), 'remote_install_status': remote.get('status'),
                'engineering_tests': local.get('tests'), 'remote_install_tests': remote.get('tests')}
    except (ValueError, OSError):
        return {'scope': 'historical-only', 'status': 'unavailable'}


def release_check(root=ROOT, require_deployed=False, *, engineering_run=None, remote_run=None):
    failures = []
    try:
        source = source_identity(root)
        commit = fixed_commit(root)
        failures.extend(domain_failures(root))
        versions = [tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version'],
                    *(read(root/name)['version'] for name in ('release/manifest.json',
                      'components/official/manifest.json', 'SOURCE-MANIFEST.json', 'docs/ACTIVE-DOCUMENTS.json')),
                    (root/'VERSION').read_text(encoding='utf-8').strip()]
        if any(version != __version__ for version in versions):
            failures.append('Current entry versions disagree')
        for name in read(root/'docs/ACTIVE-DOCUMENTS.json')['active']:
            if not inside(root, name).is_file():
                failures.append('Active documentation missing: ' + name)
        if not commit:
            failures.append('Current source is not a clean fixed Git candidate')
        for label, run, validate in (
            ('Engineering', engineering_run or latest_run(root, 'engineering'), engineering_failures),
            ('Independent clone/install', remote_run or latest_run(root, 'remote'), remote_failures),
        ):
            if run is None:
                failures.append(label + ' qualification is missing for the current candidate')
                continue
            try:
                failures.extend(validate(Path(run).resolve(), source, commit))
            except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
                failures.append(f'{label} qualification is unreadable: {exc}')
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        failures.append(str(exc))
    connection = None
    if require_deployed and not failures:
        from .deployment import probe
        try:
            connection = probe(root)
        except (ValueError, OSError, TimeoutError, EOFError) as exc:
            failures.append(str(exc))
    return {'status': 'pass' if not failures else 'fail', 'version': __version__, 'failures': failures,
            'connection': connection, 'historical': historical_status(root),
            'scope': 'Source-bound Windows x64 Codex engineering and retained finite evidence',
            'whole_product_acceptance': 'not-established; task-specific coverage remains required'}
