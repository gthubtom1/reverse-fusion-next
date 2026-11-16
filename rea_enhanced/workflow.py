"""One durable case: goal, evidence, dependent unknowns and finite checks."""
from pathlib import Path
import time
from reverse_fusion.case_bridge import dry_run_route, request_intent
from .storage import digest, inside, locked, read, write
from .comparison import compare, fresh

ROOT = Path(__file__).resolve().parents[1]


def _record_path(project, case_root):
    return inside(project, case_root + '/case-v2.json')


def _load(project, case_root):
    value = read(_record_path(project, case_root))
    if (value.get('schema_version') != 2 or value.get('case_root') != case_root
            or Path(value.get('project_root', '')).resolve() != project.resolve()
            or type(value.get('revision')) is not int):
        raise ValueError('Case identity/schema changed; recover the original case')
    return value


def _event(case, operation, detail):
    case['revision'] += 1
    case['events'].append({'revision': case['revision'], 'time': time.time(),
                           'operation': operation, 'detail': detail})


def _evidence_valid(project, case, identity):
    try:
        e = case['evidence'][identity]
        return digest(inside(project, e['path'])) == e['sha256']
    except (KeyError, OSError, ValueError):
        return False


def open_case(project: Path, request: str, case_root='work/current-case'):
    project = project.resolve()
    if not isinstance(request, str) or not request.strip():
        raise ValueError('The original plain-language request is required')
    intent = request_intent(request)
    index_path = inside(project, '.rea-enhanced/cases.json')
    if intent == 'normal-dev':
        return {'status': 'host-native', 'request': request, 'case_created': False}
    path = _record_path(project, case_root)
    if intent == 'follow-up' and not path.is_file():
        index = read(index_path) if index_path.is_file() else {'case_roots': []}
        roots = index.get('case_roots', [])
        if not isinstance(roots, list):
            raise ValueError('Invalid discovery index')
        found = [name for name in roots if _record_path(project, name).is_file()]
        if len(found) != 1:
            return {'status': 'needs-context', 'cases': found, 'case_created': False}
        case_root, path = found[0], _record_path(project, found[0])
    if path.is_file():
        return status(project, case_root)
    if intent == 'follow-up':
        return {'status': 'needs-context', 'cases': [], 'case_created': False}
    if (path.parent / 'case.json').exists():
        raise ValueError('Legacy case is read-only; select a new case or explicit import')
    route = dry_run_route(request, source='local')
    if route['status'] != 'local-route-pass' or route.get('missing_support'):
        return {'status': 'unavailable', 'route': route}
    with locked(index_path):
        with locked(path):
            if path.exists():
                return status(project, case_root)
            case = {'schema_version': 2, 'project_root': str(project), 'case_root': case_root,
                'revision': 0, 'original_request': request, 'objective': intent, 'stage': 'analysis',
                'route': {key: route.get(key) for key in ('primary_id', 'skill', 'required_reads', 'hard_target')},
                'supplements': [], 'features': {}, 'evidence': {}, 'unknowns': {}, 'checks': {}, 'events': []}
            _event(case, 'open', {'request': request})
            write(path, case)
            index = read(index_path) if index_path.exists() else {'schema_version': 2, 'case_roots': []}
            index['case_roots'] = sorted(set([*index['case_roots'], case_root]))
            write(index_path, index)
    return status(project, case_root)


def record(project: Path, case_root: str, change: dict, expected_revision: int):
    project = project.resolve()
    path = _record_path(project, case_root)
    if not isinstance(change, dict) or not isinstance(change.get('op'), str):
        raise ValueError('A structured change operation is required')
    with locked(path):
        case = _load(project, case_root)
        if type(expected_revision) is not int or expected_revision != case['revision']:
            raise ValueError('Stale case revision; reload before applying a change')
        op = change['op']
        if op == 'supplement':
            text = change.get('text')
            if not isinstance(text, str) or not text.strip():
                raise ValueError('Supplement text is required')
            case['supplements'].append(text)
        elif op in {'evidence', 'feature', 'unknown'}:
            identity = change.get('id')
            if (not isinstance(identity, str) or not identity or len(identity) > 80
                    or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in identity)):
                raise ValueError('Record ID must be a portable identifier')
            if op == 'evidence':
                if change.get('authority') not in {'observed', 'static', 'inferred', 'designed', 'native-rea-bundle'}:
                    raise ValueError('Evidence authority must be explicit')
                p = inside(project, change.get('path'))
                if not p.is_file():
                    raise ValueError('Evidence file is missing')
                case['evidence'][identity] = {'path': change['path'], 'sha256': digest(p),
                    'authority': change['authority'], 'description': str(change.get('description', '')),
                    'qualification': 'Host-supplied provenance, not automatic semantic authentication'}
            elif op == 'feature':
                required = {'op', 'id', 'description', 'evidence', 'checks', 'dependencies', 'review'}
                if (set(change) != required or not isinstance(change['description'], str) or not change['description'].strip()
                        or not isinstance(change['review'], str)
                        or any(not isinstance(change[name], list) or any(not isinstance(s, str) for s in change[name])
                               for name in ('evidence', 'checks', 'dependencies'))):
                    raise ValueError('Feature requires description, evidence/check/dependency lists and a semantic review')
                case['features'][identity] = {key: change[key] for key in required - {'op', 'id'}}
            else:
                if (not isinstance(change.get('question'), str) or not change['question'].strip()
                        or type(change.get('critical')) is not bool
                        or not isinstance(change.get('features'), list)
                        or any(s not in case['features'] for s in change['features'])):
                    raise ValueError('Unknown requires a question, critical flag and existing affected features')
                case['unknowns'][identity] = {'question': change['question'], 'critical': change['critical'],
                    'features': change['features'], 'status': 'open', 'resolution_evidence': []}
        elif op == 'resolve':
            identity, refs = change.get('id'), change.get('evidence')
            if (identity not in case['unknowns'] or not isinstance(refs, list) or not refs
                    or any(not _evidence_valid(project, case, ref) for ref in refs)
                    or any(case['evidence'][ref]['authority'] not in {'observed', 'static', 'native-rea-bundle'} for ref in refs)):
                raise ValueError('Resolve needs an existing unknown and fresh qualifying evidence')
            case['unknowns'][identity].update(status='resolved', resolution_evidence=refs)
        else:
            raise ValueError('Unknown change operation; check outcomes are produced only by actual comparison')
        _event(case, op, {key: value for key, value in change.items() if key != 'op'})
        write(path, case)
    return status(project, case_root)


