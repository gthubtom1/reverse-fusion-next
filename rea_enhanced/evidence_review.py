"""Explicit host review of external observations, separate from automatic/native proof.

This module checks saved identities and review scope. It does not authenticate an
arbitrary tool format, infer behavior from filenames, or manufacture check passes.
"""
import re
import time
from .storage import digest, inside
from .operations import file_identities, frozen_evidence, identifier, product_status

OUTPUT_KINDS = {'analysis-report', 'independent-reimplementation',
                'specification-implementation', 'modified-original'}
BASES = {'original-comparison', 'specification', 'observation'}
DIMENSION = re.compile(r'^[a-z][a-z0-9-]*:[a-z][a-z0-9_-]*$')


def wording(case):
    return {'original_request': case['original_request'], 'supplements': case['supplements'][:]}


def output_goal(case, change=None):
    if change is not None:
        if (set(change) != {'op', 'kinds', 'source', 'review'}
                or not isinstance(change['kinds'], list) or not change['kinds']
                or any(not isinstance(k, str) or k not in OUTPUT_KINDS for k in change['kinds'])
                or len(set(change['kinds'])) != len(change['kinds'])
                or change['source'] not in {'original', *('supplement:'+str(i+1) for i in range(len(case['supplements'])))}
                or not isinstance(change['review'], str) or not change['review'].strip()):
            raise ValueError('Output goal needs explicit kinds, original/supplement source and wording-based review')
        return {'kinds': change['kinds'], 'source': change['source'], 'review': change['review'],
            'inputs': wording(case), 'qualification': 'Host mapping of user agreement; not automatic authorization or intent inference'}
    saved = case.get('output_goal')
    if saved:
        current = saved.get('inputs') == wording(case)
        return {'status': 'current' if current else 'stale', 'kinds': saved['kinds'] if current else [],
            'source': saved['source'], 'review': saved['review'], 'qualification': saved['qualification']}
    kind = 'independent-reimplementation' if case['objective'] == 'reconstruction' else 'analysis-report'
    return {'status': 'implicit-default', 'kinds': [kind], 'source': 'original',
        'qualification': 'Conservative legacy default; other deliverable types require an explicit wording-based output_goal'}


def record_assessment(project, case_root, case, change):
    from .workflow import _feature_inputs
    required = {'op', 'id', 'features', 'observations', 'candidate_files', 'reference_files',
                'input_paths', 'dimensions', 'producer', 'operation', 'context', 'scope',
                'basis', 'outcome', 'review', 'limitations', 'valid_for_seconds'}
    if set(change) != required:
        raise ValueError('External assessment requires observations, identities, scope, context and a bounded explicit host review')
    identity = identifier(change['id'])
    features = change['features']
    if (not isinstance(features, list) or not features or len(set(features)) != len(features)
            or any(not isinstance(f, str) or f not in case['features'] for f in features)):
        raise ValueError('Assessment must name existing affected requirements')
    for key in ('producer', 'operation', 'context', 'scope', 'review'):
        if not isinstance(change[key], str) or not change[key].strip():
            raise ValueError('Assessment '+key+' must describe actual source and reviewed scope')
    if change['basis'] not in BASES or change['outcome'] not in {'pass', 'fail', 'unknown'}:
        raise ValueError('Assessment basis/outcome must remain explicit')
    dimensions, limits = change['dimensions'], change['limitations']
    if (not isinstance(dimensions, list) or not dimensions or len(dimensions) > 50
            or any(not isinstance(d, str) or not DIMENSION.fullmatch(d) for d in dimensions)
            or not isinstance(limits, list) or not limits
            or any(not isinstance(s, str) or not s.strip() for s in limits)
            or type(change['valid_for_seconds']) is not int or not 1 <= change['valid_for_seconds'] <= 86400):
        raise ValueError('Review needs dimensions, limitations and a 1..86400 second freshness window')
    observations = change['observations']
    if (not isinstance(observations, list) or not 1 <= len(observations) <= 50
            or any(not isinstance(p, str) for p in observations) or len(set(observations)) != len(observations)):
        raise ValueError('Save 1..50 raw observation files; a bare outcome is not evidence')
    candidates = file_identities(project, change['candidate_files'])
    references = file_identities(project, change['reference_files'])
    inputs = file_identities(project, change['input_paths'])
    if set(candidates) & set(references) or set(candidates.values()) & set(references.values()):
        raise ValueError('Candidate and reference identities must remain distinct')
    if change['basis'] == 'original-comparison' and (not candidates or not references):
        raise ValueError('Original comparison review needs both product identities')
    if change['basis'] == 'specification' and (not candidates or not inputs):
        raise ValueError('Specification review needs candidate and live specification/input identities')
    # Preflight the full list before snapshotting. Observations are source material,
    # not claimed native proof; their semantic association is explicitly host-reviewed.
    for name in observations:
        p = inside(project, name)
        if not p.is_file() or p.stat().st_size > 64*1024*1024:
            raise ValueError('Observation must be a saved file no larger than 64 MiB')
    return identity, {'producer': change['producer'], 'operation': change['operation'],
        'context': change['context'], 'scope': change['scope'], 'basis': change['basis'],
        'review_outcome': change['outcome'], 'review': change['review'], 'limitations': limits,
        'dimensions': sorted(set(dimensions)), 'features': features[:],
        'observations': [frozen_evidence(project, case_root, name) for name in observations],
        'candidate_files': candidates, 'reference_files': references, 'input_files': inputs,
        'inputs': {f: _feature_inputs(case, f) for f in features}, 'reviewed_at': time.time(),
        'valid_for_seconds': change['valid_for_seconds'],
        'qualification': 'host-reviewed-external; no automatic pass or official REA proof',
        'semantic_source_authentication': 'Host-reviewed, not authenticated by this adapter',
        'external_state': 'Recorded observation context only; freshness window does not prove a live service/device is unchanged'}


