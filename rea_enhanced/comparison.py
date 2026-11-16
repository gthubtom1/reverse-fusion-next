"""Independent finite replay; the candidate never grades itself."""
import base64
from pathlib import Path
import shutil
import time
from reverse_fusion.owned_process import run_owned
from .storage import digest, inside, read, write


def tree(root):
    files, total = {}, 0
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Replay source trees cannot contain links or escaped paths')
        if path.is_file():
            if '.git' in path.relative_to(root).parts:
                raise ValueError('Use a bounded source fixture, not a Git checkout')
            total += path.stat().st_size
            if len(files) >= 2000 or total > 256 * 1024 * 1024:
                raise ValueError('Replay tree too large; narrow the source')
            files[path.relative_to(root).as_posix()] = digest(path)
    return files


def observe_files(root, names):
    result = {}
    for name in names:
        p = inside(root, name)
        if not p.is_file():
            result[name] = {'status': 'missing'}
        elif p.stat().st_size > 4 * 1024 * 1024:
            result[name] = {'status': 'output-limit'}
        else:
            result[name] = {'status': 'observed', 'bytes': p.stat().st_size, 'sha256': digest(p)}
    return result


def validate_plan(project, plan, destination):
    required = {'version', 'scope', 'original', 'candidate', 'scenarios', 'timeout_seconds'}
    if (set(plan) != required or type(plan['version']) is not int or plan['version'] != 2
            or not isinstance(plan['scope'], str) or not plan['scope'].strip()):
        raise ValueError('Version 2 requires scope, two sides, scenarios and timeout_seconds')
    if type(plan['timeout_seconds']) not in (int, float) or not 0 < plan['timeout_seconds'] <= 60:
        raise ValueError('Timeout must be in (0, 60]')
    scenarios = plan['scenarios']
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 100:
        raise ValueError('Declare 1..100 finite scenarios')
    ids = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {'id', 'steps'}:
            raise ValueError('Each scenario requires id and steps')
        identity = scenario['id']
        if (not isinstance(identity, str) or not identity or len(identity) > 80
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in identity)
                or identity in ids):
            raise ValueError('Scenario IDs must be unique portable identifiers')
        ids.add(identity)
        if not isinstance(scenario['steps'], list) or not 1 <= len(scenario['steps']) <= 50:
            raise ValueError('Each scenario needs 1..50 ordered steps')
        for step in scenario['steps']:
            if (not isinstance(step, dict) or set(step) != {'stdin', 'args', 'files', 'expected_exit_codes'}
                    or not isinstance(step['stdin'], str) or len(step['stdin']) > 1024 * 1024
                    or not isinstance(step['args'], list) or any(not isinstance(s, str) or '\0' in s for s in step['args'])
                    or not isinstance(step['files'], list) or any(not isinstance(s, str) for s in step['files'])
                    or len(set(step['files'])) != len(step['files'])
                    or not isinstance(step['expected_exit_codes'], list) or not step['expected_exit_codes']
                    or any(type(c) is not int for c in step['expected_exit_codes'])):
                raise ValueError('Each step needs stdin, args, files and expected reference exit codes')
            for name in step['files']:
                inside(project, name)
    sides = {}
    for side in ('original', 'candidate'):
        conf = plan[side]
        if (not isinstance(conf, dict) or set(conf) != {'argv', 'cwd', 'sources'}
                or not isinstance(conf['argv'], list) or not conf['argv']
                or any(not isinstance(s, str) or '\0' in s for s in conf['argv'])
                or not isinstance(conf['sources'], list) or not conf['sources']):
            raise ValueError('Each side requires argv, bounded cwd and declared sources')
        cwd = inside(project, conf['cwd'])
        if not cwd.is_dir() or destination.is_relative_to(cwd):
            raise ValueError('Output must be outside each replay source tree')
        snapshot = tree(cwd)
        refs = {}
        for name in conf['sources']:
            p = inside(project, name)
            if not p.is_file() or not p.is_relative_to(cwd):
                raise ValueError('Sources must be files under the side cwd')
            refs[name] = digest(p)
        sides[side] = {'config': conf, 'cwd': cwd, 'tree': snapshot, 'sources': refs}
    left, right = sides['original'], sides['candidate']
    if (set(left['sources']) & set(right['sources'])
            or set(left['sources'].values()) == set(right['sources'].values())
            or left['cwd'] == right['cwd']):
        raise ValueError('Reference and candidate need independent source paths and identities')
    return sides


