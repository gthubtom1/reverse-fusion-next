"""One durable case: goal, evidence, dependent unknowns and finite checks."""
from pathlib import Path
import time
import sys
import re
from reverse_fusion.case_bridge import dry_run_route, request_intent
from .storage import digest, inside, locked, read, write
from .comparison import compare, fresh
from .operations import frozen_evidence, product_record, product_status
from .diagnostics import inspect_case, validation_guidance, operation_summary

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


def _resolution_valid(project, case, unknown):
    refs = unknown.get('resolution_evidence', [])
    return (unknown['status'] == 'resolved' and bool(refs)
        and unknown.get('resolution_snapshot') == {r: case['evidence'].get(r) for r in refs}
        and all(_evidence_valid(project, case, r) and case['evidence'][r]['authority']
                in {'observed', 'static', 'native-rea-bundle'} for r in refs))


def _coverage_inputs(case):
    result = {key:case[key] for key in ('original_request','supplements','objective','features','evidence','unknowns')}
    if case.get('product'):
        result['product'] = case['product']
    return result


def _coverage_valid(case):
    return bool(case.get('coverage')) and case['coverage']['inputs'] == _coverage_inputs(case)


def open_case(project: Path, request: str, case_root='work/current-case'):
    project = project.resolve()
    if not isinstance(request, str) or not request.strip():
        raise ValueError('The original plain-language request is required')
    follow_with_detail = bool(re.match(r'^\s*(?:继续(?:吧|做)?|接着(?:做)?|resume|continue)[，,：:\s]+\S', request, re.I))
    intent = 'follow-up' if follow_with_detail else request_intent(request)
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
        existing = _load(project, case_root)
        if intent == 'follow-up':
            if follow_with_detail and request not in existing['supplements']:
                return record(project, case_root, {'op':'supplement','text':request}, existing['revision'])
            return status(project, case_root)
        if request.strip() == existing['original_request'].strip():
            return status(project, case_root)
        return {'status':'needs-context','case_created':False,'case_root':case_root,
            'original_request':existing['original_request'],'incoming_request':request,
            'next_action':'Different goal received. Select a new case_root for a new target, or explicitly record a supplement to this case.'}
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
                'supplements': [], 'limits':{'max_checks_per_feature':12}, 'features': {}, 'evidence': {}, 'unknowns': {}, 'checks': {}, 'events': []}
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
    if change['op'] == 'execute':
        from .operations import execute
        return execute(project, case_root, change, expected_revision)
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
                retention = change.get('retention', 'snapshot')
                if retention not in {'snapshot', 'live'}:
                    raise ValueError('Evidence retention must be snapshot or live')
                location = (frozen_evidence(project, case_root, change['path']) if retention == 'snapshot'
                            else {'path': change['path'], 'sha256': digest(p), 'retention': 'live'})
                case['evidence'][identity] = {**location,
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
                    'features': change['features'], 'scope':change.get('scope','features'),
                    'status': 'open', 'resolution_evidence': []}
                if change['critical'] and not change['features'] and change.get('scope') != 'case':
                    raise ValueError('Critical unknown requires affected features or explicit scope=case')
        elif op == 'product':
            case['product'] = product_record(project, change)
        elif op == 'refine_route':
            hint=change.get('hint')
            if not isinstance(hint,str) or not hint.strip():raise ValueError('Technical refinement requires a hint')
            route=dry_run_route(hint,source='local',primary=change.get('primary'))
            if route['status']!='local-route-pass' or route.get('missing_support'):
                raise ValueError('Refined domain is unavailable')
            case['route']={key:route.get(key) for key in ('primary_id','skill','required_reads','hard_target')}
        elif op == 'deliver_analysis':
            refs=change.get('evidence');report=inside(project,change.get('report'))
            if not report.is_file() or not isinstance(refs,list) or not refs or any(not _evidence_valid(project,case,r) for r in refs):
                raise ValueError('Analysis delivery needs a saved report and fresh evidence references')
            case['analysis_report']={'path':change['report'],'sha256':digest(report),'evidence':refs,
                'inputs':_coverage_inputs(case)}
        elif op == 'budget':
            amount=change.get('max_checks_per_feature')
            if type(amount) is not int or not 1<=amount<=100 or not isinstance(change.get('reason'),str) or not change['reason'].strip():
                raise ValueError('Budget change needs an explicit 1..100 limit and reason')
            case['limits']={'max_checks_per_feature':amount}
        elif op == 'coverage':
            rows, review = change.get('requirements'), change.get('review')
            sources = {'original', *('supplement:'+str(i+1) for i in range(len(case['supplements'])))}
            if (not isinstance(rows,list) or not rows or not isinstance(review,str) or not review.strip()
                    or any(not isinstance(row,dict) or set(row)!={'id','text','source','features'}
                        or not isinstance(row['id'],str) or not row['id'].strip()
                        or not isinstance(row['text'],str) or not row['text'].strip()
                        or row['source'] not in sources or not isinstance(row['features'],list)
                        or not row['features'] or any(f not in case['features'] for f in row['features']) for row in rows)
                    or len({r['id'] for r in rows})!=len(rows)
                    or {r['source'] for r in rows}!=sources
                    or {f for r in rows for f in r['features']}!=set(case['features'])):
                raise ValueError('Coverage requires unique requirement rows mapping every original/supplement source and every feature, plus semantic review')
            case['coverage']={'requirements':rows,'review':review,'inputs':_coverage_inputs(case),
                'qualification':'Host-reviewed mapping of full wording, not automatic discovery of omitted requirements'}
        elif op == 'deliver':
            current=status(project,case_root)
            artifacts, summary=change.get('artifacts'),change.get('summary')
            if (not _coverage_valid(case) or not current['features']
                    or not all(f['complete'] for f in current['features'].values())
                    or any(not _resolution_valid(project,case,u) for u in case['unknowns'].values())):
                raise ValueError('Delivery requires fresh full-goal coverage, all declared comparisons and resolved unknowns')
            if (not isinstance(summary,str) or not summary.strip() or not isinstance(artifacts,list)
                    or not artifacts or any(not isinstance(p,str) or not inside(project,p).is_file() for p in artifacts)):
                raise ValueError('Delivery requires a summary and existing artifact files')
            if case.get('product'):
                product = product_status(project, case)
                if product['status'] != 'current' or not set(product['candidate_files']).intersection(artifacts):
                    raise ValueError('Delivery needs the current candidate product, not a reference or a changed product identity')
            case['delivery']={'summary':summary,'artifacts':{p:digest(inside(project,p)) for p in artifacts},
                'inputs':_coverage_inputs(case),'checks':case['checks'].copy(),
                'qualification':'Reviewed declared delivery using actual finite comparisons; not universal equivalence'}
        elif op == 'resolve':
            identity, refs = change.get('id'), change.get('evidence')
            if (identity not in case['unknowns'] or not isinstance(refs, list) or not refs
                    or any(not _evidence_valid(project, case, ref) for ref in refs)
                    or any(case['evidence'][ref]['authority'] not in {'observed', 'static', 'native-rea-bundle'} for ref in refs)):
                raise ValueError('Resolve needs an existing unknown and fresh qualifying evidence')
            case['unknowns'][identity].update(status='resolved', resolution_evidence=refs,
                resolution_snapshot={r:case['evidence'][r].copy() for r in refs})
        else:
            raise ValueError('Unknown change operation; check outcomes are produced only by actual comparison')
        _event(case, op, {key: value for key, value in change.items() if key != 'op'})
        write(path, case)
    return status(project, case_root)


