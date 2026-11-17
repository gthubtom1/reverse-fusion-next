"""Run the current checks and bind actual operation receipts to tested source/contracts."""
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rea_enhanced.qualification import source_identity
from rea_enhanced.storage import write,digest


def main():
    # Preserve readable output in Windows pipes regardless of the legacy console code page.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    before=source_identity(ROOT);started=time.monotonic()
    run=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests_next','-v'],
        cwd=ROOT,capture_output=True,timeout=240)
    output=run.stdout+run.stderr
    destination=ROOT/'evidence/next/s6';destination.mkdir(parents=True,exist_ok=True)
    (destination/'engineering-tests.txt').write_bytes(output)
    after=source_identity(ROOT)
    operations=['evidence/next/s2/protocol-qualified.json',
        'evidence/next/tiered-storage/live-proof.json',
        'evidence/next/final-audit/native-provider.json',
        'evidence/next/s2/native-restart-qualified.json',
        *('evidence/next/final-audit/web-'+name+'.json' for name in
          ('equal','wrong-behavior','wrong-look','missing-observation','controls'))]
    count=re.search(rb'Ran (\d+) tests?',output)
    report={'status':'pass' if run.returncode==0 and before==after else 'fail',
        'exit_code':run.returncode,'tests':int(count[1]) if count else None,
        'source_unchanged_during_tests':before==after,'source_identity':after,
        'evidence_sha256':{p:digest(ROOT/p) for p in operations},
        'elapsed_seconds':time.monotonic()-started,
        'scope':'Actual current unittest discovery, original protocol/provider operations, finite behavior/visual cases and negative cases. Tests and public contracts are bound. Not arbitrary target acceptance.'}
    write(destination/'engineering-tests.json',report)
    print(output.decode('utf-8',errors='replace')[-3000:])
    print({'status':report['status'],'tests':report['tests']})
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
