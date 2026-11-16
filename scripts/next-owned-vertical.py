"""Reproducible owned vertical run. Host code edits, actual independent checks."""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
from rea_enhanced.storage import write, read
from rea_enhanced.workflow import open_case, record, status, run_check

repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_fixture',repo/'tests_next/test_workflow.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
project=repo/'work/next-owned-counter'
if project.exists():raise SystemExit('Use a fresh owned project; preserve previous evidence')
project.mkdir(parents=True)
for name,code in [('original',fixture.REFERENCE),('candidate',fixture.CANDIDATE.replace('n=n+int(data["value"])','n=n+abs(int(data["value"]))'))]:
    area=project/name;area.mkdir();(area/'app.py').write_text(code,encoding='utf-8')
(project/'observations.md').write_text('Owned reference: ordered signed updates survive process restart; get reports persisted count. Invalid input exits 3.',encoding='utf-8')
steps=[{'stdin':json.dumps({'op':'add','value':n}),'args':[],'files':['state.json'],'expected_exit_codes':[0]} for n in [2,-1]]
steps.append({'stdin':'{"op":"get"}','args':[],'files':['state.json'],'expected_exit_codes':[0]})
plan={'version':2,'scope':'Owned stateful counter, restart and error path',
    'original':{'argv':[sys.executable,'app.py'],'cwd':'original','sources':['original/app.py']},
    'candidate':{'argv':[sys.executable,'app.py'],'cwd':'candidate','sources':['candidate/app.py']},
    'scenarios':[{'id':'state','steps':steps},{'id':'error','steps':[{'stdin':'{"op":"bad"}','args':[],'files':[],'expected_exit_codes':[3]}]}],
    'timeout_seconds':3}
write(project/'plan.json',plan)
opened=open_case(project,'分析这个计数程序，然后复刻全部已声明的计数、持久化和错误行为。我不懂技术。')
def add(change):return record(project,'work/current-case',change,status(project)['revision'])
add({'op':'evidence','id':'E1','path':'observations.md','authority':'observed','description':'Owned reference observations'})
add({'op':'feature','id':'F1','description':'Signed updates, persistence, restart and invalid input',
    'evidence':['E1'],'checks':['C1'],'dependencies':[],
    'review':'JSON add/get; signed integer state persists across separate processes; invalid operation exits 3.'})
bad=run_check(project,'work/current-case','C1','plan.json','work/round-1')
assert bad['comparison']['status']=='fail'
(project/'candidate/app.py').write_text(fixture.CANDIDATE,encoding='utf-8')
fixed=run_check(project,'work/current-case','C1','plan.json','work/round-2')
assert fixed['comparison']['status']=='pass'
resumed=json.loads(subprocess.check_output([sys.executable,'-m','rea_enhanced','status','--project-root',str(project)],cwd=repo,text=True))
assert resumed['features']['F1']['complete'] and resumed['original_request']==opened['original_request']
out=repo/'evidence/next/s1';out.mkdir(parents=True,exist_ok=True)
write(out/'vertical.json',{'status':'pass','scope':'Owned finite vertical; no universal/software/model performance claim',
    'bad':bad,'corrected':fixed,'fresh_process_resume':resumed,'runtime_dependencies':['Python standard library','owned Reverse router/process utilities'],
    'craft_present':(repo/'vendor/craft/upstream').exists(),'spec_present':(repo/'vendor/spec-kit/upstream').exists()})
print(json.dumps({'bad':bad['comparison']['status'],'corrected':fixed['comparison']['status'],'resumed':resumed['status'],
    'craft_present':(repo/'vendor/craft/upstream').exists(),'spec_present':(repo/'vendor/spec-kit/upstream').exists()}))
