"""Reclaim only the explicit inactive materials named in the restart handoff."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import time
import psutil

ROOT = Path('D:/Project/reverse-next')
EVIDENCE = ROOT/'evidence/next/slim'
AREA = Path('D:/tmp/reverse-next-slim-55fuatfp')
TARGETS = [AREA/'source', AREA/'temp', AREA/'coordinator',
    Path('D:/tmp/reverse-slim-native-foo2sqex'),
    Path('D:/tmp/reverse-slim-rollback-_cv0dlk5'),
    Path('D:/tmp/reverse-slim-rollback-bdvwfz06'),
    EVIDENCE/'coordinator-baseline', EVIDENCE/'coordinator-candidate']
sys.path.insert(0, str(ROOT))
from rea_enhanced.qualification import source_identity

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def census(path):
    total = count = 0
    if not path.exists():
        return {'files': 0, 'bytes': 0, 'existed': False}
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in [*dirs, *files]:
            p = Path(base)/name
            if p.is_symlink() or getattr(p.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Preserve linked/reparse material for inspection: '+str(p))
        for name in files:
            total += (Path(base)/name).stat().st_size
            count += 1
    return {'files': count, 'bytes': total, 'existed': True}

before_source = source_identity(ROOT)
qualification = json.loads((EVIDENCE/'regressions.json').read_text(encoding='utf-8'))
assert before_source == qualification['source_identity']
assert qualification['tests'] == 179 and not qualification['failures'] and not qualification['errors']
for name, checksum in qualification['evidence_sha256'].items():
    assert sha(EVIDENCE/name) == checksum
archive = ROOT/'state/slim-baseline-20261118/repaired-source.zip'
assert sha(archive) == '257c7fb8e90d38f0dc012e0621e181b2bb55295313a75e8b2f5e8498532a4e52'
entries = json.loads((EVIDENCE/'deployment-preservation.json').read_text())['before']
assert all(sha(Path(name)) == checksum for name, checksum in entries.items())
protected = {p.relative_to(EVIDENCE).as_posix(): sha(p) for p in EVIDENCE.rglob('*')
    if p.is_file() and not any(p.is_relative_to(t) for t in TARGETS)}
# Process inventory is observational. Exclude this script's own parent shells, never other sessions.
ignored = {os.getpid(), *(p.pid for p in psutil.Process().parents())}
for process in psutil.process_iter(['pid', 'cmdline', 'cwd']):
    if process.pid in ignored:
        continue
    try:
        info = process.info
        text = (' '.join(info.get('cmdline') or [])+' '+str(info.get('cwd') or '')).replace(chr(92), '/').lower()
        if any(p.as_posix().lower() in text for p in TARGETS) or 'state/slim-tests.py' in text:
            raise ValueError('Preserve test materials while process uses them: '+str(process.pid))
    except psutil.NoSuchProcess:
        pass
    # AccessDenied aborts rather than pretending all processes were inspected.
for path in [AREA/'coordinator', EVIDENCE/'coordinator-baseline', EVIDENCE/'coordinator-candidate']:
    for file in path.glob('*.json'):
        assert not json.loads(file.read_text())['reservations']
rows = [{'path': str(path), **census(path)} for path in TARGETS]
print(json.dumps({'status': 'inspected', 'targets': rows}), flush=True)
receipt = {'date': '2026-11-18', 'status': 'prepared', 'targets': rows,
    'scope': 'Logical bytes/files of explicit owned inactive test copies only, not allocated disk space.',
    'process_check': 'psutil command/cwd inventory; no matching process; no AccessDenied ignored',
    'archive_retained': str(archive), 'archive_sha256': sha(archive),
    'evidence_files_protected': len(protected), 'source_files_protected': len(before_source)}
output = EVIDENCE/'cleanup.json'
if output.exists():
    raise ValueError('Preserve previous cleanup receipt')
output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
try:
    for path, row in zip(TARGETS, rows):
        if path.exists():
            shutil.rmtree(path)
        row['absent_after'] = not path.exists()
    assert source_identity(ROOT) == before_source
    assert sha(archive) == receipt['archive_sha256']
    assert all(sha(EVIDENCE/name) == checksum for name, checksum in protected.items())
    assert all(sha(Path(name)) == checksum for name, checksum in entries.items())
    receipt.update(status='pass', reclaimed_logical_bytes=sum(row['bytes'] for row in rows),
        reclaimed_files=sum(row['files'] for row in rows), source_unchanged=True,
        protected_evidence_unchanged=True, user_entries_unchanged=True,
        preserved_small_test_reports=str(AREA), finished_epoch=time.time())
except BaseException as exc:
    receipt.update(status='incomplete', reason=str(exc))
    raise
finally:
    output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
print(json.dumps(receipt), flush=True)
