"""Regression specifications for the static-only recheck; NOT executed in that stage.

These mock-adapter/temporary-record tests are not native Evidence or live proof.
They are kept for a future explicitly chosen engineering run.
"""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

from rea_enhanced import workflow, comparison, deployment, relocation, web, server
from rea_enhanced.storage import read, write, digest
from rea_enhanced.native_verification import bind_claims
from reverse_fusion.case_bridge import request_intent


class StaticRecheckRegressions(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        workflow.open_case(self.project, '分析并复刻这个程序')

    def add(self, change):
        return workflow.record(self.project, 'work/current-case', change,
                               workflow.status(self.project)['revision'])

    def requirement(self, identity, checks, dimensions=None):
        return self.add({'op': 'requirement', 'id': identity, 'description': identity,
            'checks': checks, 'dimensions': dimensions or ['process:bounded'],
            'source': 'original', 'review': 'Finite reviewed requirement'})

    def test_cross_interface_updates_retain_dependencies_and_dimensions(self):
        self.requirement('F2', ['C2'])
        self.add({'op': 'feature', 'id': 'F1', 'description': 'Dependent',
            'evidence': [], 'checks': ['C1'], 'dependencies': ['F2'], 'review': 'Depends on F2'})
        self.add({'op': 'unknown', 'id': 'U1', 'question': 'Missing dependency',
            'critical': True, 'features': ['F2']})
        self.requirement('F1', ['C1'], ['behavioral:overall'])
        case = read(self.project/'work/current-case/case-v2.json')
        self.assertEqual(case['features']['F1']['dependencies'], ['F2'])
        self.assertFalse(workflow.status(self.project)['features']['F1']['ready'])
        self.add({'op': 'feature', 'id': 'F1', 'description': 'Add evidence via legacy interface',
            'evidence': [], 'checks': ['C1'], 'dependencies': ['F2'], 'review': 'Same behavior'})
        case = read(self.project/'work/current-case/case-v2.json')
        self.assertEqual(case['features']['F1']['dimensions'], ['behavioral:overall'])
        self.assertEqual(case['features']['F1']['requirement_source'], 'original')
        with self.assertRaises(ValueError):
            self.requirement('F1', ['C1'], ['structural-artifact:overall'])

    def make_product_case(self):
        for name in ('oa/app.bin', 'ca/app.bin', 'ob/app.bin', 'cb/app.bin'):
            p = self.project/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(name.encode())
        self.requirement('A', ['CA']); self.requirement('B', ['CB'])
        case = read(self.project/'work/current-case/case-v2.json')
        for identity, cid, original, candidate in [('A', 'CA', 'oa', 'ca'), ('B', 'CB', 'ob', 'cb')]:
            receipt = {'status': 'pass', 'input_trees': {
                'original': {'cwd': original, 'files': {'app.bin': digest(self.project/original/'app.bin')}},
                'candidate': {'cwd': candidate, 'files': {'app.bin': digest(self.project/candidate/'app.bin')}}}}
            path = cid+'.json'; write(self.project/path, receipt)
            case['checks'][cid] = {'path': path, 'sha256': digest(self.project/path),
                'features': [identity], 'inputs': {identity: workflow._feature_inputs(case, identity)}}
        case['product'] = {'candidate_files': {'cb/app.bin': digest(self.project/'cb/app.bin')},
            'reference_files': {'ob/app.bin': digest(self.project/'ob/app.bin')}, 'review': 'B product'}
        return case

    def test_stage_cannot_borrow_other_product_check(self):
        case = self.make_product_case()
        with patch('rea_enhanced.workflow.fresh', return_value=True):
            self.assertFalse(workflow._delivery_product_valid(self.project, case, ['cb/app.bin'], ['A']))
            self.assertTrue(workflow._delivery_product_valid(self.project, case, ['cb/app.bin'], ['B']))
            self.assertFalse(workflow._delivery_product_valid(self.project, case, ['cb/app.bin']))

    def test_unrelated_missing_receipt_does_not_break_selected_product(self):
        case = self.make_product_case()
        (self.project/'CA.json').unlink()
        with patch('rea_enhanced.workflow.fresh', return_value=True):
            self.assertTrue(workflow._delivery_product_valid(self.project, case, ['cb/app.bin'], ['B']))

    def test_unrelated_case_revision_does_not_supersede_check(self):
        self.requirement('R1', ['C1'])
        def observed(project, plan, output, cancel_event=None):
            self.requirement('R2', ['C2'])
            result = {'status': 'pass', 'operation': 'independent-finite-replay', 'plan': plan, 'cases': []}
            write(project/output/'comparison.json', result)
            return result
        with patch('rea_enhanced.workflow.compare', side_effect=observed), patch('rea_enhanced.workflow.fresh', return_value=True):
            result = workflow.run_check(self.project, 'work/current-case', 'C1', 'p.json', 'result')
        self.assertEqual(result['comparison']['status'], 'pass')
        self.assertTrue(result['workflow']['features']['R1']['complete'])
        self.assertFalse(result['workflow']['features']['R2']['complete'])

    def test_refinement_hint_survives_status_projection(self):
        self.add({'op': 'refine_route', 'hint': '发现APK动态DEX和反调试'})
        current = workflow.status(self.project)
        self.assertTrue(current['route']['hard_target'])
        self.assertIn('skills/apk-reverse/references/high-difficulty-android-playbook.md', current['route']['method_reads'])

    def test_uninstall_accepts_authentic_previous_skill_but_not_user_edit(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            deployment.install(deployment.ROOT, home, check=False)
            render = deployment.skill_text
            with patch('rea_enhanced.deployment.skill_text', side_effect=lambda root: render(root)+'\nNew owned version\n'):
                self.assertEqual(deployment.uninstall(deployment.ROOT, home)['status'], 'uninstalled')

    def test_malformed_owned_change_returns_validation_error(self):
        for change in (None, [], 'feature'):
            with self.subTest(change=change), self.assertRaises(ValueError):
                server.call_owned('rf_next_case_record', {'project_root': str(self.project),
                    'change': change, 'expected_revision': 1})

    def test_connection_fingerprint_covers_loaded_helpers(self):
        identity = server.connection_identity()
        for name in ('reverse_fusion/owned_process.py', 'reverse_fusion/mcp_probe.py',
                     'components/reverse-core/router.py', 'components/reverse-core/runtime.json'):
            self.assertIn(name, identity)

    def test_interpreter_early_exit_is_not_execution_of_declared_source(self):
        script = self.project/'app.py'; script.write_text('print("target")', encoding='utf-8')
        with self.assertRaises(ValueError):
            comparison.replay_entry([sys.executable, '--version', 'app.py'], self.project, {script})
        self.assertEqual(comparison.replay_entry([sys.executable, '-I', 'app.py'], self.project, {script}), script)

    def test_executable_resolution_prefers_exact_local_identity(self):
        target = self.project/'run.exe'; target.write_bytes(b'owned fixture; never executed')
        with patch('rea_enhanced.comparison.shutil.which', return_value='elsewhere/run.exe'):
            self.assertEqual(comparison.replay_executable(['run.exe'], self.project), target)

    def test_native_capture_null_subject_binds_only_committed_executable(self):
        bindings = {}; records = []; claim = {'kind': 'behavioral', 'left_evidence_ids': ['L'], 'right_evidence_ids': ['R']}
        for side, identity in [('original', 'L'), ('candidate', 'R')]:
            p = self.project/side/'program.exe'; p.parent.mkdir(); p.write_bytes(side.encode())
            checksum = digest(p)
            bindings[side] = {'cwd': side, 'files': {'program.exe': checksum}}
            records.append({'evidence_id': identity, 'operation': 'capture_process_scenario', 'subject': None,
                'normalized_result': {'manifest': {'scenario': {'executable': str(p), 'executable_sha256': checksum},
                    'selected_executable_sha256': checksum, 'executable_sha256': checksum,
                    'executable_identity': {'state': 'path_metadata_unchanged'},
                    'full_scenario_sha256': 'a'*64, 'comparison_contract_sha256': 'b'*64}}})
        bind_claims(self.project, {'records': records}, [claim], bindings)
        broken = copy.deepcopy(records); broken[1]['normalized_result']['manifest']['executable_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            bind_claims(self.project, {'records': broken}, [claim], bindings)

    def test_large_case_relocation_preserves_compact_backups(self):
        self.add({'op': 'supplement', 'text': 'x'*(8*1024*1024)})
        with tempfile.TemporaryDirectory() as td:
            import shutil
            moved = Path(td)/'copy'; shutil.copytree(self.project, moved)
            result = relocation.relocate(moved, str(self.project), 'Owned relocation fixture', inactive=True)
            saved = read(Path(result['receipt']))
            raw = saved['originals']['work/current-case/case-v2.json']
            self.assertIn('$rf_record', raw['supplements'][0])

    def test_relocation_final_receipt_failure_restores_case(self):
        with tempfile.TemporaryDirectory() as td:
            import shutil
            moved = Path(td)/'copy'; shutil.copytree(self.project, moved)
            path = moved/'work/current-case/case-v2.json'; before = path.read_bytes()
            real_write = relocation.write
            def fail_terminal(target, value):
                if value.get('status') == 'relocated':
                    raise OSError('Injected terminal receipt failure')
                return real_write(target, value)
            with patch('rea_enhanced.relocation.write', side_effect=fail_terminal), self.assertRaises(OSError):
                relocation.relocate(moved, str(self.project), 'Owned failure fixture', inactive=True)
            self.assertEqual(path.read_bytes(), before)

    def test_rollback_final_receipt_failure_restores_installed_entries(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td); result = deployment.install(deployment.ROOT, home, check=False)
            paths = deployment._paths(home); before = {k: p.read_bytes() for k, p in paths.items()}
            real_write = deployment.write
            def fail_terminal(target, value):
                if value.get('status') == 'rolled-back':
                    raise OSError('Injected terminal rollback receipt failure')
                return real_write(target, value)
            with patch('rea_enhanced.deployment.write', side_effect=fail_terminal), self.assertRaises(OSError):
                deployment.rollback(result['rollback_receipt'], deployment.ROOT)
            self.assertEqual({k: p.read_bytes() for k, p in paths.items()}, before)

    def test_intent_does_not_misclassify_firmware_or_packaging(self):
        self.assertEqual(request_intent('分析这个固件的启动流程'), 'analysis')
        self.assertEqual(request_intent('为项目增加 app.exe 的打包任务'), 'normal-dev')
        self.assertEqual(request_intent('分析这个软件源代码的架构'), 'normal-dev')

    def test_large_legal_output_is_externalized_and_freshness_checks_it(self):
        from tests_next import test_workflow as fixture
        helper = fixture.OwnedCase(); helper.setUp(); self.addCleanup(helper.doCleanups)
        plan = helper.plan
        plan['scenarios'] = [{'id': 'large', 'steps': [
            {'stdin': '', 'args': [], 'files': [], 'expected_exit_codes': [0]} for _ in range(7)]}]
        write(helper.root/'plan.json', plan)
        observed = {'status': 'observed', 'exit_code': 0, 'stdout': b'x'*(1024*1024), 'stderr': b''}
        with patch('rea_enhanced.comparison.run_owned', side_effect=lambda *a, **k: observed.copy()):
            result = comparison.compare(helper.root, 'plan.json', 'large-result')
        self.assertEqual(result['status'], 'pass')
        self.assertLess((helper.root/'large-result/comparison.json').stat().st_size, 1024*1024)
        channel = result['cases'][0]['observations']['original']['stdout']
        self.assertEqual(channel['bytes'], 1024*1024)
        self.assertTrue(comparison.fresh(helper.root, result))
        (helper.root/channel['snapshot']).unlink()
        self.assertFalse(comparison.fresh(helper.root, result))

    def test_web_runtime_change_invalidates_saved_result(self):
        from tests_next.test_web import WebComparison
        helper = WebComparison(); helper.setUp(); self.addCleanup(helper.doCleanups)
        saved = {'operation': 'independent-web-replay', 'engine': {'fixture': True},
            'plan': 'plan.json', 'plan_sha256': digest(helper.root/'plan.json'),
            'input_trees': {}, 'web_runtime': {'old': True}}
        with patch('rea_enhanced.comparison.engine_identity', return_value={'fixture': True}), \
             patch('rea_enhanced.web.web_runtime_identity', return_value={'new': True}):
            self.assertFalse(comparison.fresh(helper.root, saved))


if __name__ == '__main__':
    unittest.main()
