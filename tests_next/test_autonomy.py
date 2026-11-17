"""Final-form regression specifications. Added under static-only authorization; not run.

Fixtures are owned observations, not authenticated professional/native proof.
"""
from pathlib import Path
import copy
import tempfile
import unittest
from unittest.mock import patch

from rea_enhanced import workflow
from rea_enhanced.evidence_review import assessment_current
from rea_enhanced.storage import read, write


class AutonomousSupport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, data in [('candidate/app.bin', b'candidate'), ('original/app.bin', b'original'),
                           ('raw/device.txt', b'Owned device observation'), ('spec.txt', b'Reviewed spec')]:
            path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        workflow.open_case(self.root, '分析并复刻这个程序')

    def add(self, change):
        return workflow.record(self.root, 'work/current-case', change, workflow.status(self.root)['revision'])

    def requirement(self, identity='R1', dimension='device:behavior', evaluation='host-review', checks=None):
        return self.add({'op': 'requirement', 'id': identity, 'description': 'Actual declared device behavior',
            'source': 'original', 'checks': checks or [], 'dimensions': [dimension],
            'review': 'Review original wording, observation coverage and failure states', 'evaluation': evaluation})

    def assessment(self, outcome='pass', basis='original-comparison', identity='A1', features=None):
        return {'op': 'assessment', 'id': identity, 'features': features or ['R1'],
            'observations': ['raw/device.txt'], 'candidate_files': ['candidate/app.bin'],
            'reference_files': ['original/app.bin'] if basis == 'original-comparison' else [],
            'input_paths': ['spec.txt'], 'dimensions': ['device:behavior'],
            'producer': 'Owned fixture tool', 'operation': 'Observe candidate and original behavior',
            'context': 'Declared fixture device/environment/version; no claim of current remote state',
            'scope': 'Only the stated device behavior', 'basis': basis, 'outcome': outcome,
            'review': 'Host reviewed actual records; candidate identity and input context match',
            'limitations': ['Finite fixture only; not official Evidence'], 'valid_for_seconds': 3600}

    def product(self, kind='independent-reimplementation'):
        return self.add({'op': 'product', 'kind': kind, 'candidate_files': ['candidate/app.bin'],
            'reference_files': [] if kind == 'specification-implementation' else ['original/app.bin'],
            'review': 'Actual delivery identity files, not common resources'})

    def reviewed(self, kind='independent-reimplementation', scope='full', features=None):
        return {'op': 'deliver_reviewed', 'kind': kind, 'scope': scope, 'features': features or ['R1'],
            'summary': 'Host-reviewed finite device behavior, limitations retained', 'artifacts': ['candidate/app.bin']}

    def test_skip_creates_no_state_even_for_reconstruction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = workflow.open_case(root, '复刻这个APK', recording='skip')
            self.assertEqual(result['status'], 'host-native')
            self.assertFalse((root/'work').exists())
            self.assertFalse((root/'.rea-enhanced').exists())

    def test_explicit_case_can_record_native_development_without_specialist_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = workflow.open_case(root, '增加分页按钮', recording='case')
            self.assertEqual(result['objective'], 'normal-dev')
            self.assertTrue((root/'work/current-case/case-v2.json').exists())

    def test_unavailable_route_is_advisory_not_goal_memory_blocker(self):
        with tempfile.TemporaryDirectory() as td, patch('rea_enhanced.workflow.dry_run_route', return_value={
                'status': 'unavailable', 'missing_support': ['method.md']}):
            result = workflow.open_case(Path(td), '复刻这个APK')
            self.assertEqual(result['route']['status'], 'advisory-unavailable')
            self.assertEqual(result['original_request'], '复刻这个APK')
            self.assertTrue(result['workflow_policy']['host_work_allowed'])

    def test_checkpoint_does_not_require_features_or_grant_completion(self):
        result = self.add({'op': 'checkpoint', 'note': 'Observed startup obstacle; choose method next',
            'next_action': 'Inspect a useful next observation', 'paths': ['raw/device.txt']})
        self.assertTrue(result['checkpoint']['current_files'])
        self.assertFalse(result['features'])
        self.assertEqual(result['whole_product_acceptance'], 'not-established')
        (self.root/'raw/device.txt').write_bytes(b'changed')
        self.assertFalse(workflow.status(self.root)['checkpoint']['current_files'])

    def test_external_review_is_accepted_but_never_an_automatic_check(self):
        self.requirement()
        result = self.add(self.assessment())
        feature = result['features']['R1']
        self.assertTrue(feature['accepted'])
        self.assertTrue(feature['host_reviewed'])
        self.assertFalse(feature['complete'])
        self.assertFalse(feature['verified'])
        self.assertEqual(feature['checks'], {})
        self.assertEqual(read(self.root/'work/current-case/case-v2.json')['checks'], {})
        self.assertEqual(result['status'], 'host-reviewed-scope')

    def test_bare_pass_without_saved_observations_is_rejected(self):
        self.requirement(); value = self.assessment(); value['observations'] = []
        with self.assertRaises(ValueError):
            self.add(value)
        self.assertEqual(workflow.status(self.root)['external_assessments'], {})

    def test_unknown_or_failed_review_does_not_accept(self):
        self.requirement()
        for outcome in ('unknown', 'fail'):
            result = self.add(self.assessment(outcome=outcome))
            self.assertFalse(result['features']['R1']['accepted'])
            self.assertEqual(result['remaining_requirements'], ['R1'])

    def test_expired_failure_is_not_erased_by_time(self):
        self.requirement(); self.add(self.assessment(outcome='fail'))
        saved = read(self.root/'work/current-case/case-v2.json')['assessments']['A1']
        with patch('rea_enhanced.evidence_review.time.time', return_value=saved['reviewed_at']+3601):
            result = workflow.status(self.root)
        self.assertEqual(result['features']['R1']['external_review']['conflicts'], ['A1'])
        self.assertFalse(result['features']['R1']['accepted'])

    def test_candidate_and_specification_changes_stale_review(self):
        self.requirement(); self.add(self.assessment())
        candidate = self.root/'candidate/app.bin'; old = candidate.read_bytes(); candidate.write_bytes(b'changed')
        self.assertFalse(workflow.status(self.root)['features']['R1']['accepted'])
        candidate.write_bytes(old); (self.root/'spec.txt').write_bytes(b'changed spec')
        self.assertFalse(workflow.status(self.root)['features']['R1']['accepted'])

    def test_saved_observation_snapshot_is_immutable_and_expiry_is_explicit(self):
        self.requirement(); self.add(self.assessment())
        (self.root/'raw/device.txt').write_bytes(b'New observation does not rewrite old history')
        self.assertTrue(workflow.status(self.root)['features']['R1']['accepted'])
        case = read(self.root/'work/current-case/case-v2.json'); saved = case['assessments']['A1']
        with patch('rea_enhanced.evidence_review.time.time', return_value=saved['reviewed_at']+3601):
            self.assertFalse(assessment_current(self.root, case, saved))
        (self.root/saved['observations'][0]['path']).write_bytes(b'corrupt')
        self.assertFalse(assessment_current(self.root, case, saved))

    def test_reviewed_delivery_has_distinct_status_and_automatic_remainder(self):
        self.requirement(); self.add(self.assessment()); self.product()
        result = self.add(self.reviewed())
        self.assertEqual(result['status'], 'host-reviewed-delivery')
        self.assertEqual(result['delivery']['status'], 'not-delivered')
        self.assertEqual(result['remaining_requirements'], [])
        self.assertEqual(result['remaining_automatic_verification'], ['R1'])
        self.assertEqual(result['reviewed_delivery']['record']['kind'], 'independent-reimplementation')

    def test_specification_tests_cannot_be_relabelled_original_equivalence(self):
        self.requirement(); self.add(self.assessment(basis='specification')); self.product()
        with self.assertRaises(ValueError):
            self.add(self.reviewed())

    def test_specification_delivery_without_original_has_explicit_kind(self):
        self.requirement()
        self.add({'op': 'output_goal', 'kinds': ['specification-implementation'], 'source': 'original',
            'review': 'Fixture user wording accepts a specification implementation, not original equivalence'})
        self.add(self.assessment(basis='specification')); self.product('specification-implementation')
        result = self.add(self.reviewed(kind='specification-implementation'))
        self.assertEqual(result['reviewed_delivery']['status'], 'current')
        self.assertEqual(result['product_identity']['kind'], 'specification-implementation')
        with self.assertRaises(ValueError):
            self.add({'op': 'deliver', 'summary': 'No automatic relabeling', 'artifacts': ['candidate/app.bin']})

    def test_modified_original_requires_wording_based_agreement(self):
        self.requirement(); self.add(self.assessment()); self.product('modified-original')
        with self.assertRaises(ValueError):
            self.add(self.reviewed(kind='modified-original'))
        self.add({'op': 'output_goal', 'kinds': ['modified-original'], 'source': 'original',
            'review': 'User fixture explicitly accepts modified-original output'})
        result = self.add(self.reviewed(kind='modified-original'))
        self.assertEqual(result['reviewed_delivery']['record']['kind'], 'modified-original')
        self.add({'op': 'supplement', 'text': 'Now also require independent source'})
        self.assertEqual(workflow.status(self.root)['reviewed_delivery']['status'], 'stale')
        self.assertEqual(workflow.status(self.root)['output_goal']['status'], 'stale')

    def test_stage_review_preserves_missing_goal_and_unknown(self):
        self.requirement(); self.requirement('R2')
        self.add({'op': 'unknown', 'id': 'U1', 'question': 'Missing service', 'critical': True, 'features': ['R2']})
        self.add(self.assessment()); self.product()
        result = self.add(self.reviewed(scope='stage'))
        self.assertEqual(result['status'], 'host-reviewed-stage-delivery')
        self.assertEqual(result['remaining_requirements'], ['R2'])
        self.assertEqual(result['unknowns']['U1']['status'], 'open')
        self.assertEqual(result['whole_product_acceptance'], 'not-established')

    def test_other_candidate_observation_cannot_deliver_current_product(self):
        self.requirement(); other = self.root/'candidate/other.bin'; other.write_bytes(b'other')
        value = self.assessment(); value['candidate_files'] = ['candidate/other.bin']; self.add(value); self.product()
        with self.assertRaises(ValueError):
            self.add(self.reviewed())

    def test_unrelated_failed_review_does_not_block_stage_but_dependencies_do(self):
        self.requirement(); self.requirement('R2')
        self.add(self.assessment()); self.add(self.assessment(outcome='fail', identity='A2', features=['R2'])); self.product()
        self.assertEqual(self.add(self.reviewed(scope='stage'))['reviewed_delivery']['status'], 'current')
        self.add({'op': 'feature', 'id': 'R1', 'description': 'Depends on R2', 'evidence': [],
            'checks': [], 'dependencies': ['R2'], 'review': 'Actual dependency'})
        self.assertFalse(workflow.status(self.root)['features']['R1']['accepted'])

    def test_relocation_invalidates_external_review_without_rewriting_proof(self):
        from rea_enhanced.relocation import relocate
        import shutil
        self.requirement(); self.add(self.assessment()); self.product(); self.add(self.reviewed())
        with tempfile.TemporaryDirectory() as td:
            moved = Path(td)/'copy'; shutil.copytree(self.root, moved)
            relocate(moved, str(self.root), 'Owned fixture relocation', inactive=True)
            result = workflow.status(moved)
            self.assertFalse(result['features']['R1']['accepted'])
            self.assertEqual(result['reviewed_delivery']['status'], 'not-delivered')
            self.assertEqual(result['external_assessments']['A1']['review_outcome'], 'pass')
            self.assertFalse(result['external_assessments']['A1']['current'])


if __name__ == '__main__':
    unittest.main()
