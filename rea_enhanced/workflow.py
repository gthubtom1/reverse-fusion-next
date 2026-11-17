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
    if case.get('output_goal'):
        result['output_goal'] = case['output_goal']
    return result


def _automatic_output_kind(case):
    return 'independent-reimplementation' if case['objective'] == 'reconstruction' else 'analysis-report'


def _automatic_output_allowed(case, saved=None):
    from .evidence_review import output_goal
    return (saved or {}).get('kind', _automatic_output_kind(case)) in output_goal(case)['kinds']


def _coverage_valid(case):
    if case.get('coverage'):
        return case['coverage']['inputs'] == _coverage_inputs(case)
    features = case['features']
    sources = {'original', *('supplement:'+str(i+1) for i in range(len(case['supplements'])))}
    return bool(features) and all(f.get('requirement_source') in sources and f['review'].strip()
                                  for f in features.values()) and {f['requirement_source'] for f in features.values()} == sources


def _delivery_product_valid(project, case, artifacts, selected=None):
    if case['objective'] != 'reconstruction' and not case.get('product'):
        return True
    if product_status(project, case)['status'] != 'current':
        return False
    product = case['product']
    if product.get('kind', 'independent-reimplementation') != 'independent-reimplementation':
        return False
    if not set(product['candidate_files']).issubset(artifacts):
        return False
    required = set(case['features'] if selected is None else selected)
    pending = list(required)
    while pending:
        identity = pending.pop()
        if identity not in case['features']:
            return False
        for dependency in case['features'][identity]['dependencies']:
            if dependency not in required:
                required.add(dependency)
                pending.append(dependency)
    for identity in required:
        covered = {'candidate': {}, 'original': {}}
        for cid in case['features'][identity]['checks']:
            check = case['checks'].get(cid, {})
            if not check.get('path'):
                continue
            try:
                path = inside(project, check['path'])
                receipt = read(path)
                if (digest(path) != check.get('sha256') or receipt.get('status') != 'pass'
                        or check.get('inputs', {}).get(identity) != _feature_inputs(case, identity)
                        or not fresh(project, receipt)):
                    continue
                compared = {side: {tree['cwd']+'/'+name: checksum for name, checksum in tree['files'].items()}
                            for side, tree in receipt['input_trees'].items() if side in covered}
                # Only credit product files from a receipt that actually pairs a
                # current candidate identity with a current reference identity.
                if not all(any(compared.get(side, {}).get(name) == checksum
                               for name, checksum in product[key].items())
                           for side, key in (('candidate', 'candidate_files'), ('original', 'reference_files'))):
                    continue
                for side in covered:
                    covered[side].update(compared[side])
            except (OSError, ValueError, KeyError, TypeError):
                continue
        if not all(covered[side].get(name) == checksum
                   for side, key in (('candidate', 'candidate_files'), ('original', 'reference_files'))
                   for name, checksum in product[key].items()):
            return False
    return bool(required)


