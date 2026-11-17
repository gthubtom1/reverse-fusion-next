"""Disk lifecycle counterexamples with real files, leases and concurrent projects."""
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from rea_enhanced import disk
from rea_enhanced.comparison import compare, fresh
from rea_enhanced.storage import locked, read, write
from tests_next import test_workflow as fixture


class DiskLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.environment = patch.dict(os.environ, {'RF_NEXT_DISK_STATE': str(Path(self.temp.name) / 'coord')})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def allocate(self, root=None, **kwargs):
        return disk.allocate(root or self.root, 'Owned repeated test', 'Rerun the owned test fixture',
                             kwargs.get('reserve_bytes', 4 * disk.MiB))

    def test_complete_reclaims_actual_files_and_leaves_unregistered_data(self):
        original = self.root / 'original.exe'; original.write_bytes(b'original')
        old = self.root / 'work/old-run'; old.mkdir(parents=True); (old / 'keep').write_bytes(b'legacy')
        allocation = self.allocate(); area = Path(allocation['path'])
        (area / 'temporary').write_bytes(b'x' * disk.MiB)
        before = disk.size(area)
        result = disk.complete(self.root, allocation['id'])
        self.assertEqual(result['reclaimed_bytes'], before)
        self.assertFalse(area.exists())
        self.assertEqual(original.read_bytes(), b'original')
        self.assertTrue((old / 'keep').exists())

    def test_manual_work_never_expires_while_declared_active(self):
        allocation = self.allocate()
        disk.policy(self.root, {'interrupted_ttl_seconds': 0, 'completed_ttl_seconds': 0})
        report = disk.maintain(self.root, force_completed=True)
        self.assertEqual(report['entries'][0]['state'], 'active')
        self.assertTrue(Path(allocation['path']).exists())

    def test_os_lease_prevents_even_explicit_completion(self):
        allocation = self.allocate()
        # Separate OS handle, same rule as another MCP/CLI process. No PID guessing.
        with locked(disk._lease_path(allocation['id'])):
            with self.assertRaisesRegex(ValueError, 'running operation'):
                disk.complete(self.root, allocation['id'])
            self.assertEqual(disk.maintain(self.root)['entries'][0]['state'], 'active')
        disk.complete(self.root, allocation['id'])

    def test_referenced_evidence_and_product_scratch_are_protected(self):
        allocation = self.allocate(); area = Path(allocation['path'])
        (area / 'fact.bin').write_bytes(b'needed observation')
        name = allocation['relative_path'] + '/fact.bin'
        case_root = 'work/case'; case = self.root / case_root / 'case-v2.json'
        write(case, {'evidence': {'E1': {'path': name}}, 'product': {'candidate_files': {name: 'hash'}}})
        write(self.root / '.rea-enhanced/cases.json', {'case_roots': [case_root]})
        result = disk.complete(self.root, allocation['id'])
        self.assertEqual(result['entries'][0]['state'], 'protected')
        self.assertTrue((area / 'fact.bin').exists())

    def test_explicit_protection_covers_descendants_and_ancestors(self):
        a = self.allocate()
        disk.protect(self.root, [a['relative_path'] + '/future-delivery.bin'])
        self.assertEqual(disk.complete(self.root, a['id'])['entries'][0]['state'], 'protected')

    def test_marker_tampering_is_retained(self):
        a = self.allocate(); area = Path(a['path'])
        (area / disk.MARKER).write_text('{}', encoding='utf-8')
        report = disk.maintain(self.root, force_completed=True)
        self.assertEqual(report['entries'][0]['state'], 'retained-error')
        self.assertTrue(area.exists())

    def test_registry_cannot_redirect_deletion_to_original(self):
        a = self.allocate(); original = self.root / 'original'; original.mkdir()
        (original / 'sample').write_bytes(b'original')
        value = disk._load(self.root); value['entries'][a['id']]['path'] = 'original'
        disk._save(self.root, value)
        self.assertEqual(disk.maintain(self.root)['entries'][0]['state'], 'retained-error')
        self.assertTrue((original / 'sample').exists())

    def test_junction_or_symlink_causes_retention_and_external_data_survives(self):
        a = self.allocate(); area = Path(a['path'])
        external = Path(self.temp.name) / 'external'; external.mkdir(); (external / 'keep').write_bytes(b'important')
        link = area / 'linked'
        if os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(external)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            link.symlink_to(external, target_is_directory=True)
        try:
            report = disk.complete(self.root, a['id'])
            self.assertEqual(report['entries'][0]['state'], 'retained-error')
            self.assertTrue((external / 'keep').exists())
        finally:
            if os.name == 'nt': link.rmdir()
            else: link.unlink()

    def test_incomplete_case_index_preserves_all_scratch(self):
        a = self.allocate()
        write(self.root / '.rea-enhanced/cases.json', {'case_roots': ['missing-case']})
        with self.assertRaises(OSError):
            disk.complete(self.root, a['id'])
        self.assertTrue(Path(a['path']).exists())

    def test_dead_managed_lease_waits_for_interrupted_retention_then_reclaims(self):
        a = disk.allocate(self.root, 'Interrupted work', 'Rerun known fixture', disk.MiB, mode='managed')
        self.assertEqual(disk.maintain(self.root)['entries'][0]['state'], 'interrupted-retained')
        disk.policy(self.root, {'interrupted_ttl_seconds': 0})
        self.assertEqual(disk.maintain(self.root)['entries'][0]['state'], 'reclaimed')
        self.assertFalse(Path(a['path']).exists())

    def test_project_budget_accounts_for_other_active_work(self):
        disk.policy(self.root, {'max_temporary_bytes': 5 * disk.MiB})
        self.allocate()
        with self.assertRaisesRegex(ValueError, 'Project temporary budget'):
            self.allocate()

    def test_live_inventory_tolerates_disappearing_browser_files_but_deletion_is_strict(self):
        a = self.allocate(); area = Path(a['path']); (area / 'ephemeral').write_bytes(b'temporary')
        original = disk.no_links
        def disappeared(path, root):
            if path.name == 'ephemeral':
                raise FileNotFoundError('Browser removed the file after directory enumeration')
            return original(path, root)
        with patch.object(disk, 'no_links', side_effect=disappeared):
            self.assertGreater(disk.size(area, live=True), 0)
            with self.assertRaises(FileNotFoundError):
                disk.size(area)

    def test_volume_reservations_serialize_two_concurrent_projects(self):
        other = Path(self.temp.name) / 'other'; other.mkdir()
        for root in [self.root, other]:
            disk.policy(root, {'minimum_free_bytes': 100, 'minimum_free_fraction': 0})
        usage = namedtuple('Usage', 'total used free')(2000, 1000, 1000)
        barrier = threading.Barrier(2)
        def run(root):
            barrier.wait()
            try: return self.allocate(root, reserve_bytes=600)
            except ValueError as exc: return str(exc)
        with patch.object(disk.shutil, 'disk_usage', return_value=usage):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run, [self.root, other]))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1, results)
        self.assertTrue(any('unreserved disk' in r for r in results if isinstance(r, str)), results)

    def test_periodic_worker_cleans_completed_data(self):
        a = self.allocate(); disk.complete(self.root, a['id'], cleanup=False)
        disk.policy(self.root, {'completed_ttl_seconds': 0})
        stop = threading.Event(); worker = threading.Thread(target=disk.maintenance_loop, args=(stop, .02))
        worker.start()
        try:
            until = time.monotonic() + 3
            while Path(a['path']).exists() and time.monotonic() < until:
                time.sleep(.02)
            self.assertFalse(Path(a['path']).exists())
        finally:
            stop.set(); worker.join(3)

    def test_comparison_reclaims_copies_and_retains_real_effect_snapshots(self):
        helper = fixture.OwnedCase(); helper.setUp(); self.addCleanup(helper.doCleanups)
        result = compare(helper.root, 'plan.json', 'work/receipt')
        self.assertEqual(result['status'], 'pass', result.get('failure'))
        self.assertFalse((helper.root / 'work/receipt/runs').exists())
        self.assertTrue(fresh(helper.root, result))
        effect = result['cases'][0]['observations']['original']['files']['state.json']['snapshot']
        self.assertIn('count', (helper.root / effect).read_text())
        self.assertGreater(sum(r['reclaimed_bytes'] for r in result['storage']['cleanup']), 0)
        self.assertFalse(disk._load(helper.root)['entries'])
        (helper.root / effect).write_text('changed evidence', encoding='utf-8')
        self.assertFalse(fresh(helper.root, result))

    def test_independent_processes_share_the_same_volume_reservation(self):
        other = Path(self.temp.name) / 'other-process'; other.mkdir()
        for root in [self.root, other]:
            disk.policy(root, {'minimum_free_bytes': 100, 'minimum_free_fraction': 0})
        script = Path(self.temp.name) / 'reserve.py'
        script.write_text('''import sys,json
from pathlib import Path
from unittest.mock import patch
from collections import namedtuple
from rea_enhanced import disk
usage=namedtuple('Usage','total used free')(2000,1000,1000)
with patch.object(disk.shutil,'disk_usage',return_value=usage):
    try:
        value=disk.allocate(Path(sys.argv[1]),'Concurrent external test','Rerun test',600)
        print(json.dumps({'status':'allocated','id':value['id']}))
    except ValueError as exc: print(json.dumps({'status':'paused','reason':str(exc)}))
''', encoding='utf-8')
        env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
        processes = [subprocess.Popen([sys.executable, str(script), str(root)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE) for root in [self.root, other]]
        import json
        results = []
        for process in processes:
            out, err = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, err)
            results.append(json.loads(out))
        self.assertEqual(sorted(r['status'] for r in results), ['allocated', 'paused'], results)

    def test_completing_one_allocation_does_not_force_expire_another(self):
        a = self.allocate(); disk.complete(self.root, a['id'], cleanup=False)
        b = self.allocate(); disk.complete(self.root, b['id'])
        self.assertTrue(Path(a['path']).exists())
        self.assertFalse(Path(b['path']).exists())

    def test_workspace_exception_and_external_cancel_keep_cleanup(self):
        event = threading.Event(); event.set()
        with self.assertRaisesRegex(RuntimeError, 'stop'):
            with disk.workspace(self.root, 'Cancelled owned test', 'Rerun fixture', disk.MiB, event) as scratch:
                self.assertTrue(scratch['cancel_event'].is_set())
                (scratch['path'] / 'temp').write_bytes(b'x')
                raise RuntimeError('stop')
        self.assertFalse(scratch['path'].exists())
        self.assertGreater(scratch['cleanup']['reclaimed_bytes'], 0)

    def test_space_exhaustion_stops_before_workspace_use(self):
        usage = namedtuple('Usage', 'total used free')(10 * disk.GiB, 10 * disk.GiB, 0)
        with patch.object(disk.shutil, 'disk_usage', return_value=usage):
            with self.assertRaisesRegex(ValueError, 'unreserved disk'):
                with disk.workspace(self.root, 'Space check', 'Rerun fixture', disk.MiB):
                    self.fail('Must stop before process execution')
        self.assertFalse(disk._load(self.root)['entries'])

    def test_monitor_cancels_owned_process_when_temporary_growth_exceeds_budget(self):
        from reverse_fusion.owned_process import run_owned
        script = self.root / 'grow.py'
        script.write_text("import os,time\nfrom pathlib import Path\nPath(os.environ['RF_NEXT_SCRATCH'],'large').write_bytes(b'x'*2*1024**2)\ntime.sleep(10)\n", encoding='utf-8')
        with disk.workspace(self.root, 'Growth test', 'Rerun grow.py', disk.MiB) as scratch:
            result = run_owned([sys.executable, str(script)], cwd=self.root, stdin=b'', timeout=5,
                memory_mb=128, max_output_bytes=1024, cancel_event=scratch['cancel_event'],
                env={**os.environ, 'RF_NEXT_SCRATCH': str(scratch['path'])})
        self.assertEqual(result['status'], 'unknown')
        self.assertTrue(scratch['failure'])
        self.assertFalse(scratch['path'].exists())


if __name__ == '__main__':
    unittest.main()
