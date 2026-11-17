"""Archive traversal/link rejection protects the independent installation root."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile
from rea_enhanced.bootstrap import extract, verify_rea_archive, acquire


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

    def test_unmodified_entry_cannot_hide_missing_execution_module(self):
        archive=self.root/'rea.tar'
        with tarfile.open(archive,'w') as source:
            for name,data in [('package/scripts/rea.mjs',b'entry'),('package/dist/runtime.js',b'actual runtime')]:
                entry=tarfile.TarInfo(name);entry.size=len(data);source.addfile(entry,io.BytesIO(data))
        extract(archive,self.root/'vendor/rea')
        self.assertEqual(verify_rea_archive(self.root,archive),[])
        (self.root/'vendor/rea/package/dist/runtime.js').unlink()
        self.assertEqual(verify_rea_archive(self.root,archive),['package/dist/runtime.js'])

    def test_transient_tls_eof_retries_without_accepting_partial_download(self):
        import hashlib,urllib.error,ssl
        from unittest.mock import patch
        data=b'complete authenticated asset'
        with patch('urllib.request.urlopen',side_effect=[urllib.error.URLError(ssl.SSLEOFError('observed transient EOF')),io.BytesIO(data)]) as download, patch('rea_enhanced.bootstrap.time.sleep'):
            result=acquire('https://example.invalid/pinned',self.root/'asset.zip',expected=hashlib.sha256(data).hexdigest())
        self.assertEqual(download.call_count,2)
        self.assertEqual(result.read_bytes(),data)
        self.assertFalse((self.root/'asset.zip.partial').exists())

    def test_explicit_archive_transfer_still_rejects_mismatched_bytes(self):
        import hashlib
        from unittest.mock import patch
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'wrong archive')) as download:
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                acquire('https://example.invalid/pinned',self.root/'asset.zip',expected=hashlib.sha256(b'expected archive').hexdigest())
        request=download.call_args.args[0]
        self.assertEqual(request.get_header('Accept-encoding'),'identity')
        self.assertIn('Reverse-Fusion',request.get_header('User-agent'))
        self.assertEqual(download.call_count,1)
        self.assertFalse((self.root/'asset.zip').exists())
        self.assertFalse((self.root/'asset.zip.partial').exists())


if __name__=='__main__':unittest.main()