def open_case(project: Path, request: str, case_root='work/current-case', recording='auto'):
    project = project.resolve()
    if not isinstance(request, str) or not request.strip():
        raise ValueError('The original plain-language request is required')
    follow_with_detail = bool(re.match(r'^\s*(?:继续(?:吧|做)?|接着(?:做)?|resume|continue)[，,：:\s]+\S', request, re.I))
    intent = 'follow-up' if follow_with_detail else request_intent(request)
    index_path = inside(project, '.rea-enhanced/cases.json')
    if recording not in {'auto', 'case', 'skip'}:
        raise ValueError('recording must be auto, case or skip')
    if recording == 'skip' or intent == 'normal-dev' and recording != 'case':
        return {'status': 'host-native', 'request': request, 'case_created': False,
            'recording': recording, 'guidance': 'Use native tools and existing reliable task records; no case or owned checker is required.'}
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
    route_available = route.get('status') == 'local-route-pass' and not route.get('missing_support')
    with locked(index_path):
        with locked(path):
            if path.exists():
                return status(project, case_root)
            case = {'schema_version': 2, 'project_root': str(project), 'case_root': case_root,
                'revision': 0, 'original_request': request, 'objective': intent, 'stage': 'analysis',
                'route': {**{key: route.get(key) for key in ('primary_id', 'skill', 'required_reads', 'hard_target', 'method_reads')},
                    'status': 'advisory' if route_available else 'advisory-unavailable',
                    'missing_support': route.get('missing_support', []),
                    'required_reads': route.get('required_reads') or [], 'method_reads': route.get('method_reads') or []},
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
        elif op == 'checkpoint':
            from .operations import file_identities
            if (set(change)-{'op', 'note', 'next_action', 'paths'}
                    or not isinstance(change.get('note'), str) or not change['note'].strip()
                    or not isinstance(change.get('next_action'), str) or not change['next_action'].strip()):
                raise ValueError('Checkpoint needs a progress note and host-selected next action')
            case['checkpoint'] = {'note': change['note'], 'next_action': change['next_action'],
                'files': file_identities(project, change.get('paths', [])),
                'qualification': 'Resumable host note; no automatic verification or mandatory phase transition'}
        elif op == 'output_goal':
            from .evidence_review import output_goal
            case['output_goal'] = output_goal(case, change)
        elif op == 'assessment':
            from .evidence_review import record_assessment
            identity, assessment = record_assessment(project, case_root, case, change)
            case.setdefault('assessments', {})[identity] = assessment
        elif op in {'evidence', 'feature', 'requirement', 'unknown'}:
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
            elif op == 'requirement':
                required = {'op', 'id', 'description', 'checks', 'dimensions', 'source', 'review'}
                sources = {'original', *('supplement:'+str(i+1) for i in range(len(case['supplements'])))}
                evaluation = change.get('evaluation', case['features'].get(identity, {}).get('evaluation', 'automatic'))
                if (set(change)-{'evaluation'} != required or change['source'] not in sources
                        or evaluation not in {'automatic', 'host-review'}
                        or any(not isinstance(change[k], str) or not change[k].strip() for k in ('description', 'review'))
                        or any(not isinstance(change[k], list) or (not change[k] and (k == 'dimensions' or evaluation == 'automatic'))
                               or any(not isinstance(s, str) or not s.strip() for s in change[k]) for k in ('checks', 'dimensions'))
                        or any(d not in {'process:bounded', 'web:declared-behavior', 'web:pixels',
                            'behavioral:overall', 'behavioral:terminal', 'behavioral:interaction', 'behavioral:exit',
                            'behavioral:filesystem', 'behavioral:process', 'structural-artifact:overall',
                            *('structural-function:'+s for s in ('overall','identity','pseudocode','assembly','comments','calls','references','strings_names','cfg'))}
                               and not (evaluation == 'host-review' and re.fullmatch(r'[a-z][a-z0-9-]*:[a-z][a-z0-9_-]*', d))
                               for d in change['dimensions'])):
                    raise ValueError('Requirement needs original/supplement source, reviewed description, checks and explicit supported dimensions')
                previous = case['features'].get(identity, {})
                if set(previous.get('dimensions', [])) - set(change['dimensions']):
                    raise ValueError('Updating a requirement must retain its established verification dimensions')
                if previous.get('requirement_source', change['source']) != change['source']:
                    raise ValueError('Keep the original wording source when updating an existing requirement')
                case['features'][identity] = {**previous,
                    'description': change['description'], 'checks': change['checks'],
                    'evidence': previous.get('evidence', []), 'dependencies': previous.get('dependencies', []),
                    'review': change['review'], 'requirement_source': change['source'], 'dimensions': change['dimensions'],
                    'evaluation': evaluation}
                case.pop('coverage', None)
            elif op == 'feature':
                required = {'op', 'id', 'description', 'evidence', 'checks', 'dependencies', 'review'}
                if (set(change) != required or not isinstance(change['description'], str) or not change['description'].strip()
                        or not isinstance(change['review'], str)
                        or any(not isinstance(change[name], list) or any(not isinstance(s, str) for s in change[name])
                               for name in ('evidence', 'checks', 'dependencies'))):
                    raise ValueError('Feature requires description, evidence/check/dependency lists and a semantic review')
                previous = case['features'].get(identity, {})
                case['features'][identity] = {**previous, **{key: change[key] for key in required - {'op', 'id'}}}
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
            case['route']={key:route.get(key) for key in ('primary_id','skill','required_reads','hard_target','method_reads')}
            case['route']['refinement_hint'] = hint
        elif op == 'deliver_analysis':
            # An interim analysis report never replaces a reconstruction goal.
            refs=change.get('evidence');report=inside(project,change.get('report'))
            if not report.is_file() or not isinstance(refs,list) or not refs or any(not _evidence_valid(project,case,r) for r in refs):
                raise ValueError('Analysis delivery needs a saved report and fresh evidence references')
            case['analysis_report']={'path':change['report'],'sha256':digest(report),'evidence':refs,
                'inputs':_coverage_inputs(case)}
        elif op == 'budget':
            limits = {key: change[key] for key in ('max_checks_per_feature', 'max_operation_failures') if key in change}
            if (not limits or any(type(n) is not int or not 1<=n<=100 for n in limits.values())
                    or not isinstance(change.get('reason'),str) or not change['reason'].strip()):
                raise ValueError('Budget change needs an explicit 1..100 limit and reason')
            case['limits'].update(limits)
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
        elif op == 'deliver_reviewed':
            from .evidence_review import review_delivery_valid, wording
            from .operations import file_identities
            required = {'op', 'kind', 'scope', 'features', 'summary', 'artifacts'}
            selected = change.get('features')
            if (set(change) != required or change['scope'] not in {'full', 'stage'}
                    or not isinstance(selected, list) or not selected
                    or any(not isinstance(f, str) or f not in case['features'] for f in selected)
                    or len(set(selected)) != len(selected)
                    or not isinstance(change['summary'], str) or not change['summary'].strip()):
                raise ValueError('Reviewed delivery needs an explicit kind, full/stage scope, selected requirements and summary')
            current = status(project, case_root)
            closure, pending = set(selected), list(selected)
            while pending:
                for dependency in case['features'][pending.pop()]['dependencies']:
                    if dependency not in case['features']:
                        raise ValueError('Reviewed delivery has a missing dependency')
                    if dependency not in closure:
                        closure.add(dependency); pending.append(dependency)
            artifacts = file_identities(project, change['artifacts'])
            if not artifacts:
                raise ValueError('Reviewed delivery needs existing artifact files')
            assessment_ids = {aid for f in closure for aid in current['features'][f]['external_review']['assessment_ids']}
            saved = {'kind': change['kind'], 'scope': change['scope'], 'features': selected[:],
                'summary': change['summary'], 'artifacts': artifacts,
                'wording': wording(case), 'output_goal': case.get('output_goal'), 'product': case.get('product'),
                'inputs': {f: _feature_inputs(case, f) for f in closure},
                'assessments': {aid: case['assessments'][aid] for aid in assessment_ids},
                'qualification': 'Explicit host-reviewed delivery; not an automatic check pass or official REA proof'}
            if not review_delivery_valid(project, case, current['features'], saved):
                raise ValueError('Reviewed delivery lacks current in-scope evidence, allowed output kind, candidate binding or required coverage')
            case['reviewed_delivery'] = saved
        elif op == 'deliver_stage':
            current = status(project, case_root)
            selected, artifacts, summary = change.get('features'), change.get('artifacts'), change.get('summary')
            if (not isinstance(selected, list) or not selected
                    or any(f not in current['features'] or not current['features'][f]['complete'] or not current['features'][f]['accepted'] for f in selected)
                    or not isinstance(summary, str) or not summary.strip()
                    or not isinstance(artifacts, list) or not artifacts
                    or any(not isinstance(p, str) or not inside(project, p).is_file() for p in artifacts)
                    or not _automatic_output_allowed(case)
                    or not _delivery_product_valid(project, case, artifacts, selected)):
                raise ValueError('Stage delivery needs verified selected requirements and current compared candidate artifacts')
            case['stage_delivery'] = {'summary': summary, 'features': selected, 'kind': _automatic_output_kind(case),
                'artifacts': {p: digest(inside(project, p)) for p in artifacts},
                'inputs': {f: _feature_inputs(case, f) for f in selected},
                'qualification': 'Selected stage only; original wording, supplements and remaining requirements stay open'}
        elif op == 'deliver':
            current=status(project,case_root)
            artifacts, summary=change.get('artifacts'),change.get('summary')
            if (not _coverage_valid(case) or not current['features']
                    or not all(f['complete'] and f['accepted'] for f in current['features'].values())
                    or any(not _resolution_valid(project,case,u) for u in case['unknowns'].values())):
                raise ValueError('Delivery requires fresh full-goal coverage, all declared comparisons and resolved unknowns')
            if (not isinstance(summary,str) or not summary.strip() or not isinstance(artifacts,list)
                    or not artifacts or any(not isinstance(p,str) or not inside(project,p).is_file() for p in artifacts)):
                raise ValueError('Delivery requires a summary and existing artifact files')
            if not _automatic_output_allowed(case) or not _delivery_product_valid(project, case, artifacts):
                raise ValueError('Delivery needs the current compared candidate product identity and its files, not a reference or untested artifact')
            case['delivery']={'summary':summary,'kind':_automatic_output_kind(case),'artifacts':{p:digest(inside(project,p)) for p in artifacts},
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
        detail = ({'id': identity, 'assessment': assessment} if op == 'assessment'
                  else {key: value for key, value in change.items() if key != 'op'})
        _event(case, op, detail)
        write(path, case)
    return status(project, case_root)


def _readiness(project, case, evidence_state=None):
    evidence_state = evidence_state if evidence_state is not None else {
        ref: _evidence_valid(project, case, ref) for ref in case['evidence']}
    ready, blocked = [], {}
    for identity, feature in case['features'].items():
        reasons = []
        if ((not feature['evidence'] and not feature.get('requirement_source'))
                or any(not evidence_state.get(ref, False) for ref in feature['evidence'])):
            reasons.append('Missing or stale evidence')
        if not feature['checks'] and feature.get('evaluation', 'automatic') != 'host-review':
            reasons.append('No declared automatic acceptance checks; external evidence can use explicit host-review evaluation')
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
    from .evidence_review import assessment_views, feature_review, output_goal, review_delivery_valid
    external_assessments = assessment_views(project, case)
    features = {}
    for identity, feature in case['features'].items():
        checks, observed_dimensions, verification_sources = {}, set(), {}
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
                    from .native_verification import dimensions
                    verification_sources[cid] = {'path': saved['path'], 'current': qualifies,
                        'operation': report.get('operation'), 'dimensions': dimensions(report),
                        'native_result': report.get('rea_native_proof', 'not-performed'),
                        'native_unknown_ids': sorted({uid for row in report.get('cases', [])
                                                      for uid in row.get('native_unknown_ids', [])})}
                    if qualifies and outcome == 'pass':
                        observed_dimensions.update(dimensions(report))
                except (OSError, ValueError, KeyError):
                    outcome = 'stale'
            checks[cid] = outcome
        missing_dimensions = sorted(set(feature.get('dimensions', []))-observed_dimensions)
        complete = identity in ready and bool(checks) and all(s == 'pass' for s in checks.values()) and not missing_dimensions
        external = feature_review(case, identity, external_assessments, checks, observed_dimensions)
        accepted = identity in ready and not external['conflicts'] and (complete or external['supported'])
        features[identity] = {'description': feature['description'], 'ready': identity in ready,
            'evaluation': feature.get('evaluation', 'automatic'), 'accepted': accepted,
            'external_review': external, 'host_reviewed': accepted and external['supported'],
            'blocked_by': blocked.get(identity, []), 'checks': checks, 'complete': complete,
            'verified_dimensions': sorted(observed_dimensions), 'missing_dimensions': missing_dimensions,
            'observed': (bool(feature['evidence']) and all(evidence_state.get(r, False) for r in feature['evidence']))
                        or any(s['current'] for s in verification_sources.values())
                        or any(v['current'] and identity in v['features'] for v in external_assessments.values()),
            'verification_sources': verification_sources, 'verified': complete}
    # A reviewed child cannot close a dependent requirement whose own dependency
    # has a conflicting or missing review, even when structural readiness is true.
    changed = True
    while changed:
        changed = False
        for identity, view in features.items():
            if view['accepted'] and any(not features[d]['accepted'] for d in case['features'][identity]['dependencies']):
                view['accepted'] = False
                view['host_reviewed'] = False
                view['blocked_by'] = [*view['blocked_by'], 'Dependent requirement is not accepted']
                changed = True
    # External reviews never rewrite checks or the legacy automatic-complete bit.
    complete = bool(features) and all(f['complete'] and f['accepted'] for f in features.values())
    all_accepted = bool(features) and all(f['accepted'] for f in features.values())
    stage = 'finite-scope-verified' if complete else 'implementation' if ready else 'analysis'
    analysis_report=case.get('analysis_report')
    if case['objective']=='analysis' and analysis_report and 'analysis-report' in output_goal(case)['kinds']:
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
        next_action = 'Choose the next useful investigation or implementation from actual gaps; readiness only describes acceptance.'
    if all_accepted and not complete:
        stage = 'host-reviewed-scope'
        next_action = 'Review the agreed output, current artifact identities and remaining goal; external review is not an automatic pass.'
    coverage = case.get('coverage')
    coverage_state = 'current' if _coverage_valid(case) else 'stale' if coverage else 'not-reviewed'
    delivery = case.get('delivery')
    delivery_valid = False
    if delivery and complete and coverage_state=='current':
        try:
            delivery_valid = (delivery['inputs']==_coverage_inputs(case) and delivery['checks']==case['checks']
                and all(digest(inside(project,p))==sha for p,sha in delivery['artifacts'].items())
                and all(_resolution_valid(project,case,u) for u in case['unknowns'].values())
                and _automatic_output_allowed(case, delivery)
                and _delivery_product_valid(project, case, delivery['artifacts']))
        except (OSError,ValueError):pass
    if delivery_valid:
        stage='reviewed-delivery'
        next_action='Deliver saved artifacts with finite tested scope and coverage review; preserve remaining external limitations.'
    partial = case.get('stage_delivery')
    partial_valid = False
    if partial:
        try:
            partial_valid = (all(features[f]['complete'] and features[f]['accepted'] and partial['inputs'][f] == _feature_inputs(case, f)
                                 for f in partial['features'])
                and all(digest(inside(project, p)) == checksum for p, checksum in partial['artifacts'].items())
                and _automatic_output_allowed(case, partial)
                and _delivery_product_valid(project, case, partial['artifacts'], partial['features']))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if partial_valid and not delivery_valid:
        stage = 'stage-delivered'
        next_action = 'Selected stage saved; continue remaining requirements and review unmapped wording/supplements.'
    reviewed_delivery = case.get('reviewed_delivery')
    reviewed_valid = bool(reviewed_delivery) and review_delivery_valid(project, case, features, reviewed_delivery)
    if reviewed_valid and not delivery_valid:
        stage = 'host-reviewed-delivery' if reviewed_delivery['scope'] == 'full' else 'host-reviewed-stage-delivery'
        next_action = 'Present the explicit output kind, host-reviewed evidence and remaining scope; no automatic/native proof is implied.'
    checkpoint = case.get('checkpoint')
    checkpoint_current = False
    if checkpoint:
        try:
            checkpoint_current = all(digest(inside(project, p)) == h for p, h in checkpoint['files'].items())
        except (OSError, ValueError, KeyError, TypeError):
            pass
    # Old saved route reads are projected through the current short contract without rewriting the case.
    route = dict(case['route'])
    context = dry_run_route(route.get('refinement_hint', case['original_request']), source='local', primary=route.get('primary_id'))
    if route.get('refinement_hint') or not route.get('method_reads'):
        route.update({k: context[k] for k in ('required_reads', 'method_reads', 'hard_target') if k in context})
    elif 'required_reads' in context:
        route['required_reads'] = context['required_reads']
    def brief(value):
        return {k: v for k, v in value.items() if k not in {'inputs', 'checks'}} if value else value
    from .disk import summary as storage_summary
    return {'status': stage, 'case_root': case_root, 'revision': case['revision'],
        'original_request': case['original_request'], 'objective': case['objective'],
        'route':{**route,'required_read_paths':[str(ROOT/name) for name in route.get('required_reads',[])]},
        'component_entries':{'official_rea_skill':str(ROOT/'vendor/rea/package/skills/reverse-engineer-anything/SKILL.md'),
            'enhanced_cli':[sys.executable,str(ROOT/'scripts/next-cli.py')],'writer':'current-host-native',
            'mcp_server':'reverse-fusion-rea','craft_required':False,'spec_required':False},
        'analysis_report':brief(analysis_report),'supplements': case['supplements'], 'features': features,
        'workflow_policy': {'recording': 'optional; reuse reliable host records', 'method_order': 'host-selected, evidence-driven',
            'host_work_allowed': True, 'readiness_scope': 'acceptance diagnostics only, not investigation/editing permission',
            'external_results': 'explicit host review separate from automatic/native proof'},
        'checkpoint': {'current_files': checkpoint_current, 'record': checkpoint},
        'output_goal': output_goal(case), 'external_assessments': external_assessments,
        'ready_features': ready, 'blocked_features': blocked,
        'unknowns': {uid: {k: v for k, v in u.items() if k != 'resolution_snapshot'} for uid, u in case['unknowns'].items()},
        'check_budget':case.get('limits',{'max_checks_per_feature':12}),
        'coverage':{'status':coverage_state,'review':brief(coverage),
            'requirements': [{'id': identity, 'text': feature['description'], 'source': feature['requirement_source']}
                for identity, feature in case['features'].items() if feature.get('requirement_source')],
            'qualification': 'Host-reviewed wording mapping; no automatic discovery of omitted user intent'},
        'delivery':{'status':'current' if delivery_valid else 'stale' if delivery else 'not-delivered','record':brief(delivery)},
        'stage_delivery': {'status': 'current' if partial_valid else 'stale' if partial else 'not-delivered', 'record': brief(partial)},
        'reviewed_delivery': {'status': 'current' if reviewed_valid else 'stale' if reviewed_delivery else 'not-delivered',
            'record': {k: v for k, v in reviewed_delivery.items() if k not in {'inputs', 'assessments', 'wording', 'output_goal', 'product'}} if reviewed_delivery else None},
        'remaining_requirements': [identity for identity, feature in features.items() if not feature['accepted']],
        'remaining_automatic_verification': [identity for identity, feature in features.items() if not feature['complete']],
        'product_identity': product_status(project, case),
        'diagnostics': inspect_case(case, features, evidence_state),
        'validation_guidance': validation_guidance(features),
        'operations': operation_summary(case),
        'storage': storage_summary(project),
        'evidence': {ref: {'path': e['path'], 'source_path': e.get('source_path', e['path']),
                         'retention': e.get('retention', 'live'), 'current': evidence_state[ref]}
                     for ref, e in case['evidence'].items() if not evidence_state[ref]},
        'next_action': next_action, 'whole_product_acceptance': ('host-reviewed-declared-delivery' if delivery_valid
            else 'host-reviewed-external-delivery' if reviewed_valid and reviewed_delivery['scope'] == 'full' else 'not-established'),
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
            import uuid
            run_id = uuid.uuid4().hex
            before['checks'][check_id]={'status':'running','run_id':run_id,'features':affected,
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
            current_ready, _ = _readiness(project, case)
            if (case['checks'].get(check_id, {}).get('run_id') != run_id
                    or any(identity not in current_ready
                           or before['checks'][check_id]['inputs'][identity] != _feature_inputs(case, identity)
                           for identity in affected)
                    or result.get('status') == 'pass' and not fresh(project, result)):
                case['checks'][check_id]={'status':'interrupted','result':result_name,'reason':'Affected inputs or running check changed during comparison'}
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