def assessment_current(project, case, saved):
    from .workflow import _feature_inputs
    try:
        if saved.get('invalidated'):
            return False
        age = time.time()-saved['reviewed_at']
        if not 0 <= age <= saved['valid_for_seconds']:
            return False
        if any(f not in case['features'] or saved['inputs'][f] != _feature_inputs(case, f) for f in saved['features']):
            return False
        for key in ('candidate_files', 'reference_files', 'input_files'):
            if any(digest(inside(project, name)) != checksum for name, checksum in saved[key].items()):
                return False
        return bool(saved['observations']) and all(
            digest(inside(project, item['path'])) == item['sha256'] for item in saved['observations'])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def assessment_views(project, case):
    return {identity: {'current': assessment_current(project, case, saved),
        **{k: saved[k] for k in ('producer', 'operation', 'scope', 'basis', 'review_outcome',
            'dimensions', 'features', 'limitations', 'qualification', 'reviewed_at', 'valid_for_seconds')}}
        for identity, saved in case.get('assessments', {}).items()}


def feature_review(case, identity, current_views, checks, automatic_dimensions):
    feature = case['features'][identity]
    applicable = {key: value for key, value in current_views.items() if identity in value['features']}
    active = {key: value for key, value in applicable.items() if value['current']}
    dimensions = set(automatic_dimensions)
    for value in active.values():
        if value['review_outcome'] == 'pass':
            dimensions.update(value['dimensions'])
    missing = sorted(set(feature.get('dimensions', []))-dimensions)
    # Expiry never erases an observed failure/unknown. Reassess that same entry
    # with new evidence rather than letting an old automatic pass reappear.
    conflicts = [key for key, value in applicable.items() if value['review_outcome'] != 'pass']
    supported = (feature.get('evaluation', 'automatic') == 'host-review' and bool(active)
        and not conflicts and not missing and bool(feature.get('dimensions'))
        and all(outcome == 'pass' for outcome in checks.values()))
    return {'supported': supported, 'assessment_ids': sorted(active),
        'reported_dimensions': sorted(dimensions), 'missing_dimensions': missing,
        'conflicts': conflicts, 'unadapted_external_evidence': bool(applicable),
        'qualification': 'Host semantic review, separate from automatic verification'}


def review_delivery_valid(project, case, current, saved):
    from .workflow import _coverage_valid, _delivery_product_valid, _feature_inputs, _resolution_valid
    try:
        selected = saved['features']
        if (saved['kind'] not in output_goal(case)['kinds'] or saved['wording'] != wording(case)
                or saved['output_goal'] != case.get('output_goal')
                or saved['product'] != case.get('product') or not selected
                or saved['artifacts'] != file_identities(project, list(saved['artifacts']))):
            return False
        if saved['scope'] == 'full' and (set(selected) != set(case['features']) or not _coverage_valid(case)):
            return False
        closure, pending = set(), list(selected)
        while pending:
            identity = pending.pop()
            if identity in closure:
                continue
            closure.add(identity)
            pending.extend(case['features'][identity]['dependencies'])
        if any(not current[f]['accepted'] or saved['inputs'].get(f) != _feature_inputs(case, f) for f in closure):
            return False
        for unknown in case['unknowns'].values():
            if (saved['scope'] == 'full' or unknown.get('scope') == 'case'
                    or closure.intersection(unknown['features'])) and not _resolution_valid(project, case, unknown):
                return False
        candidate_required = saved['kind'] != 'analysis-report'
        if candidate_required:
            if product_status(project, case)['status'] != 'current':
                return False
            product = case['product']
            if product.get('kind', 'independent-reimplementation') != saved['kind']:
                return False
            if not set(product['candidate_files']).issubset(saved['artifacts']):
                return False
        else:
            product = None
        for identity in closure:
            paired_automatic = candidate_required and _delivery_product_valid(project, case, saved['artifacts'], [identity])
            if paired_automatic and current[identity]['complete']:
                continue
            matched = {'candidate_files': {}, 'reference_files': {}}
            covered = set(current[identity]['verified_dimensions']) if paired_automatic else set()
            if paired_automatic:
                matched = {side: dict(product[side]) for side in matched}
            for aid in current[identity]['external_review']['assessment_ids']:
                item = case['assessments'][aid]
                if saved['assessments'].get(aid) != item or not assessment_current(project, case, item) or item['review_outcome'] != 'pass':
                    return False
                if saved['kind'] == 'independent-reimplementation' and item['basis'] != 'original-comparison':
                    continue
                if saved['kind'] == 'specification-implementation' and item['basis'] != 'specification':
                    continue
                if saved['kind'] == 'modified-original' and item['basis'] != 'original-comparison':
                    continue
                if product:
                    if not all(product['candidate_files'].get(n) == h for n, h in item['candidate_files'].items()):
                        continue
                    if item['basis'] == 'original-comparison' and not all(
                            product['reference_files'].get(n) == h for n, h in item['reference_files'].items()):
                        continue
                    if not item['candidate_files']:
                        continue
                covered.update(item['dimensions'])
                for side in matched:
                    matched[side].update(item[side])
            if not set(case['features'][identity].get('dimensions', [])) <= covered:
                return False
            if not covered:
                return False
            if product:
                if any(matched['candidate_files'].get(n) != h for n, h in product['candidate_files'].items()):
                    return False
                if saved['kind'] == 'independent-reimplementation' and any(
                        matched['reference_files'].get(n) != h for n, h in product['reference_files'].items()):
                    return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
