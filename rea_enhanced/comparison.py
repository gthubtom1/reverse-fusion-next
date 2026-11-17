"""Independent finite replay; the candidate never grades itself."""
import base64
from pathlib import Path
import shutil
import time
import os
from hashlib import sha256
from reverse_fusion.owned_process import run_owned
from .storage import digest, inside, read, write


def launch_environment(plan):
    # CLI and MCP hosts add different internal variables. Those are not target
    # inputs: launch only this explicit environment, plus plan-declared app keys.
    keys={'SystemRoot','SYSTEMROOT','WINDIR','SystemDrive','COMSPEC','TEMP','TMP','PATH','PATHEXT',
          'USERPROFILE','HOME','APPDATA','LOCALAPPDATA','PROGRAMDATA','PROGRAMFILES','PROGRAMFILES(X86)',
          'PYTHONPATH','PYTHONHOME','PYTHONHASHSEED','NODE_PATH','NODE_OPTIONS','JAVA_HOME','JAVA_TOOL_OPTIONS',
          'LANG','LC_ALL','TZ'} | set(plan.get('environment_keys',[]))
    return {key:value for key,value in os.environ.items() if key in keys}


def process_identity(sides, plan):
    """Bind executable resolution and relevant inherited launch configuration, without secrets."""
    result = {}
    for side, conf in sides.items():
        argv = conf['config']['argv']
        local = conf['cwd']/argv[0]
        executable = (Path(argv[0]) if Path(argv[0]).is_absolute() else local if local.is_file()
                      else Path(shutil.which(argv[0]) or ''))
        if not executable.is_file():
            raise ValueError('Replay executable is missing: ' + argv[0])
        executable = executable.resolve()
        result[side] = {'path':str(executable),'sha256':digest(executable)}
    result['environment_sha256'] = sha256(repr(sorted(launch_environment(plan).items())).encode()).hexdigest()
    return result


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


def observe_files(root, names, project=None, destination=None):
    result = {}
    for name in names:
        p = inside(root, name)
        if not p.is_file():
            result[name] = {'status': 'missing'}
        elif p.stat().st_size > 4 * 1024 * 1024:
            result[name] = {'status': 'output-limit'}
        else:
            checksum = digest(p)
            result[name] = {'status': 'observed', 'bytes': p.stat().st_size, 'sha256': checksum}
            if destination is not None:
                target = destination / 'effects' / checksum
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, target)
                result[name]['snapshot'] = target.relative_to(project).as_posix()
    return result


def validate_plan(project, plan, destination):
    required = {'version', 'scope', 'original', 'candidate', 'scenarios', 'timeout_seconds'}
    if (set(plan)-{'environment_keys'} != required or type(plan['version']) is not int or plan['version'] != 2
            or not isinstance(plan['scope'], str) or not plan['scope'].strip()):
        raise ValueError('Version 2 requires scope, two sides, scenarios and timeout_seconds')
    if (not isinstance(plan.get('environment_keys',[]),list)
            or any(not isinstance(k,str) or not k or '=' in k or '\0' in k for k in plan.get('environment_keys',[]))):
        raise ValueError('environment_keys must name explicit additional inherited application inputs')
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
            if any(Path(arg).is_absolute() for arg in step['args']):
                raise ValueError('External scenario inputs must be copied into the declared source trees')
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
        invoked = []
        for i, arg in enumerate(conf['argv']):
            if arg.startswith('-'):
                continue
            p = Path(arg)
            resolved = p.resolve() if p.is_absolute() else (cwd/p).resolve()
            if i and p.is_absolute() and not resolved.is_relative_to(cwd):
                raise ValueError('External argv input must be copied into the declared source tree')
            if resolved.is_file() and resolved.is_relative_to(cwd):
                invoked.append(resolved)
        if not any(inside(project,name) in invoked for name in conf['sources']):
            raise ValueError('Replay argv must actually invoke a declared source, not an unrelated external command')
        if any(arg in {'-c','-e','--eval','/c','/C','-Command','-EncodedCommand'} for arg in conf['argv'][1:]):
            raise ValueError('Inline argv code is not a declared source; save it in the side source tree')
        sides[side] = {'config': conf, 'cwd': cwd, 'tree': snapshot, 'sources': refs}
    left, right = sides['original'], sides['candidate']
    if (set(left['sources']) & set(right['sources'])
            or set(left['sources'].values()) == set(right['sources'].values())
            or left['cwd'].is_relative_to(right['cwd']) or right['cwd'].is_relative_to(left['cwd'])):
        raise ValueError('Reference and candidate need independent source paths and identities')
    return sides


def engine_identity(web=False):
    root=Path(__file__).resolve().parents[1]
    names=['rea_enhanced/comparison.py','rea_enhanced/disk.py','reverse_fusion/owned_process.py']
    if web:names+=['rea_enhanced/web.py','components/rea-enhanced/web-replay.mjs']
    return {name:digest(root/name) for name in names}


