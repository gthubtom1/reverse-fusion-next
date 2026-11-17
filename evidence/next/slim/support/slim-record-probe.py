from pathlib import Path
import json,os,sys,tempfile,time
root=Path(sys.argv[1]);mode=sys.argv[2];output=Path(sys.argv[3]);sys.path.insert(0,str(root));sys.dont_write_bytecode=True
os.environ['RF_NEXT_DISK_STATE']=str(output.parent/('coordinator-'+mode))
from tests_next import test_workflow as fixture
from rea_enhanced.workflow import open_case,record,status,run_check
helper=fixture.OwnedCase();helper.setUp();project=helper.root
calls=[];responses=[];start=time.monotonic();temporary_peak=0
try:
 def api(name,fn,*args):
  global temporary_peak
  t=time.monotonic();r=fn(*args);calls.append({'operation':name,'elapsed_ms':round((time.monotonic()-t)*1000,3)})
  responses.append(len(json.dumps(r,ensure_ascii=True).encode()))
  temporary_peak=max(temporary_peak,sum(p.stat().st_size for p in project.rglob('*') if p.is_file()))
  return r
 def change(c):return api('record:'+c['op'],record,project,'work/current-case',c,status(project)['revision'])
 api('open',open_case,project,'分析并复刻程序的计数持久化和错误输入')
 if mode=='baseline':
  change({'op':'evidence','id':'E1','path':'research.md','authority':'observed','description':'Owned independent reference observation'})
  change({'op':'feature','id':'R1','description':'Count and errors','evidence':['E1'],'checks':['C1'],'dependencies':[],
   'review':'Ordered add/get, persisted count and invalid input exit3 compared with independent original.'})
 else:
  change({'op':'requirement','id':'R1','description':'Count and errors','checks':['C1'],'dimensions':['process:bounded'],'source':'original',
   'review':'Ordered add/get, persisted count and invalid input exit3 compared with independent original.'})
 checked=api('compare',run_check,project,'work/current-case','C1','plan.json','work/compared')
 assert checked['comparison']['status']=='pass'
 change({'op':'product','candidate_files':['candidate/app.py'],'reference_files':['original/app.py'],
  'review':'Independent implementations of counter behavior, not shared resource identity.'})
 if mode=='baseline':
  change({'op':'coverage','requirements':[{'id':'U1','text':'Count persistence and errors','source':'original','features':['R1']}],
   'review':'Full fixture wording maps to counter/error checks; not arbitrary-product proof.'})
 delivered=change({'op':'deliver','summary':'Owned finite counter fixture','artifacts':['candidate/app.py']})
 assert delivered['status']=='reviewed-delivery'
 report={'status':'pass','condition':mode,'calls':calls,'explicit_record_calls':sum(c['operation'].startswith('record:') for c in calls),
  'response_utf8_bytes':responses,'total_response_bytes':sum(responses),'elapsed_seconds':round(time.monotonic()-start,3),
  'sampled_project_peak_bytes':temporary_peak,'peak_scope':'After API boundaries only; not OS/process RSS or transient high-water mark',
  'comparison_reused':checked.get('reused',False),'comparison_cases':len(checked['comparison']['cases']),
  'delivery_status':delivered['status'],'extra_model_calls':0,'scope':'Same finite fixture, one deterministic API trace per condition; not model/task outcome experiment.'}
 output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report),flush=True)
finally:helper.doCleanups()
