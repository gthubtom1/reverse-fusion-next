"""Qualify the independent public repository with its actual default clone/install path."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rea_enhanced.storage import read,write
from rea_enhanced.qualification import source_identity
from reverse_fusion.owned_process import run_owned

REPOSITORY='https://github.com/gthubtom1/reverse-fusion-next.git'


def execute(argv,cwd,timeout,log):
    result=run_owned(argv,cwd=cwd,stdin=b'',timeout=timeout,memory_mb=2048,max_output_bytes=8*1024*1024)
    log.write_bytes(result['stdout']+result['stderr'])
    write(log.with_suffix('.execution.json'), {k:v for k,v in result.items() if k not in {'stdout','stderr'}})
    if result['status']!='observed' or result['exit_code']:
        raise ValueError('Remote qualification step failed: '+str(log))
    return result


def qualify(destination):
    evidence=ROOT/'evidence/next/final-audit';evidence.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    env=dict(os.environ);env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='Never')
    clone_root=destination
    clone_log=b''
    for attempt in range(3):
        destination=clone_root/('checkout-'+str(attempt+1))
        clone=subprocess.run(['git','-c','http.version=HTTP/1.1','clone','--single-branch',REPOSITORY,str(destination)],
            cwd=ROOT,capture_output=True,timeout=180,env=env)
        clone_log+=clone.stdout+clone.stderr
        (evidence/'remote-clone.log').write_bytes(clone_log)
        if clone.returncode==0:break
        if attempt==2:raise ValueError('Independent remote clone failed after three bounded attempts')
        time.sleep(attempt+1)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=destination,text=True).strip()
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=destination,text=True).strip()
    if branch!='main':raise ValueError('Unexpected default branch: '+branch)
    source=source_identity(destination)
    if source!=source_identity(ROOT):raise ValueError('Remote source/contracts differ from the source under qualification')
    home=destination/'work/temporary-user';home.joinpath('.codex').mkdir(parents=True)
    original=b'# public-clone user fixture\r\nmodel = "preserve-user-model"\r\n'
    (home/'.codex/config.toml').write_bytes(original)
    print('Installing the actual independent remote clone through its public installer',flush=True)
    installed=execute(['powershell','-NoProfile','-File',str(destination/'scripts/install.ps1'),
        '-Python',sys.executable,'-HomeDirectory',str(home)],destination,1200,evidence/'remote-install.log')
    python=destination/'.venv/Scripts/python.exe'
    print('Running the complete current suite from the clone, including real MCP and browser operations',flush=True)
    execute([str(python),str(destination/'scripts/next-qualify.py')],destination,300,evidence/'remote-tests.log')
    receipts=[p for p in (destination/'state/migrations').glob('*.json')
        if read(p)['files']['config']['path']==str(home/'.codex/config.toml') and read(p)['status']=='installed']
    if len(receipts)!=1:raise ValueError('Expected one public-install recovery receipt')
    execute([str(python),'-m','rea_enhanced','rollback','--receipt',str(receipts[0])],destination,30,evidence/'remote-rollback.log')
    if ((home/'.codex/config.toml').read_bytes()!=original or (home/'.codex/AGENTS.md').exists()
            or (home/'.agents/skills/reverse-fusion/SKILL.md').exists()):
        raise ValueError('Public clone rollback did not exactly restore original user fixture')
    providers=read(destination/'state/rea-providers.json')
    for value in providers['paths'].values():
        path=Path(value).resolve()
        if path.is_relative_to(ROOT) and not path.is_relative_to(destination):
            raise ValueError('Clone borrowed a managed provider from development checkout')
    if list((destination/'vendor/craft').rglob('*.exe')) or (destination/'vendor/spec-kit/upstream').exists():
        raise ValueError('Unexpected Craft/Spec runtime acquisition')
    if source_identity(destination)!=source:raise ValueError('Public source/contracts changed during installation')
    qualified=read(destination/'evidence/next/s6/engineering-tests.json')
    report={'status':'pass','repository':REPOSITORY,'default_branch':branch,'source_commit':commit,
        'source_method':'git-clone-remote','source_identity':source,'destination':str(destination),
        'copied_runtime_or_cache':False,'full_default_clone':True,'tests':qualified['tests'],
        'mcp_check':read(destination/'state/next-mcp-check.json'),
        'selected_provider_paths':providers,'temporary_user_rollback':'exact original config; new skill and AGENTS absent',
        'craft_runtime_acquired':False,'spec_runtime_acquired':False,'elapsed_seconds':time.monotonic()-started,
        'installer_execution':{k:v for k,v in installed.items() if k not in {'stdout','stderr'}},
        'scope':'Actual public default clone, new checkout/venv/download cache and temporary user install on this Windows x64 machine. Existing external OS providers remain discoverable; not a clean OS or another host model.'}
    write(evidence/'remote-install.json',report)
    print(json.dumps({'status':'pass','source_commit':commit,'tests':report['tests'],'seconds':report['elapsed_seconds']}))


def main():
    from rea_enhanced.disk import reserved_space, GiB
    work=(ROOT/'work').resolve();work.mkdir(parents=True,exist_ok=True)
    cleanup={}
    destination=None
    try:
        with reserved_space(ROOT, GiB):
            with tempfile.TemporaryDirectory(prefix='remote-install-',dir=work) as selected:
                destination=Path(selected).resolve()
                if destination.parent!=work or not destination.is_relative_to(ROOT.resolve()):
                    raise ValueError('Temporary clone must remain within the selected checkout work directory')
                try:
                    qualify(destination)
                finally:
                    total=count=0
                    skipped=[]
                    for base,dirs,files in os.walk(destination,followlinks=False):
                        kept=[]
                        for name in dirs:
                            p=Path(base)/name
                            if p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&1024:
                                skipped.append(str(p));continue
                            kept.append(name)
                        dirs[:]=kept
                        for name in files:
                            p=Path(base)/name
                            if p.is_symlink() or getattr(p.lstat(),'st_file_attributes',0)&1024:
                                skipped.append(str(p));continue
                            total+=p.stat().st_size;count+=1
                    cleanup.update(path=str(destination),logical_file_bytes=total,files=count,skipped_links=skipped)
    finally:
        if destination is not None:
            cleanup['path_absent_after_cleanup']=not destination.exists()
            write(ROOT/'evidence/next/disk-lifecycle/public-install-cleanup.json',cleanup)
    report_path=ROOT/'evidence/next/final-audit/remote-install.json'
    report=read(report_path)
    if destination.exists():raise ValueError('New owned installation checkout was not reclaimed')
    report.update(destination_retained=False,
        cleanup=cleanup,
        temporary_cleanup='New exclusively owned temporary checkout removed after actual qualification and exact rollback; old checkouts untouched')
    write(report_path,report)
    print('New temporary installation checkout reclaimed; qualification receipts retained',flush=True)


if __name__=='__main__':main()
