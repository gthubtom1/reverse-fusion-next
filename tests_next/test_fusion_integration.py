"""Integration checks for the local-analysis release candidate on Windows."""
import json
import os
import sqlite3
from pathlib import Path
from runpy import run_path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from reverse_fusion.mcp_probe import StdioMcp, catalog


ROOT = Path(__file__).resolve().parents[1]
hosts = run_path(str(ROOT / 'scripts/review-host.py'))
layout = hosts['FUSION']
kit = run_path(str(layout.service))
runtime = kit['review'].runtime


class FusionFailureIsolation(unittest.TestCase):
    def test_missing_rea_keeps_independent_tools_available(self):
        server = kit['FusionServer']()
        self.addCleanup(server.close)
        server.initialized = True
        with patch.object(runtime, 'checked', side_effect=ValueError('prepared runtime missing')) as checked:
            catalog_before = server.dispatch('tools/list', {})['tools']
            names = {tool['name'] for tool in catalog_before}
            self.assertIn('field_observe', names)
            self.assertIn('fusion_compare_outputs', names)
            self.assertNotIn('inspect_pe_imports', names)
            info = server.dispatch('tools/call', {'name': 'review_info'})['structuredContent']
            self.assertEqual(info['fusion']['official_rea']['status'], 'unavailable')
            self.assertEqual(server.dispatch('tools/list', {})['tools'], catalog_before)
            checked.assert_called_once()
            observed = server.dispatch('tools/call', {'name': 'field_observe', 'arguments': {
                'path': str(ROOT / 'components/fusion-kit/check.plist')}})
            self.assertFalse(observed['isError'])
            self.assertEqual(observed['structuredContent']['facts']['kind'], 'bundle-plist')


