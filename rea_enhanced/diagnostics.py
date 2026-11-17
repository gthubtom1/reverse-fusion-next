"""Small case diagnostics; suggestions never redefine the user's goal."""


def inspect_case(case, features, evidence_state):
    findings = []
    stale = [name for name, valid in evidence_state.items() if not valid]
    if stale:
        findings.append({'code': 'stale-evidence', 'items': stale,
            'action': 'Inspect named dependencies. Preserve observations as snapshots; refresh live dependencies only with new evidence.'})
    starts = [e for e in case['events'] if e['operation'] == 'comparison-start']
    if len(case['evidence']) >= 8 and len(starts) <= 1:
        findings.append({'code': 'evidence-without-integrated-checks',
            'action': 'Reports are evidence, not check results. Compare the next finite behavior with its declared check; keep external observations without inventing pass.'})
    missing = {fid: [cid for cid, outcome in f['checks'].items() if outcome == 'not-run']
               for fid, f in features.items()}
    missing = {fid: checks for fid, checks in missing.items() if checks}
    if missing:
        findings.append({'code': 'unperformed-checks', 'items': missing,
            'action': 'Select a useful independent behavior and its comparison; a whole package build is not required for each backend edit.'})
    oversized = [fid for fid, f in case['features'].items() if len(f['evidence']) >= 12
                 and not features[fid]['complete']]
    if oversized:
        findings.append({'code': 'review-feature-granularity', 'items': oversized,
            'action': 'Consider independent behavior features so one missing service does not hold unrelated work. Preserve all original requirements.'})
    paths = {}
    for identity, evidence in case['evidence'].items():
        if evidence.get('retention', 'live') == 'live':
            paths.setdefault(evidence['path'], []).append(identity)
    shared = {name: ids for name, ids in paths.items() if len(ids) > 1}
    if shared:
        findings.append({'code': 'shared-mutable-evidence', 'items': shared,
            'action': 'Different historical observations need independent snapshots; do not keep replacing a build-current report.'})
    last_check = max((e['revision'] for e in case['events'] if e['operation'] == 'comparison'), default=0)
    since = sum(e['revision'] > last_check and e['operation'] in {'feature', 'evidence', 'operation'}
                for e in case['events'])
    if since >= 12:
        findings.append({'code': 'review-acceptance-progress', 'updates_since_comparison': since,
            'action': 'Check which remaining product behavior changed or which specific unknown was answered. More files, edits, screenshots and test counts alone do not establish progress.'})
    return findings


def validation_guidance(features):
    return {'select_by_change': {
        'backend': 'Run the affected source-level contract or independent replay first.',
        'ui': 'Check changed routes, interactions, full scroll regions and affected viewports; reuse an unchanged reference capture.',
        'package': 'Build at an integration milestone or after packaging/runtime changes, then check the built product.',
        'dependency': 'Investigate the exact unanswered question; block only dependent behavior.'},
        'principle': 'Use the lightest check that answers the current question. Preserve the full final acceptance scope.',
        'host_autonomy': 'The host chooses methods and writes code directly; these records are not a second agent or a fixed tool sequence.',
        'ready': [fid for fid, feature in features.items() if feature['ready'] and not feature['complete']]}


def operation_summary(case):
    completed = [e['detail'] for e in case['events'] if e['operation'] == 'operation']
    completed_receipts = {e.get('receipt') for e in completed}
    incomplete = [e['detail']['output'] for e in case['events'] if e['operation'] == 'operation-start'
                  and e['detail']['output'] + '/operation.json' not in completed_receipts]
    return {'recorded_runs': len(completed),
            'measured_seconds': round(sum(e.get('elapsed_seconds', 0) for e in completed), 3),
            'latest': case.get('operations', {}),
            'incomplete_outputs': incomplete,
            'scope': 'Only commands executed through record execute are measured; native host tools remain available. Exit zero is not acceptance.'}