def _readiness(project, case, evidence_state=None):
    evidence_state = evidence_state if evidence_state is not None else {
        ref: _evidence_valid(project, case, ref) for ref in case['evidence']}
    ready, blocked = [], {}
    for identity, feature in case['features'].items():
        reasons = []
        if not feature['evidence'] or any(not evidence_state.get(ref, False) for ref in feature['evidence']):
            reasons.append('Missing or stale evidence')
        if not feature['checks']:
            reasons.append('No declared acceptance checks')
        if not feature['review'].strip():
            reasons.append('Semantic review of input/output/state/failure dependencies is missing')
        missing = [s for s in feature['dependencies'] if s not in case['features']]
        if missing:
            reasons.append('Missing dependent features: ' + ', '.join(missing))
        for uid, unknown in case['unknowns'].items():
            still_open = not _resolution_valid(project, case, unknown)
            affected = identity in unknown['features'] or unknown.get('scope') == 'case' or not unknown['features']
            if unknown['critical'] and affected and still_open:
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



def _feature_inputs(case, identity):
    # Flatten shared dependency graphs; nesting each path grows exponentially.
    closure, pending = set(), [identity]
    while pending:
        node=pending.pop()
        if node in closure:continue
        closure.add(node)
        pending.extend(case['features'].get(node,{}).get('dependencies',[]))
    refs={ref for node in closure for ref in case['features'].get(node,{}).get('evidence',[])}
    return {'feature':case['features'][identity],
        'evidence':{ref:case['evidence'].get(ref) for ref in sorted(refs)},
        'dependencies':{ref:case['features'].get(ref) for ref in sorted(closure-{identity})},
        'unknowns':{uid:value for uid,value in case['unknowns'].items()
                    if closure.intersection(value['features']) or value.get('scope')=='case' or not value['features']}}


