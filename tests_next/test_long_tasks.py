"""Long task counterexamples: preserved facts, measured work and candidate identity."""
import json
from pathlib import Path
import sys
import threading
import unittest

from tests_next import test_workflow as fixture
from rea_enhanced.operations import execute
from rea_enhanced.storage import read, write
from rea_enhanced.workflow import record, run_check, status


class LongTasks(unittest.TestCase):
    setUp = fixture.OwnedCase.setUp
    prepare = fixture.OwnedCase.prepare

    def operation(self, **changes):
        return {'op': 'execute', 'id': 'verify-counter', 'kind': 'verify', 'features': ['F1'],
            'argv': [sys.executable, 'work-script.py'], 'inputs': ['work-script.py', 'candidate/app.py'],
            'artifacts': ['operation-result.txt'], 'purpose': 'Check the changed counter behavior',
            'timeout_seconds': 3, **changes}

    def script(self, code="from pathlib import Path\nPath('operation-result.txt').write_text('observed')\n"):
        (self.root / 'work-script.py').write_text(code, encoding='utf-8')

    def run_operation(self, change):
        return execute(self.root, 'work/current-case', change, status(self.root)['revision'])

    def test_overwriting_work_report_keeps_original_observation(self):
        add = self.prepare()
        entry = read(self.root / 'work/current-case/case-v2.json')['evidence']['E1']
        original = (self.root / entry['path']).read_bytes()
        (self.root / 'research.md').write_text('Next build report overwrote the working file', encoding='utf-8')
        self.assertEqual((self.root / entry['path']).read_bytes(), original)
        self.assertTrue(status(self.root)['features']['F1']['ready'])
        add({'op': 'evidence', 'id': 'E2', 'path': 'research.md', 'authority': 'observed'})
        entries = read(self.root / 'work/current-case/case-v2.json')['evidence']
        self.assertNotEqual(entries['E1']['path'], entries['E2']['path'])

    def test_tampered_snapshot_is_not_ready_and_is_named(self):
        self.prepare()
        entry = read(self.root / 'work/current-case/case-v2.json')['evidence']['E1']
        (self.root / entry['path']).write_text('tampered', encoding='utf-8')
        result = status(self.root)
        self.assertFalse(result['features']['F1']['ready'])
        self.assertEqual(result['evidence']['E1']['source_path'], 'research.md')
        self.assertIn('stale-evidence', [d['code'] for d in result['diagnostics']])

    def test_live_specification_still_invalidates_when_it_changes(self):
        add = self.prepare()
        add({'op': 'evidence', 'id': 'E1', 'path': 'research.md', 'authority': 'static', 'retention': 'live'})
        (self.root / 'research.md').write_text('The current specification changed', encoding='utf-8')
        self.assertFalse(status(self.root)['features']['F1']['ready'])

    def test_default_reply_does_not_repeat_saved_qualification_inputs(self):
        add = self.prepare()
        add({'op': 'coverage', 'requirements': [{'id': 'R1', 'source': 'original',
            'text': 'Counter and errors', 'features': ['F1']}], 'review': 'All original wording mapped.'})
        result = status(self.root)
        saved = read(self.root / 'work/current-case/case-v2.json')
        self.assertIn('inputs', saved['coverage'])
        self.assertNotIn('inputs', result['coverage']['review'])

    def test_successful_operation_does_not_certify_product(self):
        self.prepare(); self.script()
        result = self.run_operation(self.operation())
        self.assertEqual(result['operation']['exit_code'], 0)
        self.assertEqual(result['workflow']['operations']['recorded_runs'], 1)
        self.assertFalse(result['workflow']['features']['F1']['complete'])
        self.assertEqual(result['workflow']['features']['F1']['checks']['C1'], 'not-run')
        self.assertTrue((self.root / result['operation']['logs'][0]).is_file())

    def test_unchanged_artifact_operation_is_reused_but_changes_rerun(self):
        self.prepare(); self.script()
        first = self.run_operation(self.operation(reusable=True))
        second = self.run_operation(self.operation(reusable=True))
        self.assertTrue(second['reused'])
        self.assertEqual(first['receipt'], second['receipt'])
        (self.root / 'candidate/app.py').write_text(fixture.CANDIDATE + '\n# new code\n', encoding='utf-8')
        third = self.run_operation(self.operation(reusable=True))
        self.assertFalse(third['reused'])
        self.assertEqual(third['workflow']['operations']['recorded_runs'], 2)

    def test_tampered_artifact_prevents_operation_reuse(self):
        self.prepare(); self.script()
        self.run_operation(self.operation(reusable=True))
        (self.root / 'operation-result.txt').write_text('tampered output', encoding='utf-8')
        self.assertFalse(self.run_operation(self.operation(reusable=True))['reused'])

    def test_unchanged_failure_needs_information_and_has_cross_id_limit(self):
        self.prepare(); self.script('raise SystemExit(2)\n')
        change = self.operation(artifacts=[])
        self.run_operation(change)
        with self.assertRaisesRegex(ValueError, 'new information'):
            self.run_operation(change)
        self.run_operation({**change, 'retry_reason': 'Verified transient external state changed'})
        self.run_operation({**change, 'id': 'renamed-operation', 'retry_reason': 'One explicit final observation'})
        with self.assertRaisesRegex(ValueError, 'Three identical'):
            self.run_operation({**change, 'id': 'another-name', 'retry_reason': 'Repeat'})

    def test_changed_declared_input_is_unknown_even_on_exit_zero(self):
        self.prepare()
        self.script("from pathlib import Path\nPath('candidate/app.py').write_text('changed')\n")
        result = self.run_operation(self.operation(artifacts=[]))
        self.assertEqual(result['operation']['status'], 'unknown')
        self.assertIn('candidate/app.py', result['operation']['changed_inputs'])

    def test_operation_cancellation_keeps_unknown_and_actual_receipt(self):
        self.prepare(); self.script('import time; time.sleep(10)\n')
        event = threading.Event(); timer = threading.Timer(.2, event.set); timer.start()
        try:
            result = execute(self.root, 'work/current-case', self.operation(artifacts=[], timeout_seconds=10),
                             status(self.root)['revision'], cancel_event=event)
        finally:
            timer.join()
        self.assertEqual(result['operation']['status'], 'unknown')
        self.assertTrue((self.root / result['receipt']).is_file())
        self.assertFalse(result['workflow']['features']['F1']['complete'])

    def test_unbound_invoked_script_is_rejected_before_execution(self):
        self.prepare(); self.script()
        with self.assertRaisesRegex(ValueError, 'declared inputs'):
            self.run_operation(self.operation(inputs=['candidate/app.py']))
        self.assertFalse((self.root / 'operation-result.txt').exists())

    def test_external_environment_change_prevents_operation_reuse(self):
        import os
        from unittest.mock import patch
        self.prepare(); self.script()
        change = self.operation(reusable=True, environment_keys=['RF_OWNED_TEST_MODE'])
        with patch.dict(os.environ, {'RF_OWNED_TEST_MODE': 'first'}):
            self.run_operation(change)
        with patch.dict(os.environ, {'RF_OWNED_TEST_MODE': 'second'}):
            self.assertFalse(self.run_operation(change)['reused'])

    def test_accumulated_reports_surface_missing_integration(self):
        add = self.prepare()
        for i in range(12):
            add({'op': 'evidence', 'id': 'E-extra-' + str(i), 'path': 'research.md', 'authority': 'observed'})
        result = add({'op': 'feature', 'id': 'F2', 'description': 'Large mixed feature',
            'evidence': ['E-extra-' + str(i) for i in range(12)], 'checks': ['C2'],
            'dependencies': [], 'review': 'Several unrelated behaviors need decomposition review.'})
        codes = {item['code'] for item in result['diagnostics']}
        self.assertTrue({'evidence-without-integrated-checks', 'review-feature-granularity',
                         'review-acceptance-progress'}.issubset(codes))

    def test_reference_file_cannot_be_declared_as_candidate(self):
        add = self.prepare()
        (self.root / 'candidate/product.exe').write_bytes(b'author release')
        (self.root / 'original/product.exe').write_bytes(b'author release')
        with self.assertRaisesRegex(ValueError, 'reference identity'):
            add({'op': 'product', 'candidate_files': ['candidate/product.exe'],
                 'reference_files': ['original/product.exe'], 'review': 'Distinct candidate intended'})

    def test_product_identity_is_required_after_declaration_and_invalidates_delivery(self):
        add = self.prepare()
        add({'op': 'product', 'candidate_files': ['candidate/app.py'],
             'reference_files': ['original/app.py'], 'review': 'Independent host counter implementation'})
        run_check(self.root, 'work/current-case', 'C1', 'plan.json', 'work/pass')
        add({'op': 'coverage', 'requirements': [{'id': 'R1', 'text': 'Full counter behavior',
            'source': 'original', 'features': ['F1']}], 'review': 'Original request and candidate checked.'})
        with self.assertRaisesRegex(ValueError, 'candidate product'):
            add({'op': 'deliver', 'summary': 'Wrong reference delivery', 'artifacts': ['original/app.py']})
        self.assertEqual(add({'op': 'deliver', 'summary': 'Candidate delivery',
                             'artifacts': ['candidate/app.py']})['delivery']['status'], 'current')
        (self.root / 'candidate/app.py').write_text(fixture.REFERENCE, encoding='utf-8')
        self.assertEqual(status(self.root)['product_identity']['status'], 'stale')
        self.assertEqual(status(self.root)['delivery']['status'], 'stale')


if __name__ == '__main__':
    unittest.main()
