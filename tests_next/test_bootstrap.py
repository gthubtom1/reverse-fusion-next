"""Archive traversal/link rejection protects the independent installation root."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile
from rea_enhanced.bootstrap import extract


class ArchiveSafety(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_zip_escape_rejected_before_any_write(self):
        archive=self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as source:
            source.writestr('good.txt',b'ok');source.writestr('../outside',b'bad')
        with self.assertRaises(ValueError):extract(archive,self.root/'out')
        self.assertFalse((self.root/'out/good.txt').exists())
        self.assertFalse((self.root/'outside').exists())

    def test_tar_symlink_rejected_before_writes(self):
        archive=self.root/'bad.tar'
        with tarfile.open(archive,'w') as source:
            entry=tarfile.TarInfo('link');entry.type=tarfile.SYMTYPE;entry.linkname='../outside';source.addfile(entry)
        with self.assertRaises(ValueError):extract(archive,self.root/'out')
        self.assertFalse((self.root/'out').exists())

    def test_safe_archive_extracts_to_selected_root(self):
        archive=self.root/'good.tar'
        with tarfile.open(archive,'w') as source:
            entry=tarfile.TarInfo('package/nested.txt');entry.size=4;source.addfile(entry,io.BytesIO(b'data'))
        extract(archive,self.root/'out')
        self.assertEqual((self.root/'out/package/nested.txt').read_bytes(),b'data')


if __name__=='__main__':unittest.main()
