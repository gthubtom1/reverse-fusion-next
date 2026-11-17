"""Regression cases for the nine independent audit findings, not another review."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rea_enhanced import disk
from rea_enhanced.comparison import compare, fresh
from rea_enhanced.deployment import install, rollback, _paths
from rea_enhanced.operations import execute
from rea_enhanced.providers import environment, providers
from rea_enhanced.relocation import relocate
from rea_enhanced.storage import digest, locked, read, write
from rea_enhanced.workflow import open_case, record, run_check, status
from tests_next import test_workflow as fixture
from tests_next import test_web

ROOT = Path(__file__).resolve().parents[1]


class CaseRepairs(unittest.TestCase):
    prepare = fixture.OwnedCase.prepare

    def setUp(self):
        fixture.OwnedCase.setUp(self)
        self.environment = patch.dict(os.environ, {'RF_NEXT_DISK_STATE': str(self.root/'coordinator')})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def coverage(self, add):
        return add({'op':'coverage','requirements':[{'id':'R1','text':'Counter and errors',
            'source':'original','features':['F1']}],'review':'Original wording reviewed'})

    def test_delivery_requires_identity_and_compared_artifacts(self):
        add = self.prepare()
        run_check(self.root, 'work/current-case', 'C1', 'plan.json', 'work/pass')
        self.coverage(add)
        with self.assertRaisesRegex(ValueError, 'candidate product'):
            add({'op':'deliver','summary':'Wrong original','artifacts':['original/app.py']})
        (self.root/'untested.py').write_text('print("unrelated")')
        add({'op':'product','candidate_files':['untested.py'],'reference_files':['original/app.py'],
             'review':'Unrelated file must not satisfy the compared product'})
        self.coverage(add)
        with self.assertRaisesRegex(ValueError, 'candidate product'):
            add({'op':'deliver','summary':'Untested candidate','artifacts':['untested.py']})
        add({'op':'product','candidate_files':['candidate/app.py'],'reference_files':['original/app.py'],
             'review':'Actual independent implementations'})
        self.coverage(add)
        result = add({'op':'deliver','summary':'Compared candidate','artifacts':['candidate/app.py']})
        self.assertEqual(result['status'], 'reviewed-delivery')

    def test_successful_nonreusable_observations_can_repeat(self):
        self.prepare()
        (self.root/'observe.py').write_text('print("observation")\n')
        for _ in range(5):
            result = execute(self.root, 'work/current-case', {'op':'execute','id':'observe','kind':'verify',
                'features':['F1'],'argv':[sys.executable,'observe.py'],'inputs':['observe.py'],
                'purpose':'Observe external state','reusable':False}, status(self.root)['revision'])
            self.assertEqual(result['operation']['status'], 'observed')
            self.assertFalse(result['reused'])

    def test_failed_operations_have_a_reasoned_adjustable_budget(self):
        add = self.prepare()
        (self.root/'fail.py').write_text('raise SystemExit(2)\n')
        change = {'op':'execute','id':'fail','kind':'verify','features':['F1'],
                  'argv':[sys.executable,'fail.py'],'inputs':['fail.py'],'purpose':'Observe failure'}
        execute(self.root, 'work/current-case', change, status(self.root)['revision'])
        with self.assertRaisesRegex(ValueError, 'new information'):
            execute(self.root, 'work/current-case', change, status(self.root)['revision'])
        for _ in range(2):
            execute(self.root, 'work/current-case', {**change,'retry_reason':'New external observation'}, status(self.root)['revision'])
        with self.assertRaisesRegex(ValueError, 'budget'):
            execute(self.root, 'work/current-case', {**change,'retry_reason':'One more'}, status(self.root)['revision'])
        add({'op':'budget','max_operation_failures':4,'reason':'One verified external recovery to investigate'})
        execute(self.root, 'work/current-case', {**change,'retry_reason':'Recovery observed'}, status(self.root)['revision'])

    def test_used_cache_can_retire_but_active_lease_is_protected(self):
        self.prepare()
        allocation = disk.allocate(self.root, 'Cached script', 'Regenerate script', disk.MiB,
            tier='reusable', reuse_key='script-v1', reuse_reason='Next batch', input_paths=[])
        area = Path(allocation['path'])
        script = allocation['relative_path']+'/verify.py'
        (area/'verify.py').write_text('print("observed")\n')
        execute(self.root, 'work/current-case', {'op':'execute','id':'verify','kind':'verify','features':['F1'],
            'argv':[sys.executable,script],'inputs':[script],'purpose':'Use cached script'}, status(self.root)['revision'])
        disk.complete(self.root, allocation['id'])
        decision = [{'id':allocation['id'],'decision':'release','reason':'All uses complete'}]
        with disk.using_paths(self.root, [script]):
            result = disk.review(self.root, 'task-end', decision)
            self.assertEqual(result['review']['decisions'][0]['outcome'], 'retained')
        result = disk.review(self.root, 'task-end', decision)
        self.assertEqual(result['review']['decisions'][0]['outcome'], 'reclaimed')
        self.assertFalse(area.exists())

    def test_legacy_explicit_protection_can_retire_without_overriding_evidence(self):
        self.prepare()
        allocation = disk.allocate(self.root, 'Disposable', 'Recreate', disk.MiB)
        disk.protect(self.root, [allocation['relative_path']])
        disk.complete(self.root, allocation['id'])
        self.assertTrue(Path(allocation['path']).exists())
        disk.dispatch(self.root, 'unprotect', paths=[allocation['relative_path']])
        disk.review(self.root, 'task-end')
        self.assertFalse(Path(allocation['path']).exists())

    def test_large_supplement_and_events_are_sharded_and_readable(self):
        add = self.prepare()
        text = 'x'*(8*1024*1024)
        result = add({'op':'supplement','text':text})
        path = self.root/'work/current-case/case-v2.json'
        raw = json.loads(path.read_text())
        self.assertLess(path.stat().st_size, 65536)
        self.assertIn('$rf_record', raw['events'][-1])
        self.assertIn('$rf_record', raw['supplements'][-1])
        self.assertEqual(result['supplements'][-1], text)
        self.assertEqual(read(path)['events'][-1]['detail']['text'], text)

    def test_relocation_cli_is_available(self):
        result = subprocess.run([sys.executable, str(ROOT/'scripts/next-cli.py'), 'relocate', '--help'],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'--from-root', result.stdout)
        self.assertIn(b'--inactive', result.stdout)

    def test_oversized_metadata_preserves_previous_readable_record(self):
        self.prepare()
        path = self.root/'record.json'
        write(path, {'original':'preserved'})
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, '16 MiB'):
            write(path, {'too_large':'x'*(16*1024*1024)})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(read(path), {'original':'preserved'})

    def test_shard_tampering_is_detected(self):
        self.prepare()
        path = self.root/'work/current-case/case-v2.json'
        raw = json.loads(path.read_text())
        (path.parent/raw['events'][0]['$rf_record']).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'reference changed'):
            status(self.root)

    def copied_project(self):
        destination = self.root.parent/(self.root.name+'-copy')
        shutil.copytree(self.root, destination)
        self.addCleanup(lambda: shutil.rmtree(destination))
        return destination

    def test_relocation_rebinds_copy_and_invalidates_checks_without_changing_source(self):
        add = self.prepare()
        add({'op':'supplement','text':'Preserve the full goal'})
        run_check(self.root, 'work/current-case', 'C1', 'plan.json', 'work/pass')
        allocation = disk.allocate(self.root, 'Cached observation', 'Recreate', disk.MiB,
            tier='reusable', reuse_key='v1', reuse_reason='Next phase', input_paths=['research.md'])
        (Path(allocation['path'])/'payload').write_bytes(b'known')
        disk.complete(self.root, allocation['id'])
        before = (self.root/'work/current-case/case-v2.json').read_bytes()
        destination = self.copied_project()
        result = relocate(destination, str(self.root), 'Copied to another machine', inactive=True)
        self.assertEqual(result['status'], 'relocated')
        current = status(destination)
        self.assertEqual(current['supplements'], ['Preserve the full goal'])
        self.assertEqual(current['features']['F1']['checks']['C1'], 'incomplete')
        self.assertEqual(current['delivery']['status'], 'not-delivered')
        self.assertEqual((self.root/'work/current-case/case-v2.json').read_bytes(), before)
        self.assertEqual(disk.maintain(destination, apply=False)['status'], 'ok')
        with self.assertRaisesRegex(ValueError, 'relocated'):
            disk.reuse(destination, allocation['id'])
        again = run_check(destination, 'work/current-case', 'C1', 'plan.json', 'work/new-check')
        self.assertEqual(again['comparison']['status'], 'pass')

    def test_relocation_refuses_bad_evidence_and_live_lease(self):
        self.prepare()
        allocation = disk.allocate(self.root, 'Active', 'Recreate', disk.MiB)
        destination = self.copied_project()
        before = (destination/'work/current-case/case-v2.json').read_bytes()
        with locked(disk._lease_path(allocation['id'])):
            with self.assertRaisesRegex(ValueError, 'lease'):
                relocate(destination, str(self.root), 'Move', inactive=True)
        self.assertEqual((destination/'work/current-case/case-v2.json').read_bytes(), before)
        entry = read(destination/'work/current-case/case-v2.json')['evidence']['E1']
        (destination/entry['path']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            relocate(destination, str(self.root), 'Move', inactive=True)
        self.assertEqual((destination/'work/current-case/case-v2.json').read_bytes(), before)

    def test_relocation_does_not_release_original_manual_reservations(self):
        self.prepare()
        allocation = disk.allocate(self.root, 'Stopped manual work', 'Recreate', disk.MiB)
        destination = self.copied_project()
        relocate(destination, str(self.root), 'Copy stopped work', inactive=True)
        disk.complete(destination, allocation['id'])
        self.assertEqual(disk._global(self.root)['reservations'][allocation['id']]['project'], str(self.root))
        self.assertTrue(Path(allocation['path']).exists())

    def test_relocation_requires_confirmation_and_rolls_back_write_failures(self):
        self.prepare()
        destination = self.copied_project()
        with self.assertRaisesRegex(ValueError, 'inactive'):
            relocate(destination, str(self.root), 'Move')
        before = (destination/'work/current-case/case-v2.json').read_bytes()
        from rea_enhanced import relocation
        real_write = relocation.write
        def fail(path, value):
            if path.name.startswith('volume-'):
                raise OSError('injected coordinator failure')
            return real_write(path, value)
        with patch('rea_enhanced.relocation.write', side_effect=fail):
            with self.assertRaises(OSError):
                relocate(destination, str(self.root), 'Move', inactive=True)
        self.assertEqual((destination/'work/current-case/case-v2.json').read_bytes(), before)


class InstallationRepairs(unittest.TestCase):
    def test_missing_optional_tool_does_not_block_the_environment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root/'state/rea-providers.json', {'schema_version':2,'repository_root':str(root),
                'paths':{'REA_GDB_COMMAND':str(root/'gone.exe')},'sources':{}})
            self.assertIn('REA_GDB_COMMAND', providers(root)['unavailable'])
            self.assertNotIn('REA_GDB_COMMAND', environment(root))

    def test_reinstall_preserves_modified_skill_and_accepts_recorded_previous_version(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            first = install(ROOT, home, check=False)
            paths = _paths(home)
            before = {k:p.read_bytes() for k,p in paths.items()}
            with paths['skill'].open('ab') as f:
                f.write(b'\nUser addition\n')
            changed = paths['skill'].read_bytes()
            with self.assertRaisesRegex(ValueError, 'skill changed'):
                install(ROOT, home, check=False)
            self.assertEqual(paths['skill'].read_bytes(), changed)
            self.assertEqual(paths['config'].read_bytes(), before['config'])
            paths['skill'].write_bytes(before['skill'])
            import rea_enhanced.deployment as deployment
            render = deployment.skill_text
            with patch('rea_enhanced.deployment.skill_text', side_effect=lambda root:render(root)+'\nNew release guidance\n'):
                second = install(ROOT, home, check=False)
            rollback(second['rollback_receipt'], ROOT)
            rollback(first['rollback_receipt'], ROOT)


class BrowserRepairs(unittest.TestCase):
    setUp = test_web.WebComparison.setUp

    def test_below_fold_color_difference_fails_full_page_capture(self):
        for side,color in [('original','blue'),('candidate','red')]:
            (self.root/side/'index.html').write_text('<!doctype html><body style="margin:0">'
                '<h1 id="top">Same</h1><div style="height:1400px"></div>'
                '<footer id="footer" style="height:200px;background:'+color+'">Same footer</footer>')
        self.plan.update(widths=[390], observe=['#top','#footer'], storage_keys=[],
            scenarios=[{'id':'long-page','steps':[{'action':'observe'},{'action':'scroll','selector':'#footer'}]}])
        write(self.root/'plan.json', self.plan)
        result = compare(self.root, 'plan.json', 'work/full')
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(all(c['visual_status']=='fail' and c['behavior_status']=='pass' for c in result['cases']))
        self.assertIn('full-page', result['visual_coverage'])

    def test_capture_and_screenshot_loss_or_tampering_invalidate(self):
        self.plan.update(widths=[390], scenarios=[{'id':'one','steps':[{'action':'observe'}]}])
        write(self.root/'plan.json', self.plan)
        result = compare(self.root, 'plan.json', 'work/screens')
        self.assertEqual(result['status'], 'pass')
        self.assertTrue(fresh(self.root, result))
        for name in result['observation_files']:
            path = self.root/name
            data = path.read_bytes()
            path.unlink()
            self.assertFalse(fresh(self.root, result), name)
            path.write_bytes(data+b'changed')
            self.assertFalse(fresh(self.root, result), name)
            path.write_bytes(data)
        self.assertTrue(fresh(self.root, result))


if __name__ == '__main__':
    unittest.main()