def compare(project: Path, plan_name: str, output: str, cancel_event=None) -> dict:
    project = project.resolve()
    plan_path, destination = inside(project, plan_name), inside(project, output)
    plan = read(plan_path)
    if plan.get('kind') == 'web':
        from .web import compare_web
        return compare_web(project,plan_name,output,cancel_event=cancel_event)
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
    engine=engine_identity()
    launch=process_identity(sides,plan)
    from .disk import protect, workspace, MiB
    protect(project, [plan_name, output, *(c['config']['cwd'] for c in sides.values())])
    destination.mkdir(parents=True)
    cleanup = []
    scratch_budget = max(64 * MiB, sum(sum(p.stat().st_size for p in c['cwd'].rglob('*') if p.is_file()) for c in sides.values()) + 32 * MiB)
    started, results, failure = time.perf_counter(), [], None
    try:
        for scenario in plan['scenarios']:
            with workspace(project, 'Finite comparison ' + scenario['id'],
                           'Rerun ' + plan_name + ' with unchanged declared fixtures', scratch_budget,
                           cancel_event=cancel_event) as scratch:
                places = {}
                for side, conf in sides.items():
                    area = scratch['path'] / side
                    shutil.copytree(conf['cwd'], area)
                    places[side] = area
                    (scratch['path'] / ('temp-' + side)).mkdir()
                for index, step in enumerate(scenario['steps']):
                    if cancel_event and cancel_event.is_set():
                        raise ValueError('Comparison cancelled')
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
                            temp = str(scratch['path'] / ('temp-' + side))
                            environment = {**launch_environment(plan), 'TEMP': temp, 'TMP': temp, 'TMPDIR': temp}
                            run = run_owned([*argv, *step['args']], cwd=area, stdin=step['stdin'].encode('utf-8'),
                                timeout=min(plan['timeout_seconds'], max(.001, 600 - (time.perf_counter() - started))),
                                memory_mb=512, max_output_bytes=1024 * 1024, cancel_event=scratch['cancel_event'],
                                env=environment)
                            observed = {k: v for k, v in run.items() if k not in {'stdout', 'stderr'}}
                            observed.update(stdout=base64.b64encode(run['stdout']).decode('ascii'),
                                stderr=base64.b64encode(run['stderr']).decode('ascii'),
                                files=observe_files(area, step['files'], project, destination))
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
                if scratch['failure']:
                    raise ValueError(scratch['failure'][0])
            cleanup.append(scratch['cleanup'])
            if scratch['failure']:
                raise ValueError(scratch['failure'][0])
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
    if engine_identity()!=engine:changed.append('comparison-engine')
    try:
        if process_identity(sides,plan)!=launch:changed.append('process-runtime')
    except (OSError,ValueError):changed.append('process-runtime')
    expected_count = sum(len(s['steps']) for s in plan['scenarios'])
    status = ('unknown' if failure or changed or len(results) != expected_count or any(r['status'] == 'unknown' for r in results)
              else 'fail' if any(r['status'] == 'fail' for r in results) else 'pass')
    result = {'schema_version': 2, 'operation': 'independent-finite-replay', 'status': status,
        'scope': plan['scope'], 'plan': plan_name, 'plan_sha256': plan_sha,
        'sources': {name: value for conf in sides.values() for name, value in conf['sources'].items()},
        'engine':engine, 'process_runtime':launch,
        'input_trees': {side: {'cwd': conf['config']['cwd'], 'files': conf['tree']} for side, conf in sides.items()},
        'cases': results, 'changed_inputs': changed, 'failure': failure,
        'storage': {'cleanup': cleanup, 'working_copies': 'owned scratch; reclaimed after each scenario',
                    'observed_files': 'content-addressed snapshots retained under effects'},
        'elapsed_ms': round((time.perf_counter() - started) * 1000, 3),
        'rea_native_proof': 'not-performed', 'whole_product_acceptance': 'not-established',
        'limitations': ['Only declared ordered inputs, raw output, exit and named file effects were compared.',
            'Working copies and owned cleanup are not filesystem or network isolation.',
            'No UI, network, unlisted effects or whole-program equivalence established.']}
    write(destination / 'comparison.json', result)
    return result


def fresh(project: Path, result: dict) -> bool:
    try:
        if result.get('engine')!=engine_identity(web=result.get('operation')=='independent-web-replay'):
            return False
        if result.get('browser_executable') and digest(Path(result['browser_executable']))!=result['browser_sha256']:
            return False
        if digest(inside(project, result['plan'])) != result['plan_sha256']:
            return False
        for conf in result['input_trees'].values():
            if tree(inside(project, conf['cwd'])) != conf['files']:
                return False
        for case in result.get('cases', []):
            for observation in case.get('observations', {}).values():
                for observed in observation.get('files', {}).values():
                    if observed.get('snapshot') and digest(inside(project, observed['snapshot'])) != observed['sha256']:
                        return False
        if result.get('operation') == 'independent-finite-replay':
            plan = read(inside(project,result['plan']))
            sides = {side:{'config':plan[side],'cwd':inside(project,plan[side]['cwd'])}
                     for side in ('original','candidate')}
            if result.get('process_runtime') != process_identity(sides,plan):
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