@unittest.skipUnless(os.name == 'nt', 'candidate needs the pinned Windows runtime')
class FusionIntegration(unittest.TestCase):
    def mcp(self, cwd):
        return StdioMcp(hosts['command'](layout), cwd=cwd, timeout=40)

    def call(self, client, name, **arguments):
        response = client.request('tools/call', {'name': name, 'arguments': arguments})
        self.assertFalse(response.get('isError'), response)
        return response['structuredContent']

    def test_real_registration_and_byte_exact_removal(self):
        before = {
            'codex': b'# legacy stays\r\n[mcp_servers.reverse-fusion-field]\r\ncommand = "old"\r\n',
            'pi': b'{"mcpServers":{"reverse-fusion-field":{"command":"old"}},"unrelated":1}\n',
            'opencode': b'{// keep this comment\r\n"theme":"other",}\r\n',
        }
        for host, major in (('codex', 1), ('claude', 1), ('pi', 1), ('opencode', 1), ('opencode', 2)):
            with self.subTest(host=host, major=major), tempfile.TemporaryDirectory(prefix='fusion host ') as td:
                home = Path(td)
                personal = home / 'my-notes.txt'
                personal.write_bytes(b'unchanged')
                folder, config = hosts['paths'](host, home, opencode_version=major, layout=layout)
                if config:
                    config.parent.mkdir(parents=True, exist_ok=True)
                    config.write_bytes(before[host])
                def manage(action):
                    return hosts['manage'](action, host, home, opencode_version=major, layout=layout)
                self.assertEqual(manage('attach')['status'], 'attached')
                self.assertTrue((folder / 'references/domain-methods.md').is_file())
                self.assertTrue((folder / 'references/rea-evidence.md').is_file())
                check = manage('check')
                self.assertEqual(check['status'], 'verified')
                self.assertEqual(check['service_version'], kit['PROFILE']['version'])
                self.assertEqual(check['official_import']['imported'], 2)
                self.assertEqual(manage('remove')['status'], 'removed')
                self.assertFalse(folder.exists())
                self.assertEqual(personal.read_bytes(), b'unchanged')
                if config:
                    self.assertEqual(config.read_bytes(), before[host])

    def test_native_catalog_evidence_and_goal_survive_reconnection(self):
        prepared = runtime.checked()
        with tempfile.TemporaryDirectory(prefix='fusion project ') as td:
            project = Path(td)
            bundle = project / 'official.json'
            restored = project / 'restored.json'
            plain_request = 'Compare the exports and preserve the original task across a new connection.'
            with StdioMcp([prepared['node'], prepared['entry'], 'mcp'], cwd=project) as official:
                official.initialize()
                originals = {t['name']: t for t in catalog(official)}
            with self.mcp(project) as client:
                client.initialize()
                actual = {t['name']: t for t in catalog(client)}
                self.assertEqual({name: actual[name] for name in kit['NATIVE']},
                                 {name: originals[name] for name in kit['NATIVE']})
                self.assertEqual(set(actual), kit['NATIVE'] | set(kit['MEMORY']) |
                                 set(kit['review'].SPECS) | {'fusion_compare_outputs',
                                                            'fusion_read_method',
                                                            'fusion_observe_flutter_library'})
                self.call(client, 'open_binary', path=str(ROOT / 'components/fusion-kit/check.plist'))
                artifact = self.call(client, 'inspect_artifact', detail='summary')
                self.assertIn('evidence_id', artifact)
                observation = self.call(client, 'inspect_pe_imports', path=sys.executable)
                self.assertIn('normalized_result', observation)
                self.call(client, 'export_evidence_bundle', path=str(bundle))
                state = self.call(client, 'rf_next_case_open', project_root=str(project),
                                  recording='case', request=plain_request)
                self.assertEqual(state['original_request'], plain_request)
                self.call(client, 'rf_next_case_record', project_root=str(project),
                          expected_revision=state['revision'], change={
                              'op': 'checkpoint', 'note': 'Official observation saved.',
                              'next_action': 'Recheck the remaining input.', 'paths': [bundle.name]})
                blocked = client.request('tools/call', {'name': 'rf_next_case_record', 'arguments': {
                    'project_root': str(project), 'change': {'op': 'execute'}}})
                self.assertTrue(blocked['isError'])
            with self.mcp(project) as client:
                client.initialize()
                self.call(client, 'import_evidence_bundle', path=str(bundle))
                self.call(client, 'export_evidence_bundle', path=str(restored))
                state = self.call(client, 'rf_next_case_open', project_root=str(project), request='continue')
                self.assertEqual(state['original_request'], plain_request)
                checkpoint = state['checkpoint']
                self.assertTrue(checkpoint['current_files'])
                self.assertEqual(checkpoint['record']['next_action'], 'Recheck the remaining input.')
                self.assertIn(bundle.name, checkpoint['record']['files'])
                bundle.write_bytes(bundle.read_bytes() + b'\n')
                stale = self.call(client, 'rf_next_case_status', project_root=str(project))
                self.assertFalse(stale['checkpoint']['current_files'])
            original_records = json.loads(bundle.read_bytes())['records']
            self.assertIn(observation['evidence_id'], {r['evidence_id'] for r in original_records})
            self.assertEqual(original_records, json.loads(restored.read_bytes())['records'])

    def test_release_comparison_and_sqlite_snapshot_in_one_connection(self):
        with tempfile.TemporaryDirectory(prefix='fusion release ') as td:
            project = Path(td)
            old, new = project / 'old.zip', project / 'new.zip'
            for file, entries in ((old, {'notice.txt': 'v1', 'removed.txt': 'old'}),
                                  (new, {'notice.txt': 'v2', 'added.txt': 'new'})):
                with zipfile.ZipFile(file, 'w') as archive:
                    for name, value in entries.items():
                        archive.writestr(name, value)
            db_path, backup = project / 'live.db', project / 'backup.db'
            writer = sqlite3.connect(db_path)
            target = sqlite3.connect(backup)
            try:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('CREATE TABLE live_entries(id INTEGER PRIMARY KEY)')
                writer.execute('INSERT INTO live_entries VALUES (42)')
                writer.commit()
                writer.backup(target)
                with self.mcp(project) as client:
                    client.initialize()
                    changes = self.call(client, 'field_compare_files', first=str(old), second=str(new))
                    self.assertEqual((changes['added'], changes['removed'], changes['changed']),
                                     (['added.txt'], ['removed.txt'], ['notice.txt']))
                    live = client.request('tools/call', {'name': 'field_observe', 'arguments': {'path': str(db_path)}})
                    self.assertTrue(live['isError'])
                    self.assertIn('WAL', live['structuredContent']['error']['message'])
                    observed = self.call(client, 'field_observe', path=str(backup))
                    self.assertEqual([entry['name'] for entry in observed['facts']['schema']], ['live_entries'])
                    native = self.call(client, 'inspect_sqlite_database', path=str(backup), table='live_entries')
                    self.assertIn('evidence_id', native)
                    self.assertIn('normalized_result', native)
            finally:
                target.close()
                writer.close()

    def test_independent_output_error_is_detected_before_fix(self):
        with tempfile.TemporaryDirectory(prefix='fusion compare ') as td:
            project = Path(td)
            reference, candidate = project / 'r.txt', project / 'c.txt'
            # Run separate implementations, with the same input, outside the server.
            args = ['0', '', '7']
            def run_source(source, output):
                completed = subprocess.run([sys.executable, '-I', '-c', source, *args],
                                           cwd=project, capture_output=True, timeout=10, check=True)
                output.write_bytes(completed.stdout)
            run_source('import sys; print("unknown" if "" in sys.argv[1:] else sum(map(int, sys.argv[1:])))', reference)
            run_source('import sys; print(sum(int(v or 0) for v in sys.argv[1:]))', candidate)
            with self.mcp(project) as client:
                client.initialize()
                def compare():
                    return self.call(client, 'fusion_compare_outputs', reference=str(reference), candidate=str(candidate))
                self.assertFalse(compare()['bytes_equal'])
                run_source('import sys; rows = sys.argv[1:]; print(sum(map(int, rows)) if all(rows) else "unknown")', candidate)
                self.assertTrue(compare()['bytes_equal'])
                self.assertFalse(compare()['execution_observed'])
                error = client.request('tools/call', {'name': 'fusion_compare_outputs', 'arguments': {
                    'reference': str(reference), 'candidate': str(reference)}})
                self.assertTrue(error['isError'])


if __name__ == '__main__':
    unittest.main()
