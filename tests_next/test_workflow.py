"""Owned behavioral counterexamples, not implementation-mirroring mocks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from rea_enhanced.comparison import compare, fresh
from rea_enhanced.storage import read, write, inside
from rea_enhanced.workflow import open_case, record, status, run_check

REFERENCE = '''import json,sys
from pathlib import Path
p=Path("state.json")
state=json.loads(p.read_text()) if p.exists() else {"count":0}
try:
 command=json.loads(sys.stdin.read())
 if command["op"]=="add": state["count"]+=int(command["value"])
 elif command["op"]!="get": raise ValueError("unknown operation")
 p.write_text(json.dumps(state,sort_keys=True))
 print(json.dumps(state,sort_keys=True))
except (ValueError,KeyError) as exc:
 print("invalid input",file=sys.stderr)
 sys.exit(3)
'''
CANDIDATE = '''import sys,json
from pathlib import Path
f=Path("state.json")
n=json.loads(f.read_text())["count"] if f.exists() else 0
try:
 data=json.load(sys.stdin)
 operation=data["op"]
 if operation=="add": n=n+int(data["value"])
 elif operation!="get": raise ValueError()
 result=dict(count=n)
 f.write_text(json.dumps(result,sort_keys=True))
 sys.stdout.write(json.dumps(result,sort_keys=True)+"\\n")
except (KeyError,ValueError):
 sys.stderr.write("invalid input\\n")
 raise SystemExit(3)
'''


class OwnedCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, code in [('original', REFERENCE), ('candidate', CANDIDATE)]:
            area=self.root/name;area.mkdir();(area/'app.py').write_text(code,encoding='utf-8')
        (self.root/'research.md').write_text('Observed ordered count updates, persistence, get and invalid-input exit 3.',encoding='utf-8')
        steps=[]
        for value in [2,-1]:
            steps.append({'stdin':json.dumps({'op':'add','value':value}), 'args':[], 'files':['state.json'], 'expected_exit_codes':[0]})
        steps.append({'stdin':'{"op":"get"}','args':[],'files':['state.json'],'expected_exit_codes':[0]})
        self.plan={'version':2,'scope':'Owned persistent count behavior and invalid input',
            'original':{'argv':[sys.executable,'app.py'],'cwd':'original','sources':['original/app.py']},
            'candidate':{'argv':[sys.executable,'app.py'],'cwd':'candidate','sources':['candidate/app.py']},
            'scenarios':[{'id':'ordered-state','steps':steps}, {'id':'invalid-input','steps':[
                {'stdin':'{"op":"bad"}','args':[],'files':[],'expected_exit_codes':[3]}]}],
            'timeout_seconds':3}
        write(self.root/'plan.json',self.plan)

    def prepare(self):
        result=open_case(self.root,'分析这个程序，然后复刻完整的计数和错误处理功能')
        def add(change):
            return record(self.root,'work/current-case',change,status(self.root)['revision'])
        add({'op':'evidence','id':'E1','path':'research.md','authority':'observed','description':'Owned original observation'})
        add({'op':'feature','id':'F1','description':'Persistent ordered counter and errors',
             'evidence':['E1'],'checks':['C1'],'dependencies':[],
             'review':'Input add/get; persistent count; invalid input exits 3 without state mutation.'})
        return add

    def test_independent_ordered_state_and_error(self):
        result=compare(self.root,'plan.json','work/pass')
        self.assertEqual(result['status'],'pass',result)
        self.assertEqual(len(result['cases']),4)
        self.assertFalse((self.root/'original/state.json').exists())
        self.assertFalse((self.root/'candidate/state.json').exists())
        self.assertEqual(result['rea_native_proof'],'not-performed')

    def test_wrong_algorithm_fails(self):
        p=self.root/'candidate/app.py';p.write_text(CANDIDATE.replace('n=n+int(data["value"])','n=n+abs(int(data["value"]))'),encoding='utf-8')
        result=compare(self.root,'plan.json','work/bad')
        self.assertEqual(result['status'],'fail')
        self.assertTrue(any('files' in c['differences'] for c in result['cases']))

    def test_same_stdout_wrong_persistence_fails(self):
        p=self.root/'candidate/app.py';p.write_text(CANDIDATE.replace('json.dumps(result,sort_keys=True))','json.dumps({"count":0},sort_keys=True))'),encoding='utf-8')
        self.assertEqual(compare(self.root,'plan.json','work/bad-state')['status'],'fail')

    def test_two_missing_files_are_not_success(self):
        self.plan['scenarios'][0]['steps'][0]['files']=['missing.bin'];write(self.root/'plan.json',self.plan)
        self.assertEqual(compare(self.root,'plan.json','work/missing')['status'],'unknown')

    def test_matching_crashes_are_not_success(self):
        for name,code in [('original','raise RuntimeError("bad")'),('candidate','# separate\nraise RuntimeError("bad")')]:
            (self.root/name/'app.py').write_text(code,encoding='utf-8')
        self.assertEqual(compare(self.root,'plan.json','work/crash')['status'],'unknown')

    def test_no_reused_original_identity(self):
        (self.root/'candidate/app.py').write_text(REFERENCE,encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'independent'):
            compare(self.root,'plan.json','work/same')

    def test_original_request_and_resume(self):
        self.prepare(); before=status(self.root)
        resumed=open_case(self.root,'继续')
        self.assertEqual(resumed['original_request'],before['original_request'])
        self.assertEqual(resumed['revision'],before['revision'])
        self.assertEqual(resumed['ready_features'],['F1'])

    def test_normal_development_and_missing_continue(self):
        self.assertEqual(open_case(self.root,'开发一个记账网站')['status'],'host-native')
        self.assertFalse((self.root/'work').exists())
        self.assertEqual(open_case(self.root,'继续')['status'],'needs-context')

    def test_dependency_blocks_only_affected_feature(self):
        add=self.prepare()
        add({'op':'feature','id':'F2','description':'Remote feature remains in full goal',
            'evidence':['E1'],'checks':['C2'],'dependencies':[],'review':'Requires server response.'})
        result=add({'op':'unknown','id':'U1','question':'Missing authorized server observation',
                   'critical':True,'features':['F2']})
        self.assertEqual(result['ready_features'],['F1'])
        self.assertIn('F2',result['blocked_features'])
        checked=run_check(self.root,'work/current-case','C1','plan.json','work/run')
        self.assertTrue(checked['workflow']['features']['F1']['complete'])
        self.assertFalse(checked['workflow']['features']['F2']['complete'])
        self.assertEqual(checked['workflow']['status'],'implementation')

    def test_freshness_invalidates_success_after_edit(self):
        self.prepare();run_check(self.root,'work/current-case','C1','plan.json','work/first')
        self.assertTrue(status(self.root)['features']['F1']['complete'])
        with (self.root/'candidate/app.py').open('a',encoding='utf-8') as stream:stream.write('\n# changed\n')
        result=status(self.root)
        self.assertEqual(result['features']['F1']['checks']['C1'],'stale')
        self.assertFalse(result['features']['F1']['complete'])

    def test_plan_change_invalidates_success(self):
        result=compare(self.root,'plan.json','work/fresh')
        self.assertTrue(fresh(self.root,result))
        self.plan['scope']='Changed scope';write(self.root/'plan.json',self.plan)
        self.assertFalse(fresh(self.root,result))

    def test_stale_revision_rejected(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'Stale'):
            record(self.root,'work/current-case',{'op':'supplement','text':'new request'},1)

    def test_supplement_retains_original_and_remaining_work(self):
        add=self.prepare();original=status(self.root)['original_request']
        result=add({'op':'supplement','text':'还需要支持导出，不取消前面的要求'})
        self.assertEqual(result['original_request'],original)
        self.assertEqual(len(result['supplements']),1)
        self.assertIn('F1',result['features'])

    def test_no_manually_posted_pass(self):
        add=self.prepare()
        with self.assertRaisesRegex(ValueError,'actual comparison'):
            add({'op':'check','id':'C1','status':'pass'})

    def test_missing_evidence_and_inferred_resolution(self):
        add=self.prepare()
        add({'op':'unknown','id':'U1','critical':True,'features':['F1'],'question':'Need runtime evidence'})
        add({'op':'evidence','id':'E2','path':'research.md','authority':'inferred'})
        with self.assertRaisesRegex(ValueError,'qualifying evidence'):
            add({'op':'resolve','id':'U1','evidence':['E2']})
        self.assertFalse(status(self.root)['ready_features'])

    def test_timeout_is_unknown_and_owned_process_ends(self):
        (self.root/'candidate/app.py').write_text('import time;time.sleep(5)',encoding='utf-8')
        self.plan['timeout_seconds']=.1
        self.plan['scenarios']=self.plan['scenarios'][:1]
        self.plan['scenarios'][0]['steps']=self.plan['scenarios'][0]['steps'][:1]
        write(self.root/'plan.json',self.plan)
        result=compare(self.root,'plan.json','work/timeout')
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(result['cases'][0]['observations']['candidate']['reason'],'timeout')
        self.assertIn('owned',result['cases'][0]['observations']['candidate']['cleanup'])

    def test_escape_and_overwrite_rejected(self):
        for name in ['../outside','/absolute','C:/absolute','nested/../outside','nested\\outside']:
            with self.assertRaises(ValueError):inside(self.root,name)
        compare(self.root,'plan.json','work/once')
        with self.assertRaisesRegex(ValueError,'previous runs'):
            compare(self.root,'plan.json','work/once')


if __name__=='__main__':unittest.main()
