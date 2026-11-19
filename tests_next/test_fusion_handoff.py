"""Exercise evidence handoff and the trusted finite replay entry point."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from reverse_fusion.mcp_probe import StdioMcp
from tests_next.test_fusion_integration import ROOT, hosts, kit, layout

SAMPLE_ROOT = ROOT / 'state/aotopsy-sample-20261118-1ygfiX/results/comparison'
SAMPLES = {f'FixtureShelfV{n}': SAMPLE_ROOT / f'v{n}/libapp.so' for n in (1, 2)}


def write_json(path, value):
    path.write_text(json.dumps(value), encoding='ascii')


def replay(project, output, *flags):
    return invoke_replay([sys.executable, '-I', str(ROOT / 'fusion.py'), 'replay'], project, output, *flags)


def invoke_replay(argv_prefix, project, output, *flags):
    return subprocess.run([*argv_prefix, '--project-root', str(project), '--plan', 'plan.json',
                           '--output', output, *flags], cwd=project, capture_output=True, timeout=60)


def call(client, name, **arguments):
    response = client.request('tools/call', {'name': name, 'arguments': arguments})
    if response.get('isError'):
        raise AssertionError(response)
    return response['structuredContent']


class FusionHandoff(unittest.TestCase):
    def test_replay_requires_trusted_programs_and_finite_plan(self):
        with tempfile.TemporaryDirectory(prefix='fusion limited ') as td:
            project = Path(td)
            write_json(project / 'plan.json', {'kind': 'web'})
            untrusted = replay(project, 'result')
            self.assertEqual(untrusted.returncode, 2)
            self.assertIn(b'Use --trusted-local', untrusted.stderr)
            wrong_mode = replay(project, 'result', '--trusted-local')
            self.assertEqual(wrong_mode.returncode, 2)
            self.assertIn('finite local replay', json.loads(wrong_mode.stdout)['message'])
            self.assertFalse((project / 'result').exists())

    def test_methods_are_selected_and_sourced(self):
        topics = {m['topic'] for m in kit['read_method']({})['topics']}
        self.assertIn('forensics', topics)
        for topic in topics:
            with self.subTest(topic=topic):
                method = kit['read_method']({'topic': topic})
                self.assertEqual(method['sha256'], sha256((ROOT / method['file']).read_bytes()).hexdigest())
                self.assertTrue(method['text'])
        self.assertEqual(kit['read_method']({'topic': 'forensics'})['source'], 'Reverse Skills')
        with self.assertRaises(ValueError):
            kit['read_method']({'topic': '../service.py'})

    def test_conflicting_or_unavailable_official_identity_never_binds(self):
        specialty = {'file': {'sha256': 'a' * 64}, 'status': 'observed', 'classes': []}
        official = {'structuredContent': {'operation': 'inspect_elf_notes', 'evidence_id': 'native-id',
                                         'subject': {'digest': {'sha256': 'b' * 64}}}}
        with patch.object(kit['field']['flutter_inventory'], 'observe', return_value=specialty):
            args = {'path': str(ROOT / 'local.so')}
            report = kit['observe_flutter'](args, lambda *_: official)
            self.assertIs(report['same_input'], False)
            self.assertEqual(report['official'], official)
            report = kit['observe_flutter'](args, lambda *_: {'isError': True})
            self.assertIsNone(report['same_input'])

            def disconnected(*_):
                raise OSError('connection closed')

            report = kit['observe_flutter'](args, disconnected)
            self.assertIsNone(report['same_input'])
            self.assertEqual(report['official_issue'], 'connection closed')
            self.assertEqual(report['specialty'], specialty)

    @unittest.skipUnless(os.name == 'nt' and all(p.is_file() for p in SAMPLES.values()),
                         'needs the two locally built synthetic Windows test inputs')
    def test_local_artifacts_to_corrected_export_and_resumed_evidence(self):
        with tempfile.TemporaryDirectory(prefix='fusion handoff ') as td:
            project = Path(td)
            bundle = project / 'official.json'
            request = 'Identify the library of each selected class and verify the class-to-library export.'
            with StdioMcp(hosts['command'](layout), cwd=project, timeout=40) as client:
                client.initialize()
                method = call(client, 'fusion_read_method', topic='source-identity')
                self.assertEqual(method['source'], 'Reverse Skills')
                rows, evidence_ids = [], set()
                for name, sample in SAMPLES.items():
                    local = project / name / 'app.so'
                    local.parent.mkdir()
                    raw = sample.read_bytes()
                    local.write_bytes(raw)
                    report = call(client, 'fusion_observe_flutter_library', path=str(local), query=name)
                    self.assertIs(report['same_input'], True)
                    self.assertEqual(report['runtime'], 'unobserved')
                    native = report['official']['structuredContent']
                    self.assertEqual(native['subject']['digest']['sha256'], sha256(raw).hexdigest())
                    self.assertIn('normalized_result', native)
                    evidence_ids.add(native['evidence_id'])
                    specialty = report['specialty']
                    self.assertEqual(specialty['status'], 'observed')
                    self.assertEqual([(row['class_name'], row['library_uri']) for row in specialty['classes']],
                                     [(name, f'package:reverse_fusion_aot_fixture/main_v{name[-1]}.dart')])
                    rows.extend(specialty['classes'])
                    write_json(local.parent / 'observation.json', specialty)
                call(client, 'export_evidence_bundle', path=str(bundle))
                self.assertEqual(evidence_ids, {r['evidence_id'] for r in json.loads(bundle.read_bytes())['records']})

                original = ('import json, sys\n'
                            'out = {}\n'
                            'for row in json.load(sys.stdin):\n'
                            '    out[row["class_name"]] = row["library_uri"]\n'
                            'print(json.dumps(out, sort_keys=True))\n')
                candidate = ('import json, sys\n'
                             'entries = json.load(sys.stdin)\n'
                             'exported = {item["class_name"]: item["class_name"] for item in entries}\n'
                             'print(json.dumps(exported, sort_keys=True))\n')
                config = {}
                for side, source in (('original', original), ('candidate', candidate)):
                    (project / side).mkdir()
                    (project / side / 'export.py').write_text(source, encoding='ascii')
                    config[side] = {'argv': [sys.executable, '-I', 'export.py'], 'cwd': side,
                                    'sources': [side + '/export.py']}
                write_json(project / 'plan.json', {
                    'version': 2, 'scope': 'Export a class-to-library map from two trusted inventories',
                    **config, 'timeout_seconds': 8,
                    'scenarios': [{'id': name, 'steps': [{'stdin': json.dumps(data), 'args': [],
                                                         'files': [], 'expected_exit_codes': [0]}]}
                                  for name, data in [('owned-classes', rows), ('empty', [])]],
                })
                method = call(client, 'fusion_read_method', topic='comparison')
                self.assertIn('Craft', method['source'])
                launch = method['local_replay']['argv_prefix']
                self.assertEqual(launch[-2:], [str(ROOT / 'fusion.py'), 'replay'])
                bad = invoke_replay(launch, project, 'before', '--trusted-local')
                self.assertEqual(bad.returncode, 1, bad.stdout + bad.stderr)
                before_path = project / 'before/comparison.json'
                before_bytes = before_path.read_bytes()
                before = json.loads(before_bytes)
                self.assertEqual([r['status'] for r in before['cases']], ['fail', 'pass'])
                self.assertEqual(before['cases'][0]['differences'], ['stdout'])
                candidate_path = project / 'candidate/export.py'
                candidate_path.write_text(candidate.replace(': item["class_name"]', ': item["library_uri"]'),
                                          encoding='ascii')
                fixed = replay(project, 'after', '--trusted-local')
                self.assertEqual(fixed.returncode, 0, fixed.stdout + fixed.stderr)
                self.assertEqual(before_path.read_bytes(), before_bytes)
                receipt = json.loads(fixed.stdout)
                self.assertFalse(receipt['official_rea_evidence'])
                after = json.loads((project / receipt['receipt']).read_bytes())
                self.assertEqual([r['status'] for r in after['cases']], ['pass', 'pass'])
                channel = after['cases'][0]['observations']['candidate']['stdout']
                self.assertEqual(json.loads((project / channel['snapshot']).read_bytes()),
                                 {row['class_name']: row['library_uri'] for row in rows})

                state = call(client, 'rf_next_case_open', project_root=str(project), recording='case', request=request)
                paths = [bundle.name, receipt['receipt'], 'before/comparison.json', 'plan.json', 'candidate/export.py',
                         'original/export.py', channel['snapshot']]
                paths.extend(f'{name}/{file}' for name in SAMPLES for file in ('app.so', 'observation.json'))
                call(client, 'rf_next_case_record', project_root=str(project), expected_revision=state['revision'],
                     change={'op': 'checkpoint', 'note': 'Export fixed; app runtime remains unobserved.',
                             'next_action': 'Check another input if requested.', 'paths': paths})
            with StdioMcp(hosts['command'](layout), cwd=project, timeout=40) as resumed:
                resumed.initialize()
                state = call(resumed, 'rf_next_case_open', project_root=str(project), request='continue')
                self.assertEqual(state['original_request'], request)
                self.assertTrue(state['checkpoint']['current_files'])
                self.assertEqual(set(state['checkpoint']['record']['files']), set(paths))
                call(resumed, 'import_evidence_bundle', path=str(bundle))
                restored = project / 'restored.json'
                call(resumed, 'export_evidence_bundle', path=str(restored))
                self.assertEqual(json.loads(bundle.read_bytes())['records'], json.loads(restored.read_bytes())['records'])
                candidate_path.write_bytes(candidate_path.read_bytes() + b'\n# new revision\n')
                state = call(resumed, 'rf_next_case_status', project_root=str(project))
                self.assertFalse(state['checkpoint']['current_files'])


if __name__ == '__main__':
    unittest.main()
