"""Preserved domain readers must get a real, current installation path index."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from rea_enhanced.providers import providers
from rea_enhanced.storage import read,write
from rea_enhanced.health import inspect

ROOT=Path(__file__).resolve().parents[1]


class Inventory(unittest.TestCase):
    def test_refresh_generates_current_index_without_fabricated_readiness(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            selected=providers(root,refresh=True,overrides={'REA_BROWSER_EXECUTABLE':sys.executable})
            inventory=read(root/'skills/tool-index.json')
            self.assertEqual(inventory['repository_root'],str(root))
            self.assertEqual(inventory['paths']['REA_BROWSER_EXECUTABLE'],str(Path(sys.executable).resolve()))
            self.assertIn('actual provider calls',inventory['qualification'])
            self.assertNotIn('ready',inventory)
            self.assertTrue((root/'skills/tool-index.md').is_file())

    def test_missing_node_binding_makes_core_doctor_incomplete(self):
        from reverse_fusion.runtime import node_runtime
        node,_=node_runtime(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            write(root/'vendor/rea/manifest.json',{'method_files_sha256':{},'package':'owned-health-fixture','version':'test'})
            entry=root/'vendor/rea/package/scripts/rea.mjs';entry.parent.mkdir(parents=True);entry.write_text('fixture',encoding='utf-8')
            write(root/'components/rea-enhanced/provider-bindings.json',{'binding_sha256':'0'*64})
            with patch('rea_enhanced.health.node_runtime',return_value=(node,'owned-test')):
                result=inspect(root)
            self.assertEqual(result['status'],'incomplete')
            self.assertTrue(any('Frida binding' in failure for failure in result['failures']))


if __name__=='__main__':unittest.main()