def status(project: Path, case_root='work/current-case'):
    project = project.resolve()
    case = _load(project, case_root)
    evidence_state = {ref: _evidence_valid(project, case, ref) for ref in case['evidence']}
    ready, blocked = _readiness(project, case, evidence_state)
    features = {}
    for identity, feature in case['features'].items():
        checks = {}
        for cid in feature['checks']:
            saved = case['checks'].get(cid)
            outcome = 'not-run'
            if saved and saved.get('status') in {'running','interrupted'}:
                outcome='incomplete'
            elif saved:
                try:
                    report = read(inside(project, saved['path']))
                    qualifies = (digest(inside(project, saved['path'])) == saved['sha256']
                        and saved.get('inputs',{}).get(identity) == _feature_inputs(case,identity) and fresh(project, report))
                    outcome = report['status'] if qualifies else 'stale'
                except (OSError, ValueError, KeyError):
                    outcome = 'stale'
            checks[cid] = outcome
        complete = identity in ready and bool(checks) and all(s == 'pass' for s in checks.values())
        features[identity] = {'description': feature['description'], 'ready': identity in ready,
            'blocked_by': blocked.get(identity, []), 'checks': checks, 'complete': complete}
    complete = bool(features) and all(f['complete'] for f in features.values())
    stage = 'finite-scope-verified' if complete else 'implementation' if ready else 'analysis'
    analysis_report=case.get('analysis_report')
    if case['objective']=='analysis' and analysis_report:
        try:
            if (digest(inside(project,analysis_report['path']))==analysis_report['sha256']
                    and analysis_report.get('inputs')==_coverage_inputs(case)
                    and all(_evidence_valid(project,case,ref) for ref in analysis_report['evidence'])):
                stage='analysis-delivered'
        except (OSError,ValueError):pass
    if complete:
        next_action = 'Review declared coverage against the full goal; unlisted requirements are not automatically verified.'
    elif ready:
        todo = [s for s in ready if not features[s]['complete']]
        next_action = 'Implement/check or refine ready features: ' + ', '.join(todo or ready)
    else:
        next_action = 'Continue evidence gathering and dependency review; preserve the full goal.'
    coverage = case.get('coverage')
    coverage_state = 'current' if _coverage_valid(case) else 'stale' if coverage else 'not-reviewed'
    delivery = case.get('delivery')
    delivery_valid = False
    if delivery and complete and coverage_state=='current':
        try:
            delivery_valid = (delivery['inputs']==_coverage_inputs(case) and delivery['checks']==case['checks']
                and all(digest(inside(project,p))==sha for p,sha in delivery['artifacts'].items())
                and all(_resolution_valid(project,case,u) for u in case['unknowns'].values())
                and (not case.get('product') or product_status(project, case)['status'] == 'current'))
        except (OSError,ValueError):pass
    if delivery_valid:
        stage='reviewed-delivery'
        next_action='Deliver saved artifacts with finite tested scope and coverage review; preserve remaining external limitations.'
    def brief(value):
        return {k: v for k, v in value.items() if k not in {'inputs', 'checks'}} if value else value
    return {'status': stage, 'case_root': case_root, 'revision': case['revision'],
        'original_request': case['original_request'], 'objective': case['objective'],
        'route':{**case['route'],'required_read_paths':[str(ROOT/name) for name in case['route'].get('required_reads',[])]},
        'component_entries':{'official_rea_skill':str(ROOT/'vendor/rea/package/skills/reverse-engineer-anything/SKILL.md'),
            'enhanced_cli':[sys.executable,str(ROOT/'scripts/next-cli.py')],'writer':'current-host-native',
            'mcp_server':'reverse-fusion-rea','craft_required':False,'spec_required':False},
        'analysis_report':brief(analysis_report),'supplements': case['supplements'], 'features': features,
        'ready_features': ready, 'blocked_features': blocked,
        'unknowns': {uid: {k: v for k, v in u.items() if k != 'resolution_snapshot'} for uid, u in case['unknowns'].items()},
        'check_budget':case.get('limits',{'max_checks_per_feature':12}),
        'coverage':{'status':coverage_state,'review':brief(coverage)},
        'delivery':{'status':'current' if delivery_valid else 'stale' if delivery else 'not-delivered','record':brief(delivery)},
        'product_identity': product_status(project, case),
        'diagnostics': inspect_case(case, features, evidence_state),
        'validation_guidance': validation_guidance(features),
        'operations': operation_summary(case),
        'evidence': {ref: {'path': e['path'], 'source_path': e.get('source_path', e['path']),
                         'retention': e.get('retention', 'live'), 'current': evidence_state[ref]}
                     for ref, e in case['evidence'].items() if not evidence_state[ref]},
        'next_action': next_action, 'whole_product_acceptance': 'host-reviewed-declared-delivery' if delivery_valid else 'not-established',
        'limitations': ['Readiness checks declared evidence, not automatic semantic understanding.',
            'Completion covers only declared features and actual finite checks.',
            'Host editing is permitted; these records are not an OS write sandbox.']}



