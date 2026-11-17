"""Changing a test, public workflow or actual operation receipt invalidates qualification."""
from pathlib import Path
import tempfile
import unittest
from rea_enhanced.qualification import source_identity

ROOT=Path(__file__).resolve().parents[1]


class Qualification(unittest.TestCase):
    def test_test_and_public_contract_edits_change_release_identity(self):
        before=source_identity(ROOT)
        for target in ('tests_next/test_final_audit.py','docs/AGENT-WORKFLOW.md','components/reverse-core/runtime.json','scripts/install.ps1'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as td:
                root=Path(td)
                for name in before:
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
                    p.write_bytes((ROOT/name).read_bytes())
                self.assertEqual(source_identity(root),before)
                with (root/target).open('ab') as stream:stream.write(b'\nchanged contract\n')
                self.assertNotEqual(source_identity(root),before)


if __name__=='__main__':unittest.main()
