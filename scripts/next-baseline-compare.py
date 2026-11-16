"""Finite, like-for-like tool comparison; no claim about model intelligence."""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rea_enhanced.comparison import compare
from rea_enhanced.storage import read,write
from reverse_fusion.owned_process import run_owned


def main():
    baseline=read(ROOT/'baseline/identity.json');old=Path(baseline['source'])
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=old,text=True).strip()
    if head!=baseline['frozen_commit']:raise ValueError('Frozen baseline changed')
    before=subprocess.check_output(['git','status','--porcelain'],cwd=old)
    area=ROOT/'work/baseline-comparison'
    if area.exists():raise ValueError('Retain old comparison; choose a new named run')
    results=[]
    reference='import sys\nfrom pathlib import Path\nx=sys.stdin.read().strip().upper()\nPath("result.txt").write_text(x,encoding="utf-8")\nprint(x)\n'
    candidate='from pathlib import Path\nimport sys\ny="".join(sys.stdin.readlines()).strip()\nvalue=y.upper()\nPath("result.txt").write_text(value,encoding="utf-8")\nsys.stdout.write(value+"\\n")\n'
    for scenario,code,expected in [('correct',candidate,('pass','pass')),
        ('wrong-behavior',candidate.replace('value=y.upper()','value=y.lower()'),('fail','fail')),
        ('file-channel',candidate.replace('write_text(value,','write_text("wrong-state",'),('pass','fail'))]:
        project=area/scenario
        for side,source in [('original',reference),('candidate',code)]:
            folder=project/side;folder.mkdir(parents=True);(folder/'main.py').write_text(source,encoding='utf-8')
        sides={side:{'argv':[sys.executable,'main.py'],'cwd':side,'sources':[side+'/main.py']} for side in ('original','candidate')}
        inputs=[' aBc\n','  MiXeD words  \n','!Ab9\n']
        old_plan={'version':1,'scope':'Finite ASCII text normalization and declared streams',**sides,
            'cases':[{'id':'input-'+str(i),'stdin':text} for i,text in enumerate(inputs)],'timeout_seconds':3}
        write(project/'old-plan.json',old_plan)
        invoked=run_owned([str(old/'.venv/Scripts/python.exe'),'-m','reverse_fusion','compare',
            '--project-root',str(project),'--plan','old-plan.json','--output','work/v1'],cwd=old,
            stdin=b'',timeout=45,memory_mb=768,max_output_bytes=2*1024*1024)
        previous=read(project/'work/v1/comparison.json')
        new_plan={'version':2,'scope':'Same stream cases plus declared file output',**sides,
            'scenarios':[{'id':'input-'+str(i),'steps':[{'stdin':text,'args':[],'files':['result.txt'],
                'expected_exit_codes':[0]}]} for i,text in enumerate(inputs)],'timeout_seconds':3}
        # The new replay copies sources into fresh independent directories per scenario.
        # Retained file state from the old process-only run is not part of either source fixture.
        for side in sides:(project/side/'result.txt').unlink(missing_ok=True)
        write(project/'new-plan.json',new_plan)
        started=time.monotonic();current=compare(project,'new-plan.json','work/v2');elapsed=time.monotonic()-started
        if (previous['status'],current['status'])!=expected:raise ValueError('Unexpected paired result: '+scenario)
        results.append({'scenario':scenario,'baseline':previous,'enhanced':current,
            'cost':{'baseline_command':{k:v for k,v in invoked.items() if k not in {'stdout','stderr'}},
                'enhanced_wall_seconds':elapsed,'executions_each':6},
            'interpretation':'Extra explicit file channel; v1 promised streams only, so its pass is not whole-state acceptance' if scenario=='file-channel' else 'Shared stream behavior checked on the same owned inputs'})
    after=subprocess.check_output(['git','status','--porcelain'],cwd=old)
    if before!=after:raise ValueError('Original checkout status changed during read-only baseline run')
    report={'status':'pass','baseline_commit':head,'baseline_git_unchanged':True,'pairs':results,
        'scope':'Same owned finite stream scenarios and separate explicit file-channel extension',
        'not_measured':['model reasoning quality','success rate across arbitrary software','model token cost','all provider performance'],
        'cost_limit':'Single finite run; CLI startup/copy costs are included and are not a statistically stable speed benchmark'}
    write(ROOT/'evidence/next/s5/baseline-comparison.json',report)
    print(json.dumps({'status':'pass','results':[(r['scenario'],r['baseline']['status'],r['enhanced']['status']) for r in results]}))


if __name__=='__main__':main()