def run_check(project: Path, case_root: str, check_id: str, plan: str, output: str, cancel_event=None, retry_reason=None):
    project=project.resolve()
    if retry_reason is not None and (not isinstance(retry_reason,str) or not retry_reason.strip() or len(retry_reason)>2000):
        raise ValueError('Retry reason must describe concrete new information')
    if not isinstance(check_id,str) or not check_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in check_id):
        raise ValueError('Check ID must be a portable identifier')
    path=_record_path(project,case_root)
    run_lock=inside(project,case_root+'/checks/'+check_id+'.json')
    with locked(run_lock):
        with locked(path):
            before=_load(project,case_root)
            ready,blocked=_readiness(project,before)
            affected={identity:feature for identity,feature in before['features'].items()
                      if check_id in feature['checks'] and identity in ready}
            if not affected:
                raise ValueError('Check is not declared by a ready feature; inspect affected dependencies')
            previous=before['checks'].get(check_id)
            if previous and previous.get('path'):
                try:
                    old=read(inside(project,previous['path']))
                    unchanged=(digest(inside(project,previous['path']))==previous.get('sha256')
                        and old.get('plan')==plan and fresh(project,old)
                        and all(previous.get('inputs',{}).get(identity)==_feature_inputs(before,identity) for identity in affected))
                except (ValueError,OSError,KeyError):unchanged=False
                if unchanged and old['status']=='pass':
                    return {'comparison':old,'workflow':status(project,case_root),'reused':True,
                            'receipt_path':previous['path']}
                if unchanged and old['status'] in {'fail','unknown'} and not retry_reason:
                    raise ValueError('Unchanged unsuccessful comparison: revise candidate/evidence or record a concrete retry reason')
            attempts=sum(e['operation']=='comparison-start' and e['detail'].get('check')==check_id for e in before['events'])
            if attempts>=before.get('limits',{}).get('max_checks_per_feature',12):
                raise ValueError('Check budget exhausted; revisit investigation or record a justified budget change')
            before['checks'][check_id]={'status':'running','features':affected,
                'inputs':{identity:_feature_inputs(before,identity) for identity in affected}}
            _event(before,'comparison-start',{'check':check_id,'plan':plan,'output':output,
                'retry_reason':retry_reason,'scope':'Marker is incomplete, not proof a process is still live'})
            write(path,before)
        try:
            result=compare(project,plan,output,cancel_event=cancel_event)
        except (OSError,ValueError) as exc:
            with locked(path):
                case=_load(project,case_root)
                case['checks'][check_id]={'status':'interrupted','reason':str(exc)}
                _event(case,'comparison-error',{'check':check_id,'reason':str(exc)})
                write(path,case)
            raise
        result_name=output+'/comparison.json'
        with locked(path):
            case=_load(project,case_root)
            if case['revision']!=before['revision']:
                case['checks'][check_id]={'status':'interrupted','result':result_name,'reason':'Case changed during comparison'}
                _event(case,'comparison-superseded',{'check':check_id,'result':result_name})
                write(path,case)
                return {'status':'superseded','result':result,
                    'next_action':'Reload changed case; old result preserved but not accepted.'}
            case['checks'][check_id]={'path':result_name,'sha256':digest(inside(project,result_name)),
                'features':affected,'inputs':{identity:_feature_inputs(before,identity) for identity in affected},
                'status':result['status']}
            _event(case,'comparison',{'check':check_id,'result':result_name,'status':result['status']})
            write(path,case)
        return {'comparison':result,'workflow':status(project,case_root),'receipt_path':result_name}
