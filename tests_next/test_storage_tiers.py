"""Real-file counterexamples for generated storage tiers and host boundary review."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from rea_enhanced import disk
from rea_enhanced.storage import digest, locked, read, write

ROOT = Path(__file__).resolve().parents[1]


class StorageTiers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.environment = patch.dict(os.environ, {'RF_NEXT_DISK_STATE': str(Path(self.temp.name) / 'coordinator')})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        (self.root / 'source.txt').write_text('source version one', encoding='utf-8')

    def allocate(self, tier='disposable', **options):
        if tier == 'reusable':
            options = {'reuse_key': 'fixture/source-v1', 'reuse_reason': 'Reuse in the next comparison batch',
                       'input_paths': ['source.txt'], **options}
        return disk.allocate(self.root, 'A bounded test output', 'Rerun the saved fixture',
                             options.pop('reserve_bytes', disk.MiB), tier=tier, **options)

    def produced(self, tier='reusable', **options):
        allocation = self.allocate(tier, **options)
        area = Path(allocation['path'])
        (area / 'payload.bin').write_bytes(b'known rebuildable output')
        disk.complete(self.root, allocation['id'], cleanup=False)
        return allocation, area

    def decision(self, allocation, decision='release', reason='The dependent work is finished; regenerate if needed'):
        return {'id': allocation['id'], 'decision': decision, 'reason': reason}

    def test_generated_tiers_separate_permanent_cache_and_throwaway_paths(self):
        permanent, saved = self.produced('persistent')
        cache, cached = self.produced()
        throwaway, transient = self.produced('disposable')
        self.assertTrue(saved.is_relative_to(self.root / '.rea-enhanced/persistent'))
        self.assertTrue(cached.is_relative_to(self.root / '.rea-enhanced/reusable'))
        self.assertTrue(transient.is_relative_to(self.root / '.rea-enhanced/scratch'))
        report = disk.review(self.root, 'stage-change')
        self.assertTrue(saved.exists())
        self.assertTrue(cached.exists())
        self.assertFalse(transient.exists())
        self.assertEqual([p['id'] for p in report['review']['pending']], [cache['id']])
        permanent_row = next(row for row in report['entries'] if row['id'] == permanent['id'])
        self.assertFalse(permanent_row['measured'])
        self.assertEqual((self.root / 'source.txt').read_text(), 'source version one')

    def test_permanent_data_survives_zero_ttls_pressure_and_explicit_release_attempt(self):
        permanent, area = self.produced('persistent')
        disk.policy(self.root, {'completed_ttl_seconds': 0, 'interrupted_ttl_seconds': 0,
                                'reuse_review_seconds': 0})
        for boundary in ('task-end', 'space-pressure', 'resume'):
            report = disk.review(self.root, boundary)
            self.assertEqual(report['entries'][0]['state'], 'persistent-preserved')
        with self.assertRaises(ValueError):
            disk.review(self.root, 'space-pressure', [self.decision(permanent)])
        self.assertEqual((area / 'payload.bin').read_bytes(), b'known rebuildable output')

    def test_cache_age_only_requests_host_review_and_keep_records_next_use(self):
        allocation, area = self.produced()
        disk.policy(self.root, {'completed_ttl_seconds': 0, 'interrupted_ttl_seconds': 0,
                                'reuse_review_seconds': 0})
        report = disk.maintain(self.root)
        self.assertTrue(area.exists())
        self.assertIn('review_reason', report['entries'][0])
        result = disk.review(self.root, 'stage-change', [self.decision(
            allocation, 'keep', 'The next selected scenario reuses this decoded resource set')])
        self.assertEqual(result['review']['decisions'][0]['outcome'], 'kept-for-reuse')
        self.assertIn('decoded resource', disk._load(self.root)['entries'][allocation['id']]['reuse_reason'])
        self.assertTrue(area.exists())

    def test_release_at_boundary_reclaims_actual_cache_and_completed_throwaway_only(self):
        cache, cached = self.produced()
        throwaway, transient = self.produced('disposable')
        active = self.allocate()
        active_path = Path(active['path'])
        (active_path / 'in-flight').write_bytes(b'still needed')
        expected = disk.size(cached) + disk.size(transient)
        result = disk.review(self.root, 'verification-end', [self.decision(cache)])
        self.assertEqual(result['reclaimed_bytes'], expected)
        self.assertFalse(cached.exists())
        self.assertFalse(transient.exists())
        self.assertTrue((active_path / 'in-flight').exists())
        self.assertEqual(result['total_reclaimed_bytes'], expected)
        self.assertNotIn(cache['id'], disk._load(self.root)['entries'])

    def test_reuse_checks_content_and_inputs_then_retains_active_user(self):
        allocation, area = self.produced()
        reused = disk.reuse(self.root, allocation['id'])
        self.assertTrue(reused['inputs_verified'])
        self.assertTrue(reused['content_verified'])
        report = disk.review(self.root, 'task-end', [self.decision(allocation)])
        self.assertEqual(report['review']['decisions'][0]['outcome'], 'retained')
        self.assertTrue(area.exists())
        disk.complete(self.root, allocation['id'])
        self.assertTrue(area.exists())
        disk.review(self.root, 'operation-end', [self.decision(allocation)])
        self.assertFalse(area.exists())

    def test_reuse_refuses_changed_dependency_without_deleting_old_output(self):
        allocation, area = self.produced()
        (self.root / 'source.txt').write_text('source version two', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'inputs changed'):
            disk.reuse(self.root, allocation['id'])
        self.assertEqual(disk._load(self.root)['entries'][allocation['id']]['state'], 'completed')
        self.assertTrue(area.exists())
        disk.review(self.root, 'stage-change', [self.decision(allocation)])
        self.assertFalse(area.exists())

    def test_reuse_refuses_modified_or_missing_output_without_blessing_it(self):
        allocation, area = self.produced()
        (area / 'unexpected-empty-directory').mkdir()
        with self.assertRaisesRegex(ValueError, 'content changed'):
            disk.reuse(self.root, allocation['id'])
        (area / 'unexpected-empty-directory').rmdir()
        (area / 'payload.bin').write_bytes(b'untracked replacement')
        with self.assertRaisesRegex(ValueError, 'content changed'):
            disk.reuse(self.root, allocation['id'])
        self.assertTrue(area.exists())
        (area / 'payload.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'content changed'):
            disk.reuse(self.root, allocation['id'])

    def test_input_changed_during_generation_does_not_certify_stale_cache(self):
        allocation = self.allocate('reusable')
        area = Path(allocation['path'])
        (area / 'payload.bin').write_bytes(b'compiled from previous source')
        (self.root / 'source.txt').write_text('source version two', encoding='utf-8')
        disk.complete(self.root, allocation['id'])
        saved = disk._load(self.root)['entries'][allocation['id']]
        self.assertEqual(saved['state'], 'completed')
        self.assertIn('reuse_invalid', saved)
        self.assertTrue(area.exists())
        with self.assertRaises(ValueError):
            disk.reuse(self.root, allocation['id'])
        (self.root / 'source.txt').unlink()
        disk.complete(self.root, allocation['id'])
        self.assertEqual(disk._load(self.root)['entries'][allocation['id']]['state'], 'completed')
        disk.review(self.root, 'operation-end', [self.decision(allocation)])
        self.assertFalse(area.exists())

    def test_os_lease_prevents_release_and_promotion_of_completed_cache(self):
        allocation, area = self.produced()
        with locked(disk._lease_path(allocation['id'])):
            report = disk.review(self.root, 'space-pressure', [self.decision(allocation)])
            self.assertEqual(report['review']['decisions'][0]['outcome'], 'retained')
            with self.assertRaises(ValueError):
                disk.promote(self.root, allocation['id'])
            self.assertTrue(area.exists())

    def test_explicit_and_case_protection_override_host_cache_release(self):
        explicit, first = self.produced()
        referenced, second = self.produced()
        disk.protect(self.root, [explicit['relative_path'] + '/payload.bin'])
        write(self.root / 'work/current-case/case-v2.json', {
            'evidence': {'E1': {'path': referenced['relative_path'] + '/payload.bin'}}})
        write(self.root / '.rea-enhanced/cases.json', {'case_roots': ['work/current-case']})
        result = disk.review(self.root, 'space-pressure', [self.decision(explicit), self.decision(referenced)])
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertTrue(all(r['outcome'] == 'retained' for r in result['review']['decisions']))
        with self.assertRaisesRegex(ValueError, 'Referenced paths'):
            disk.promote(self.root, referenced['id'])

    def test_promotion_moves_finished_cache_to_permanent_and_forbids_downgrade(self):
        allocation, old = self.produced()
        result = disk.promote(self.root, allocation['id'])
        area = Path(result['path'])
        self.assertFalse(old.exists())
        self.assertTrue(area.is_relative_to(self.root / '.rea-enhanced/persistent'))
        self.assertEqual((area / 'payload.bin').read_bytes(), b'known rebuildable output')
        with self.assertRaises(ValueError):
            disk.review(self.root, 'space-pressure', [self.decision(allocation)])
        disk.maintain(self.root, force_completed=True)
        self.assertTrue(area.exists())

    def test_failed_promotion_record_write_restores_original_path(self):
        allocation, old = self.produced()
        with patch.object(disk, '_save', side_effect=OSError('simulated registry write failure')):
            with self.assertRaises(OSError):
                disk.promote(self.root, allocation['id'])
        self.assertTrue((old / 'payload.bin').exists())
        self.assertFalse((self.root / '.rea-enhanced/persistent' / allocation['id']).exists())
        self.assertEqual(disk._load(self.root)['entries'][allocation['id']]['tier'], 'reusable')

    def test_reusable_budget_blocks_growth_until_host_releases_unused_cache(self):
        disk.policy(self.root, {'max_reusable_bytes': disk.MiB})
        first, area = self.produced(reserve_bytes=disk.MiB)
        with self.assertRaisesRegex(ValueError, 'Reusable budget'):
            self.allocate('reusable', reserve_bytes=disk.MiB)
        self.assertTrue(area.exists())
        disk.review(self.root, 'space-pressure', [self.decision(first)])
        second = self.allocate('reusable', reserve_bytes=disk.MiB)
        self.assertTrue(Path(second['path']).exists())

    def test_reacquiring_small_cache_rechecks_its_full_peak_against_other_active_work(self):
        disk.policy(self.root, {'max_temporary_bytes': 3 * disk.MiB, 'max_reusable_bytes': 3 * disk.MiB})
        cache, area = self.produced(reserve_bytes=2 * disk.MiB)
        active = self.allocate(reserve_bytes=2 * disk.MiB)
        with self.assertRaisesRegex(ValueError, 'budget'):
            disk.reuse(self.root, cache['id'])
        self.assertTrue(area.exists())
        self.assertEqual(disk._load(self.root)['entries'][cache['id']]['state'], 'completed')
        self.assertTrue(Path(active['path']).exists())

    def test_permanent_artifacts_do_not_consume_temporary_project_budget(self):
        disk.policy(self.root, {'max_temporary_bytes': disk.MiB})
        permanent, area = self.produced('persistent', reserve_bytes=2 * disk.MiB)
        throwaway = self.allocate(reserve_bytes=disk.MiB)
        self.assertTrue(area.exists())
        self.assertTrue(Path(throwaway['path']).exists())

    def test_old_registry_without_tier_or_new_policy_keeps_disposable_compatibility(self):
        allocation, area = self.produced('disposable')
        value = disk._load(self.root)
        value['entries'][allocation['id']].pop('tier')
        value['policy'].pop('max_reusable_bytes')
        value['policy'].pop('reuse_review_seconds')
        disk._save(self.root, value)
        report = disk.review(self.root, 'resume')
        self.assertFalse(area.exists())
        self.assertEqual(report['entries'][0]['tier'], 'disposable')
        self.assertIn('max_reusable_bytes', report['policy'])

    def test_two_users_racing_for_same_cache_get_one_active_lifetime(self):
        allocation, area = self.produced()
        barrier = threading.Barrier(2)
        def acquire(_):
            barrier.wait()
            try:
                return disk.reuse(self.root, allocation['id'])
            except ValueError as exc:
                return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(acquire, range(2)))
        self.assertEqual(sum(isinstance(v, dict) for v in results), 1, results)
        self.assertTrue(area.exists())
        self.assertEqual(disk._load(self.root)['entries'][allocation['id']]['state'], 'active')

    def test_duplicate_identity_keeps_existing_data_and_volume_reservation(self):
        allocation = self.allocate('reusable')
        area = Path(allocation['path'])
        (area / 'owned-output.bin').write_bytes(b'active existing output')
        before = disk._global(self.root)['reservations'][allocation['id']]
        with self.assertRaises(ValueError):
            self.allocate('persistent', token=allocation['id'])
        self.assertEqual(disk._global(self.root)['reservations'][allocation['id']], before)
        self.assertEqual((area / 'owned-output.bin').read_bytes(), b'active existing output')

    def test_invalid_production_cannot_be_blessed_by_restoring_inputs_and_missing_cache_can_retire(self):
        allocation = self.allocate('reusable')
        area = Path(allocation['path'])
        original = (self.root / 'source.txt').read_bytes()
        (area / 'payload').write_bytes(b'output produced with changing input')
        (self.root / 'source.txt').write_bytes(b'changed during production')
        disk.complete(self.root, allocation['id'])
        (self.root / 'source.txt').write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'production was invalid'):
            disk.reuse(self.root, allocation['id'])
        disk.review(self.root, 'verification-end', [self.decision(allocation)])
        self.assertFalse(area.exists())
        missing = self.allocate('reusable')
        missing_area = Path(missing['path'])
        (missing_area / disk.MARKER).unlink()
        missing_area.rmdir()
        disk.complete(self.root, missing['id'])
        result = disk.review(self.root, 'space-pressure', [self.decision(missing)])
        self.assertEqual(result['review']['decisions'][0]['outcome'], 'reclaimed')
        self.assertNotIn(missing['id'], disk._load(self.root)['entries'])

    def test_invalid_later_review_decision_does_not_delete_earlier_cache(self):
        allocation, area = self.produced()
        with self.assertRaises(ValueError):
            disk.review(self.root, 'stage-change', [self.decision(allocation), {
                'id': 'not-registered', 'decision': 'release', 'reason': 'invalid later identity'}])
        self.assertTrue(area.exists())
        self.assertIn(allocation['id'], disk._load(self.root)['entries'])

    def test_marker_tampering_prevents_cache_release(self):
        allocation, area = self.produced()
        write(area / disk.MARKER, {'owner': 'someone-else'})
        result = disk.review(self.root, 'space-pressure', [self.decision(allocation)])
        self.assertEqual(result['review']['decisions'][0]['outcome'], 'retained-error')
        self.assertTrue((area / 'payload.bin').exists())

    def test_cache_junction_prevents_release_and_preserves_external_original(self):
        allocation, area = self.produced()
        external = Path(self.temp.name) / 'outside-project'
        external.mkdir()
        (external / 'original.bin').write_bytes(b'irreplaceable original')
        link = area / 'linked'
        if os.name == 'nt':
            created = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(external)], capture_output=True)
            self.assertEqual(created.returncode, 0, created.stderr)
        else:
            link.symlink_to(external, target_is_directory=True)
        try:
            result = disk.review(self.root, 'space-pressure', [self.decision(allocation)])
            self.assertEqual(result['review']['decisions'][0]['outcome'], 'retained-error')
            self.assertEqual((external / 'original.bin').read_bytes(), b'irreplaceable original')
            self.assertTrue(area.exists())
        finally:
            if os.name == 'nt':
                link.rmdir()
            else:
                link.unlink()

    def test_live_stdio_catalog_and_tier_lifecycle_preserve_actual_payload(self):
        from reverse_fusion.mcp_probe import StdioMcp, catalog
        original_hash = digest(self.root / 'source.txt')
        events = []
        client = StdioMcp([sys.executable, '-m', 'rea_enhanced', 'mcp'], cwd=ROOT, timeout=45)
        with client:
            server_info = client.initialize()['serverInfo']
            storage = next(tool for tool in catalog(client) if tool['name'] == 'rf_next_storage')
            properties = storage['inputSchema']['properties']
            self.assertTrue({'review', 'reuse', 'promote'} <= set(properties['action']['enum']))
            self.assertEqual(set(properties['tier']['enum']), {'persistent', 'reusable', 'disposable'})
            def call(action, **options):
                result = client.request('tools/call', {'name': 'rf_next_storage', 'arguments': {
                    'project_root': str(self.root), 'action': action, **options}})
                self.assertFalse(result.get('isError'), result)
                receipt = result['structuredContent']
                events.append({'action': action, 'arguments': options, 'result': receipt})
                return receipt
            allocation = call('allocate', tier='reusable', purpose='Real MCP reusable output',
                              rebuild='Rerun this fixture', reserve_bytes=disk.MiB,
                              reuse_key='stdio-fixture-v1', reuse_reason='Reuse at the next boundary',
                              input_paths=['source.txt'])
            old = Path(allocation['path'])
            (old / 'mcp-output.bin').write_bytes(b'actual MCP payload')
            payload_hash = digest(old / 'mcp-output.bin')
            call('complete', id=allocation['id'])
            review = call('review', boundary='stage-change')
            self.assertEqual([row['id'] for row in review['review']['pending']], [allocation['id']])
            kept = call('review', boundary='stage-change', decisions=[self.decision(
                allocation, 'keep', 'The next MCP replay uses this payload')])
            self.assertEqual(kept['review']['decisions'][0]['outcome'], 'kept-for-reuse')
            self.assertTrue(call('reuse', id=allocation['id'])['content_verified'])
            call('complete', id=allocation['id'])
            promoted = call('promote', id=allocation['id'])
            self.assertFalse(old.exists())
            saved = Path(promoted['path'])
            call('review', boundary='task-end')
            self.assertEqual((saved / 'mcp-output.bin').read_bytes(), b'actual MCP payload')
            self.assertEqual(digest(saved / 'mcp-output.bin'), payload_hash)
            releasable = call('allocate', tier='reusable', purpose='Real MCP cache release',
                             rebuild='Rerun fixture', reserve_bytes=disk.MiB,
                             reuse_key='stdio-discard-v1', reuse_reason='Only needed during this batch',
                             input_paths=['source.txt'])
            cache_path = Path(releasable['path'])
            (cache_path / 'cache.bin').write_bytes(b'actual reusable cache')
            call('complete', id=releasable['id'])
            released = call('review', boundary='verification-end', decisions=[self.decision(releasable)])
            self.assertGreater(released['reclaimed_bytes'], 0)
            self.assertFalse(cache_path.exists())
            disposable = call('allocate', purpose='Real MCP throwaway', rebuild='Rerun fixture',
                              reserve_bytes=disk.MiB)
            transient = Path(disposable['path'])
            (transient / 'discard.bin').write_bytes(b'throwaway')
            completed = call('complete', id=disposable['id'])
            self.assertGreater(completed['reclaimed_bytes'], 0)
            self.assertFalse(transient.exists())
            promotable = call('allocate', purpose='MCP disposable-to-persistent upgrade',
                              rebuild='Rerun fixture', reserve_bytes=disk.MiB)
            initial = Path(promotable['path'])
            (initial / 'upgrade.bin').write_bytes(b'durable result selected from temporary work')
            upgrade_hash = digest(initial / 'upgrade.bin')
            call('complete', id=promotable['id'], cleanup=False)
            self.assertTrue(initial.exists())
            durable_upgrade = Path(call('promote', id=promotable['id'])['path'])
            self.assertFalse(initial.exists())
            call('review', boundary='task-end')
            self.assertEqual(digest(durable_upgrade / 'upgrade.bin'), upgrade_hash)
        self.assertEqual(client.cleanup['status'], 'verified')
        self.assertEqual(digest(self.root / 'source.txt'), original_hash)
        write(ROOT / 'evidence/next/tiered-storage/live-proof.json', {
            'status': 'pass', 'server_info': server_info, 'events': events,
            'original_input_sha256_before': original_hash,
            'original_input_sha256_after': digest(self.root / 'source.txt'),
            'promoted_payload_sha256_before': payload_hash,
            'promoted_payload_sha256_after': digest(saved / 'mcp-output.bin'),
            'persistent_file_preserved_at_task_end': (saved / 'mcp-output.bin').exists(),
            'reusable_release_path_absent': not cache_path.exists(),
            'disposable_complete_path_absent': not transient.exists(),
            'disposable_promoted_payload_sha256_before': upgrade_hash,
            'disposable_promoted_payload_sha256_after': digest(durable_upgrade / 'upgrade.bin'),
            'disposable_promoted_path_preserved': durable_upgrade.exists(),
            'actual_reclaimed_bytes': released['reclaimed_bytes'] + completed['reclaimed_bytes'],
            'cleanup': client.cleanup,
            'scope': 'Actual stdio MCP lifecycle on owned fixtures, original input and promoted payload preserved during the operation. Temporary test fixture is removed after assertions; not a real target or model-effectiveness result.'})

    def test_absolute_cli_tier_actions_work_from_an_unrelated_working_directory(self):
        elsewhere = Path(self.temp.name) / 'unrelated-empty-workspace'
        elsewhere.mkdir()
        options_file = Path(self.temp.name) / 'storage-options.json'
        def call(action, **options):
            write(options_file, options)
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/next-cli.py'), 'storage',
                '--project-root', str(self.root), '--action', action, '--options-file', str(options_file)],
                cwd=elsewhere, capture_output=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', errors='replace'))
            return json.loads(run.stdout)
        cache = call('allocate', tier='reusable', purpose='Absolute CLI reusable output',
                     rebuild='Rerun this fixture', reserve_bytes=disk.MiB,
                     reuse_key='cli-fixture-v1', reuse_reason='Reuse at next operation boundary',
                     input_paths=['source.txt'])
        area = Path(cache['path'])
        (area / 'cli-output.bin').write_bytes(b'actual CLI payload')
        call('complete', id=cache['id'])
        self.assertTrue(call('reuse', id=cache['id'])['inputs_verified'])
        call('complete', id=cache['id'])
        result = call('review', boundary='verification-end', decisions=[self.decision(cache)])
        self.assertGreater(result['reclaimed_bytes'], 0)
        self.assertFalse(area.exists())
        permanent = call('allocate', tier='persistent', purpose='Absolute CLI durable output',
                         rebuild='Keep durable output; source fixture is preserved', reserve_bytes=disk.MiB)
        saved = Path(permanent['path'])
        (saved / 'final.bin').write_bytes(b'actual final payload')
        call('complete', id=permanent['id'])
        call('review', boundary='task-end')
        self.assertEqual((saved / 'final.bin').read_bytes(), b'actual final payload')
        self.assertFalse((elsewhere / '.rea-enhanced').exists())


if __name__ == '__main__':
    unittest.main()
