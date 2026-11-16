"""Owned configuration byte preservation and transactional migration regressions."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rea_enhanced.deployment import install,rollback,_paths,_mcp_region
from rea_enhanced.storage import read

ROOT=Path(__file__).resolve().parents[1]


class Deployment(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.paths=_paths(self.home)
        self.paths['config'].parent.mkdir(parents=True)
        self.config=b'# user comment\r\nmodel = "retained"\r\n[mcp_servers.user]\r\ncommand = "unrelated"\r\n'
        self.agents='用户原有指引\r\n'.encode()
        self.paths['config'].write_bytes(self.config);self.paths['agents'].write_bytes(self.agents)

    def test_real_registered_server_and_owned_rollback(self):
        result=install(ROOT,self.home)
        self.assertEqual(result['mcp_check']['status'],'pass')
        self.assertEqual(result['mcp_check']['server']['name'],'rea-enhanced')
        self.assertEqual(result['mcp_check']['tools'],259)
        receipt=read(Path(result['rollback_receipt']))
        self.assertNotIn(b'retained',base64.b64decode(receipt['files']['config']['before']))
        # User adds content after install: rollback must retain these new bytes too.
        extra=b'\n# new user comment\n'
        for name in ('agents','config'):
            with self.paths[name].open('ab') as stream:stream.write(extra)
        rollback(result['rollback_receipt'],ROOT)
        self.assertEqual(self.paths['config'].read_bytes(),self.config+extra)
        self.assertEqual(self.paths['agents'].read_bytes(),self.agents+extra)
        self.assertFalse(self.paths['skill'].exists())

    def test_migrate_legacy_two_servers_then_restore_exact_owned_sections(self):
        from reverse_fusion.global_adapter import install_global_adapter
        from reverse_fusion.mcp_adapter import _render,_registrations
        previous=ROOT.parent/'reverse'
        install_global_adapter(previous,self.home)
        self.paths['config'].write_bytes(self.config+_render(previous,_registrations(previous),separator=0,original_existed=True))
        before={k:p.read_bytes() for k,p in self.paths.items()}
        with self.assertRaises(ValueError):install(ROOT,self.home,check=False)
        result=install(ROOT,self.home,replace_from=previous,check=False)
        self.assertNotIn(b'[mcp_servers.reverse-fusion-craft]',self.paths['config'].read_bytes())
        rollback(result['rollback_receipt'],ROOT)
        self.assertEqual({k:p.read_bytes() for k,p in self.paths.items()},before)

    def test_probe_failure_restores_and_retains_unrelated_edit(self):
        def failed(*args):
            with self.paths['config'].open('ab') as stream:stream.write(b'\n# concurrent user addition\n')
            raise TimeoutError('owned injected connection failure')
        with patch('rea_enhanced.deployment.probe',side_effect=failed):
            with self.assertRaisesRegex(ValueError,'previous owned entries restored'):install(ROOT,self.home)
        self.assertEqual(self.paths['config'].read_bytes(),self.config+b'\n# concurrent user addition\n')
        self.assertEqual(self.paths['agents'].read_bytes(),self.agents)
        self.assertFalse(self.paths['skill'].exists())

    def test_unmanaged_conflict_is_not_overwritten(self):
        self.paths['config'].write_bytes(self.config+b'\n[mcp_servers.reverse-fusion-rea]\ncommand = "user"\n')
        before=self.paths['config'].read_bytes()
        with self.assertRaises(ValueError):install(ROOT,self.home,check=False)
        self.assertEqual(self.paths['config'].read_bytes(),before)
        self.assertFalse(self.paths['skill'].exists())

    def test_modified_owned_entry_refuses_rollback(self):
        result=install(ROOT,self.home,check=False)
        self.paths['skill'].write_text('user replaced this skill',encoding='utf-8')
        before=self.paths['config'].read_bytes()
        with self.assertRaises(ValueError):rollback(result['rollback_receipt'],ROOT)
        self.assertEqual(self.paths['config'].read_bytes(),before)

    def test_interrupted_prepared_transaction_can_be_recovered(self):
        with patch('rea_enhanced.deployment.probe',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):install(ROOT,self.home)
        receipts=[path for path in (ROOT/'state/migrations').glob('*.json')
            if read(path)['files']['config']['path']==str(self.paths['config'])]
        self.assertEqual(len(receipts),1)
        self.assertEqual(read(receipts[0])['status'],'prepared')
        rollback(receipts[0],ROOT)
        self.assertEqual(self.paths['config'].read_bytes(),self.config)
        self.assertEqual(self.paths['agents'].read_bytes(),self.agents)
        self.assertFalse(self.paths['skill'].exists())

    def test_reserialized_legacy_comments_require_explicit_exact_adoption(self):
        from reverse_fusion.global_adapter import install_global_adapter
        from reverse_fusion.mcp_adapter import _render,_registrations
        previous=ROOT.parent/'reverse'
        install_global_adapter(previous,self.home)
        raw=_render(previous,_registrations(previous),separator=0,original_existed=True)
        for mode in ('absent','adjacent','moved-to-eof'):
            with self.subTest(marker_mode=mode):
                lines=[line for line in raw.splitlines(keepends=True)
                    if not line.startswith(b'# reverse-fusion:mcp:') or mode=='adjacent' and line.strip()==b'# reverse-fusion:mcp:end']
                suffix=b'\n[mcp_servers.extra]\ncommand = "unrelated-after"\n'
                if mode=='moved-to-eof':suffix+=b'\n# reverse-fusion:mcp:end\n'
                value=self.config+b''.join(lines)+suffix
                self.paths['config'].write_bytes(value)
                with self.assertRaises(ValueError):install(ROOT,self.home,check=False)
                result=install(ROOT,self.home,replace_from=previous,check=False)
                rollback(result['rollback_receipt'],ROOT)
                self.assertEqual(self.paths['config'].read_bytes(),value)

    def test_codex_reserialized_enhanced_entry_still_connects_and_rolls_back(self):
        import tomllib
        from rea_enhanced.deployment import probe
        result=install(ROOT,self.home,check=False)
        payload=self.paths['config'].read_bytes()
        rewritten=b''.join(line for line in payload.splitlines(keepends=True)
            if not line.startswith(b'# reverse-fusion:mcp:'))
        self.paths['config'].write_bytes(rewritten)
        self.assertEqual(probe(ROOT,self.home)['status'],'pass')
        rollback(result['rollback_receipt'],ROOT)
        parsed=tomllib.loads(self.paths['config'].read_text(encoding='utf-8'))
        self.assertEqual(parsed['mcp_servers'],{'user':{'command':'unrelated'}})
        self.assertEqual(parsed['model'],'retained')


if __name__=='__main__':unittest.main()
