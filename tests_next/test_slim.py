"""Real official REA + owned Windows checks in one requirement view; no model calls."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
import uuid
import zipfile
from unittest.mock import patch

from rea_enhanced.comparison import compare, fresh
from rea_enhanced.storage import digest, read, write
from rea_enhanced.workflow import open_case, record, run_check, status
from rea_enhanced.native_verification import ROOT, runtime_identity
from rea_enhanced.providers import environment
from reverse_fusion.mcp_probe import StdioMcp
from reverse_fusion.runtime import node_runtime
from tests_next import test_workflow as fixtures


def native_fixture(project, residual_unknown=False):
    for side in ('original', 'candidate'):
        (project/side).mkdir(exist_ok=True)
    with zipfile.ZipFile(project/'original/data.zip', 'w') as archive:
        archive.writestr('hello.txt', 'Owned asset, not a behavior proof')
    shutil.copyfile(project/'original/data.zip', project/'candidate/data.zip')
    node, _ = node_runtime(ROOT)
    with StdioMcp([node, str(ROOT/'vendor/rea/package/scripts/rea.mjs'), 'mcp'],
                  cwd=ROOT, env=environment(ROOT), timeout=45) as client:
        client.initialize()
        def call(name, args):
            response = client.request('tools/call', {'name': name, 'arguments': args})
            if response.get('isError'):
                raise AssertionError((name, response))
            return response['structuredContent']
        ids = []
        for side in ('original', 'candidate'):
            call('open_binary', {'path': str(project/side/'data.zip')})
            ids.append(call('inspect_artifact', {'integrity_policy': 'fail'})['evidence_id'])
        compared = call('compare_artifacts', {side: {'kind': 'retained-evidence', 'evidence_id': identity}
            for side, identity in zip(('left', 'right'), ids)})
        if residual_unknown:
            call('record_unknown', {'question': 'Unresolved meaning of this structural claim', 'severity': 'high',
                'domain': 'reconstruction',
                'required_authority': None, 'required_confidence': 'observed', 'required_environment': None,
                'recommended_probes': [], 'relationships': [], 'supporting_evidence_ids': ids,
                'contradicting_evidence_ids': []})
        call('export_evidence_bundle', {'path': str(project/'bundle.json'), 'overwrite': False})
    plan = {'version': 2, 'kind': 'rea', 'scope': 'Owned shared asset structure only',
        'bundle': 'bundle.json', 'timeout_seconds': 60,
        'specification': {'name': 'Shared asset', 'claims': [{'claim_id': 'Asset', 'title': 'Declared asset structure',
            'comparison_evidence_id': compared['evidence_id'], 'kind': 'structural-artifact', 'dimension': 'overall'}]},
        **{side: {'cwd': side, 'sources': [side+'/data.zip']} for side in ('original', 'candidate')}}
    write(project/'native-plan.json', plan)
    return plan


class SlimNative(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.plan = native_fixture(self.project)
        open_case(self.project, '分析并复刻这个程序，保留资源和计数行为')

    def add(self, change):
        return record(self.project, 'work/current-case', change, status(self.project)['revision'])

    def requirement(self, identity='R1', checks=None, dimensions=None):
        return self.add({'op': 'requirement', 'id': identity, 'description': 'Shared asset structure',
            'checks': checks or ['N1'], 'dimensions': dimensions or ['structural-artifact:overall'],
            'source': 'original', 'review': 'This requirement concerns only the asset structure, not app behavior.'})

    def test_native_and_owned_in_one_case_without_duplicate_evidence_or_coverage(self):
        # Asset structure and its association with the delivered program are
        # distinct checks; both must belong to this requirement.
        self.requirement(checks=['N1', 'C1'])
        native = run_check(self.project, 'work/current-case', 'N1', 'native-plan.json', 'checks/native')
        self.assertEqual(native['comparison']['status'], 'pass', native)
        self.assertEqual(native['workflow']['features']['R1']['verified_dimensions'], ['structural-artifact:overall'])
        self.assertFalse(native['workflow']['features']['R1']['complete'])
        self.assertEqual(native['workflow']['coverage']['status'], 'current')
        self.assertEqual(read(self.project/'work/current-case/case-v2.json')['evidence'], {})
        for side, code in [('original', fixtures.REFERENCE), ('candidate', fixtures.CANDIDATE)]:
            (self.project/side/'app.py').write_text(code, encoding='utf-8')
        helper = fixtures.OwnedCase(); helper.setUp(); self.addCleanup(helper.doCleanups)
        write(self.project/'process-plan.json', helper.plan)
        self.add({'op': 'requirement', 'id': 'R2', 'description': 'Counter state and errors',
            'checks': ['C1'], 'dimensions': ['process:bounded'], 'source': 'original',
            'review': 'Ordered add/get persistence and invalid input compared against independent reference.'})
        owned = run_check(self.project, 'work/current-case', 'C1', 'process-plan.json', 'checks/process')
        self.assertEqual(owned['comparison']['status'], 'pass')
        self.assertTrue(all(f['complete'] for f in owned['workflow']['features'].values()))
        self.add({'op': 'product', 'candidate_files': ['candidate/app.py'], 'reference_files': ['original/app.py'],
            'review': 'Distinct app code, common data.zip is not product identity.'})
        delivered = self.add({'op': 'deliver', 'summary': 'Declared counter and shared asset; not global equivalence',
            'artifacts': ['candidate/app.py', 'candidate/data.zip']})
        self.assertEqual(delivered['status'], 'reviewed-delivery')
        self.add({'op': 'supplement', 'text': '还要增加服务端错误处理'})
        self.add({'op': 'requirement', 'id': 'R3', 'description': 'Unavailable service errors',
            'checks': ['S1'], 'dimensions': ['process:bounded'], 'source': 'supplement:1',
            'review': 'Service observation is still missing; keep this open.'})
        self.add({'op': 'unknown', 'id': 'U1', 'question': 'Service fixture missing', 'critical': True, 'features': ['R3']})
        stage = self.add({'op': 'deliver_stage', 'features': ['R1', 'R2'], 'summary': 'Counter and assets only; service remains',
            'artifacts': ['candidate/app.py', 'candidate/data.zip']})
        self.assertEqual(stage['status'], 'stage-delivered')
        self.assertEqual(stage['remaining_requirements'], ['R3'])
        self.assertEqual(stage['whole_product_acceptance'], 'not-established')
        self.assertEqual(stage['unknowns']['U1']['status'], 'open')
        self.assertEqual(read(self.project/'work/current-case/case-v2.json').get('coverage'), None)
        exported = {r['evidence_id']: r for r in read(self.project/'checks/native/native-bundle.json')['records']}
        self.assertTrue(all(exported[r['evidence_id']] == r for r in read(self.project/'bundle.json')['records']))
        write(ROOT/'evidence/next/slim/representative-test.json', {
            'status': 'pass', 'native': native['comparison'], 'owned': owned['comparison'],
            'native_response': read(self.project/'checks/native/native-response.json'),
            'native_bundle': read(self.project/'checks/native/native-bundle.json'),
            'stage_delivery': stage, 'scope': 'Owned deterministic asset/counter fixture; original temporary paths retained as historical observations, not reusable current project proof.'})

    def test_native_through_existing_single_mcp_entry_and_original_result_reference(self):
        with StdioMcp([sys.executable, '-m', 'rea_enhanced', 'mcp'], cwd=ROOT, timeout=90) as client:
            client.initialize()
            def call(name, args):
                response = client.request('tools/call', {'name': name, 'arguments': {
                    'project_root': str(self.project), **args}})
                self.assertFalse(response.get('isError'), response)
                return response['structuredContent']
            current = call('rf_next_case_status', {})
            call('rf_next_case_record', {'expected_revision': current['revision'], 'change': {
                'op': 'requirement', 'id': 'R1', 'description': 'Asset structure', 'source': 'original',
                'checks': ['N1'], 'dimensions': ['structural-artifact:overall'], 'review': 'Structure only, not behavior.'}})
            result = call('rf_next_compare', {'check_id': 'N1', 'plan': 'native-plan.json', 'output': 'checks/mcp-native'})
            self.assertEqual(result['status'], 'pass', result)
            self.assertEqual(result['rea_native_proof']['operation'], 'verify_reconstruction')
            self.assertTrue(result['workflow']['features']['R1']['complete'])
        self.assertIn(client.cleanup['status'], ('verified', 'observed'))

    def test_structural_pass_does_not_cover_required_behavior(self):
        self.requirement(dimensions=['behavioral:overall'])
        result = run_check(self.project, 'work/current-case', 'N1', 'native-plan.json', 'checks/native')
        self.assertEqual(result['comparison']['status'], 'pass')
        self.assertFalse(result['workflow']['features']['R1']['complete'])
        self.assertEqual(result['workflow']['features']['R1']['missing_dimensions'], ['behavioral:overall'])

    def test_wrong_candidate_and_missing_selected_subject_not_accepted(self):
        (self.project/'candidate/other.zip').write_bytes((self.project/'candidate/data.zip').read_bytes()+b'other')
        self.plan['candidate']['sources'] = ['candidate/other.zip']
        write(self.project/'native-plan.json', self.plan)
        result = compare(self.project, 'native-plan.json', 'checks/wrong')
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('current candidate identity', result['failure'])

    def test_native_reference_cannot_be_replaced_by_candidate_path(self):
        self.plan['original'] = self.plan['candidate'].copy()
        write(self.project/'native-plan.json', self.plan)
        with self.assertRaisesRegex(ValueError, 'independent paths'):
            compare(self.project, 'native-plan.json', 'checks/replaced-reference')

    def test_forged_bundle_pass_is_rejected_by_official_import(self):
        value = read(self.project/'bundle.json')
        value['records'][-1]['normalized_result']['status'] = 'unchanged'
        value['records'][-1]['limitations'].append('tamper')
        write(self.project/'bundle.json', value)
        result = compare(self.project, 'native-plan.json', 'checks/forged')
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('Official REA import_evidence_bundle', result['failure'])

    def test_native_unknown_remains_native_and_blocks_only_affected_requirement(self):
        (self.project/'bundle.json').unlink()
        native_fixture(self.project, residual_unknown=True)
        self.requirement()
        result = run_check(self.project, 'work/current-case', 'N1', 'native-plan.json', 'checks/unknown')
        self.assertEqual(result['comparison']['status'], 'unknown')
        self.assertTrue(result['comparison']['cases'][0]['native_unknown_ids'])
        self.assertEqual(result['workflow']['features']['R1']['verification_sources']['N1']['native_unknown_ids'],
                         result['comparison']['cases'][0]['native_unknown_ids'])
        self.assertFalse(result['workflow']['features']['R1']['complete'])
        self.assertEqual(result['workflow']['unknowns'], {})
        with self.assertRaises(ValueError):
            self.add({'op': 'resolve', 'id': result['comparison']['cases'][0]['native_unknown_ids'][0], 'evidence': []})

    def test_missing_observation_changed_subject_runtime_or_receipt_invalidates(self):
        self.requirement()
        result = run_check(self.project, 'work/current-case', 'N1', 'native-plan.json', 'checks/native')
        receipt = result['comparison']
        self.assertTrue(fresh(self.project, receipt))
        with patch.dict(os.environ, {'TZ': 'OwnedChangedTimezone'}):
            self.assertFalse(fresh(self.project, receipt))
        with patch('rea_enhanced.native_verification.runtime_identity', return_value={'old': True}):
            self.assertFalse(fresh(self.project, receipt))
        p = self.project/'candidate/data.zip'; old = p.read_bytes(); p.write_bytes(old+b'changed')
        self.assertFalse(fresh(self.project, receipt)); p.write_bytes(old)
        p = self.project/'checks/native/native-response.json'; old = p.read_bytes(); p.unlink()
        self.assertFalse(fresh(self.project, receipt)); p.write_bytes(old)
        p = self.project/'checks/native/comparison.json'; saved = read(p); saved['status'] = 'fail'; write(p, saved)
        self.assertFalse(status(self.project)['features']['R1']['complete'])

    def test_interrupted_native_call_preserves_unknown_and_cleans_owned_process(self):
        event = threading.Event(); event.set()
        result = compare(self.project, 'native-plan.json', 'checks/cancelled', cancel_event=event)
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('cancelled', result['failure'])
        self.assertIn(result['storage']['cleanup']['status'], ('verified', 'observed'))

    def test_supplement_invalidates_coverage_without_discarding_original_requirement(self):
        self.requirement()
        result = self.add({'op': 'supplement', 'text': '增加独立网络错误处理'})
        self.assertEqual(result['coverage']['status'], 'not-reviewed')
        self.assertEqual(result['original_request'], '分析并复刻这个程序，保留资源和计数行为')
        self.assertIn('R1', result['features'])
        self.assertEqual(result['supplements'], ['增加独立网络错误处理'])

    def test_relocation_preserves_wording_but_does_not_rebind_native_pass(self):
        from rea_enhanced.relocation import relocate
        self.requirement()
        run_check(self.project, 'work/current-case', 'N1', 'native-plan.json', 'checks/native')
        with tempfile.TemporaryDirectory() as destination:
            moved = Path(destination)/'copy'; shutil.copytree(self.project, moved)
            before = digest(self.project/'work/current-case/case-v2.json')
            relocate(moved, str(self.project), 'Owned copy relocation test', inactive=True)
            self.assertFalse(status(moved)['features']['R1']['complete'])
            self.assertEqual(status(moved)['original_request'], status(self.project)['original_request'])
            self.assertEqual(digest(self.project/'work/current-case/case-v2.json'), before)
            # Old source subject paths stay intact; a new observation is required for the new project.
            result = compare(moved, 'native-plan.json', 'checks/relocated')
            self.assertEqual(result['status'], 'unknown')


class SlimInstructions(unittest.TestCase):
    def test_public_owned_contract_under_six_kibibytes(self):
        from rea_enhanced.deployment import skill_text
        payload = b''.join((ROOT/name).read_bytes() for name in ('RULES.md', 'docs/AGENT-WORKFLOW.md'))
        payload += skill_text(ROOT).encode('utf-8')
        self.assertLessEqual(len(payload), 6*1024)

    def test_difficult_methods_are_hints_not_mandatory_context(self):
        from reverse_fusion.case_bridge import dry_run_route
        result = dry_run_route('分析APK的反调试和运行时DEX', source='local')
        self.assertEqual(result['required_reads'], ['RULES.md'])
        self.assertIn('skills/apk-reverse/references/high-difficulty-android-playbook.md', result['method_reads'])
        self.assertEqual(result['skill'], 'skills/apk-reverse/SKILL.md')

    def test_old_case_read_is_byte_preserving_and_current_contract_is_projected(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            open_case(project, '分析这个程序')
            path = project/'work/current-case/case-v2.json'
            saved = read(path)
            saved['route']['required_reads'] = ['skills/ops/rea-delegation-contract.md']
            saved['route'].pop('method_reads', None)
            write(path, saved); before = path.read_bytes()
            current = status(project)
            self.assertEqual(current['route']['required_reads'], ['RULES.md'])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(current['status'], 'analysis')

    def test_normal_development_creates_no_case(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(open_case(Path(td), '给普通项目修复分页按钮')['status'], 'host-native')
            self.assertFalse((Path(td)/'work').exists())


if __name__ == '__main__':
    unittest.main()