def compare(project: Path, plan_name: str, output: str) -> dict:
    project = project.resolve()
    plan_path, destination = inside(project, plan_name), inside(project, output)
    plan = read(plan_path)
    sides = validate_plan(project, plan, destination)
    if sum(len(s['steps']) for s in plan['scenarios']) > 200:
        raise ValueError('At most 200 steps per replay')
    for conf in sides.values():
        for arg in conf['config']['argv']:
            p = Path(arg)
            if p.is_absolute() and p.resolve().is_relative_to(project) and not p.resolve().is_relative_to(conf['cwd']):
                raise ValueError('Replay argv references another project area')
    if destination.exists():
        raise ValueError('Preserve previous runs; choose a new output path')
    plan_sha = digest(plan_path)
    destination.mkdir(parents=True)
    started, results, failure = time.perf_counter(), [], None
    try:
        for scenario in plan['scenarios']:
            places = {}
            for side, conf in sides.items():
                area = destination / 'runs' / scenario['id'] / side
                shutil.copytree(conf['cwd'], area)
                places[side] = area
            for index, step in enumerate(scenario['steps']):
                if time.perf_counter() - started >= 600:
                    raise ValueError('Total comparison deadline exceeded')
                pair = {'scenario': scenario['id'], 'step': index, 'observations': {}, 'differences': []}
                for side, conf in sides.items():
                    area = places[side]
                    argv = []
                    for arg in conf['config']['argv']:
                        p = Path(arg)
                        if p.is_absolute() and p.resolve().is_relative_to(conf['cwd']):
                            arg = str(area / p.resolve().relative_to(conf['cwd']))
                        argv.append(arg)
                    try:
                        run = run_owned([*argv, *step['args']], cwd=area, stdin=step['stdin'].encode('utf-8'),
                            timeout=min(plan['timeout_seconds'], max(.001, 600 - (time.perf_counter() - started))),
                            memory_mb=512, max_output_bytes=1024 * 1024)
                        observed = {k: v for k, v in run.items() if k not in {'stdout', 'stderr'}}
                        observed.update(stdout=base64.b64encode(run['stdout']).decode('ascii'),
                            stderr=base64.b64encode(run['stderr']).decode('ascii'),
                            files=observe_files(area, step['files']))
                    except OSError as exc:
                        observed = {'status': 'unknown', 'reason': str(exc), 'cleanup': 'no invocation established'}
                    pair['observations'][side] = observed
                left, right = pair['observations']['original'], pair['observations']['candidate']
                comparable = (left['status'] == right['status'] == 'observed'
                    and left['exit_code'] in step['expected_exit_codes']
                    and all(f['status'] == 'observed' for f in left['files'].values()))
                if comparable:
                    for channel in ('exit_code', 'stdout', 'stderr', 'files'):
                        if left[channel] != right[channel]:
                            pair['differences'].append(channel)
                    has_observation = bool(left['stdout'] or left['stderr'] or step['files'])
                    pair['status'] = 'fail' if pair['differences'] else 'pass' if has_observation else 'unknown'
                    if not has_observation:
                        pair['reason'] = 'No output or declared effect to establish comparable behavior'
                else:
                    pair['status'] = 'unknown'
                    pair['reason'] = 'Incomplete runtime, unexpected reference exit, or missing effect'
                results.append(pair)
    except (OSError, ValueError) as exc:
        failure = str(exc)
    changed = []
    for side, conf in sides.items():
        try:
            if tree(conf['cwd']) != conf['tree']:
                changed.append(side)
        except (OSError, ValueError):
            changed.append(side)
    if not plan_path.is_file() or digest(plan_path) != plan_sha:
        changed.append(plan_name)
    expected_count = sum(len(s['steps']) for s in plan['scenarios'])
    status = ('unknown' if failure or changed or len(results) != expected_count or any(r['status'] == 'unknown' for r in results)
              else 'fail' if any(r['status'] == 'fail' for r in results) else 'pass')
    result = {'schema_version': 2, 'operation': 'independent-finite-replay', 'status': status,
        'scope': plan['scope'], 'plan': plan_name, 'plan_sha256': plan_sha,
        'sources': {name: value for conf in sides.values() for name, value in conf['sources'].items()},
        'input_trees': {side: {'cwd': conf['config']['cwd'], 'files': conf['tree']} for side, conf in sides.items()},
        'cases': results, 'changed_inputs': changed, 'failure': failure,
        'elapsed_ms': round((time.perf_counter() - started) * 1000, 3),
        'rea_native_proof': 'not-performed', 'whole_product_acceptance': 'not-established',
        'limitations': ['Only declared ordered inputs, raw output, exit and named file effects were compared.',
            'Working copies and owned cleanup are not filesystem or network isolation.',
            'No UI, network, unlisted effects or whole-program equivalence established.']}
    write(destination / 'comparison.json', result)
    return result


def fresh(project: Path, result: dict) -> bool:
    try:
        if digest(inside(project, result['plan'])) != result['plan_sha256']:
            return False
        for conf in result['input_trees'].values():
            if tree(inside(project, conf['cwd'])) != conf['files']:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