def _readiness(project, case):
    ready, blocked = [], {}
    for identity, feature in case['features'].items():
        reasons = []
        if not feature['evidence'] or any(not _evidence_valid(project, case, ref) for ref in feature['evidence']):
            reasons.append('Missing or stale evidence')
        if not feature['checks']:
            reasons.append('No declared acceptance checks')
        if not feature['review'].strip():
            reasons.append('Semantic review of input/output/state/failure dependencies is missing')
        missing = [s for s in feature['dependencies'] if s not in case['features']]
        if missing:
            reasons.append('Missing dependent features: ' + ', '.join(missing))
        for uid, unknown in case['unknowns'].items():
            still_open = unknown['status'] == 'open' or any(not _evidence_valid(project, case, r) for r in unknown['resolution_evidence'])
            if unknown['critical'] and identity in unknown['features'] and still_open:
                reasons.append('Critical unknown ' + uid)
        if reasons:
            blocked[identity] = reasons
        else:
            ready.append(identity)
    # Propagate only relevant dependencies; a cycle cannot certify itself ready.
    changed = True
    while changed:
        changed = False
        for identity in list(ready):
            if any(dep in blocked for dep in case['features'][identity]['dependencies']):
                ready.remove(identity); blocked[identity] = ['Blocked dependent feature']; changed = True
    def cycle(node, visiting, seen):
        if node in visiting:
            return True
        if node in seen:
            return False
        seen.add(node)
        return any(cycle(dep, visiting | {node}, seen) for dep in case['features'].get(node, {}).get('dependencies', []))
    for identity in list(ready):
        if cycle(identity, set(), set()):
            ready.remove(identity); blocked[identity] = ['Dependency cycle requires review']
    return ready, blocked


def status(project: Path, case_root='work/current-case'):
    project = project.resolve()
    case = _load(project, case_root)
    ready, blocked = _readiness(project, case)
    features = {}
    for identity, feature in case['features'].items():
        checks = {}
        for cid in feature['checks']:
            saved = case['checks'].get(cid)
            outcome = 'not-run'
            if saved:
                try:
                    report = read(inside(project, saved['path']))
                    qualifies = (digest(inside(project, saved['path'])) == saved['sha256']
                        and saved['features'].get(identity) == feature and fresh(project, report))
                    outcome = report['status'] if qualifies else 'stale'
                except (OSError, ValueError, KeyError):
                    outcome = 'stale'
            checks[cid] = outcome
        complete = identity in ready and bool(checks) and all(s == 'pass' for s in checks.values())
        features[identity] = {'description': feature['description'], 'ready': identity in ready,
            'blocked_by': blocked.get(identity, []), 'checks': checks, 'complete': complete}
    complete = bool(features) and all(f['complete'] for f in features.values())
    stage = 'finite-scope-verified' if complete else 'implementation' if ready else 'analysis'
    if complete:
        next_action = 'Review declared coverage against the full goal; unlisted requirements are not automatically verified.'
    elif ready:
        todo = [s for s in ready if not features[s]['complete']]
        next_action = 'Implement/check or refine ready features: ' + ', '.join(todo or ready)
    else:
        next_action = 'Continue evidence gathering and dependency review; preserve the full goal.'
    return {'status': stage, 'case_root': case_root, 'revision': case['revision'],
        'original_request': case['original_request'], 'objective': case['objective'],
        'route': case['route'], 'supplements': case['supplements'], 'features': features,
        'ready_features': ready, 'blocked_features': blocked, 'unknowns': case['unknowns'],
        'next_action': next_action, 'whole_product_acceptance': 'not-established',
        'limitations': ['Readiness checks declared evidence, not automatic semantic understanding.',
            'Completion covers only declared features and actual finite checks.',
            'Host editing is permitted; these records are not an OS write sandbox.']}


def run_check(project: Path, case_root: str, check_id: str, plan: str, output: str):
    project = project.resolve()
    path = _record_path(project, case_root)
    with locked(path):
        before = _load(project, case_root)
        ready, blocked = _readiness(project, before)
        affected = {identity: feature for identity, feature in before['features'].items()
                    if check_id in feature['checks'] and identity in ready}
        if not affected:
            raise ValueError('Check is not declared by a ready feature; inspect affected dependencies')
    result = compare(project, plan, output)
    result_name = output + '/comparison.json'
    with locked(path):
        case = _load(project, case_root)
        if case['revision'] != before['revision']:
            return {'status': 'superseded', 'result': result, 'next_action': 'Reload the changed case; result preserved but not accepted.'}
        case['checks'][check_id] = {'path': result_name, 'sha256': digest(inside(project, result_name)),
            'features': affected, 'status': result['status']}
        _event(case, 'comparison', {'check': check_id, 'result': result_name, 'status': result['status']})
        write(path, case)
    return {'comparison': result, 'workflow': status(project, case_root)}
