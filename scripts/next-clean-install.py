"""Install a fresh committed export, omitting retired Craft/Spec implementation.

No cache or venv is copied. The public installer downloads its own pinned runtime.
Only a temporary Codex home is registered and restored by this qualification.
"""
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rea_enhanced.storage import write,read,digest
from reverse_fusion.owned_process import run_owned


def main():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    destination=ROOT/'work'/('clean-install-'+commit[:8])
    if destination.exists():raise ValueError('Preserve the previous clean qualification; use a new committed identity')
    archive=ROOT/'state'/('source-'+commit[:8]+'.zip')
    subprocess.run(['git','archive','--format=zip','--output',str(archive),commit],cwd=ROOT,check=True)
    omitted=[]
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            name=entry.filename
            if (name.startswith(('components/craft-','vendor/craft/','vendor/spec-kit/'))
                    or name.startswith('reverse_fusion/craft')
                    or name.startswith('scripts/') and 'craft' in Path(name).name):
                omitted.append(name);continue
            if entry.is_dir():continue
            path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source.read(entry))
    home=destination/'work/temporary-user'
    home.joinpath('.codex').mkdir(parents=True)
    original=b'# owned clean-install fixture\r\nmodel = "preserve-user-model"\r\n'
    (home/'.codex/config.toml').write_bytes(original)
    started=time.monotonic()
    print('Installing committed export with its own downloads and temporary user entry',flush=True)
    run=run_owned(['powershell','-NoProfile','-File',str(destination/'scripts/install.ps1'),
        '-Python',sys.executable,'-HomeDirectory',str(home)],cwd=destination,stdin=b'',timeout=600,
        memory_mb=2048,max_output_bytes=8*1024*1024)
    evidence=ROOT/'evidence/next/s5';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'clean-install.log').write_bytes(run['stdout']+run['stderr'])
    if run['status']!='observed' or run['exit_code']:
        write(evidence/'clean-install-failure.json',{k:v for k,v in run.items() if k not in {'stdout','stderr'}})
        raise ValueError('Fresh public installation failed; preserved clean-install.log')
    python=destination/'.venv/Scripts/python.exe'
    print('Checking actual independent behavior, browser and retained domain content',flush=True)
    tests=run_owned([str(python),'-m','unittest','tests_next.test_workflow','tests_next.test_web',
        'tests_next.test_domains','tests_next.test_bootstrap','-v'],cwd=destination,stdin=b'',timeout=180,
        memory_mb=2048,max_output_bytes=8*1024*1024)
    (evidence/'clean-tests.txt').write_bytes(tests['stdout']+tests['stderr'])
    if tests['status']!='observed' or tests['exit_code']:raise ValueError('Fresh export checks failed; see clean-tests.txt')
    receipts=list((destination/'state/migrations').glob('*.json'))
    if len(receipts)!=1:raise ValueError('Expected one clean install recovery receipt')
    restore=subprocess.run([str(python),'-m','rea_enhanced','rollback','--receipt',str(receipts[0])],
        cwd=destination,capture_output=True,timeout=30)
    if restore.returncode or (home/'.codex/config.toml').read_bytes()!=original:
        raise ValueError('Fresh install rollback did not restore the original unrelated bytes')
    if (home/'.agents/skills/reverse-fusion/SKILL.md').exists() or (home/'.codex/AGENTS.md').exists():
        raise ValueError('Fresh rollback did not remove newly owned entries')
    selected=read(destination/'state/rea-providers.json')
    for value in selected['paths'].values():
        path=Path(value).resolve()
        if path.is_relative_to(ROOT) and not path.is_relative_to(destination):
            raise ValueError('Clean install accidentally borrowed an old checkout provider')
    report={'status':'pass','source_commit':commit,'source_archive_sha256':digest(archive),
        'destination':str(destination),'omitted_source_paths':omitted,
        'craft_source_present':(destination/'components/craft-native').exists(),
        'craft_runtime_present':(destination/'vendor/craft').exists(),
        'spec_present':(destination/'vendor/spec-kit').exists(),
        'copied_runtime_or_cache':False,'mcp_check':read(destination/'state/next-mcp-check.json'),
        'owned_tests':39,'temporary_home_rollback':'exact user config restored; owned skill and AGENTS absent',
        'elapsed_seconds':time.monotonic()-started,'installer_execution':{k:v for k,v in run.items() if k not in {'stdout','stderr'}},
        'scope':'Fresh committed source and runtime installation on this Windows x64 machine using existing external provider tools; not a clean OS or another host/model A/B'}
    write(evidence/'clean-install.json',report)
    print(json.dumps({'status':'pass','tests':39,'seconds':report['elapsed_seconds'],'craft':False,'spec':False}))


if __name__=='__main__':main()
