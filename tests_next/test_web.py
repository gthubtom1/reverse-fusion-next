"""Actual browser cases: equal output, wrong behavior, and look-only mismatch."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from rea_enhanced.comparison import compare,fresh
from rea_enhanced.storage import write,digest

ROOT=Path(__file__).resolve().parents[1]

HTML='''<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:Arial,sans-serif;margin:24px;color:#18202c}
button{background:#2463eb;color:white;border:0;padding:10px 20px;font-size:16px}
#count{display:block;font-size:32px;margin:20px 0}
</style></head><body><h1>Owned counter</h1><output id="count">0</output><button id="increment">Add one</button><script>CODE</script></body></html>'''
REFERENCE='''let count=Number(localStorage.getItem('counter')||0);const show=()=>document.getElementById('count').textContent=String(count);show();document.getElementById('increment').addEventListener('click',()=>{count=count+1;localStorage.setItem('counter',String(count));show();});'''
CANDIDATE='''const output=document.querySelector('#count');let x=parseInt(localStorage.counter??'0',10);output.textContent=x;document.querySelector('#increment').onclick=function(){x+=1;output.textContent=x;localStorage.counter=''+x;};'''


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


class WebComparison(unittest.TestCase):
    def retain(self,name,result):
        write(ROOT/('evidence/next/final-audit/web-'+name+'.json'),{
            'status':'pass','observed_comparison_status':result['status'],'comparison':result,
            'test_sha256':digest(Path(__file__)),
            'scope':'Actual finite browser assertions in this test; not a whole website acceptance'})

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.servers=[]
        for name,code in [('original',REFERENCE),('candidate',CANDIDATE)]:
            area=self.root/name;area.mkdir();(area/'index.html').write_text(HTML.replace('CODE',code),encoding='utf-8')
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(area)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
            self.servers.append(server)
        self.plan={'version':1,'kind':'web','scope':'Owned counter visual, click and persistence behavior',
            'original':{'url':f'http://127.0.0.1:{self.servers[0].server_port}/','cwd':'original','sources':['original/index.html']},
            'candidate':{'url':f'http://127.0.0.1:{self.servers[1].server_port}/','cwd':'candidate','sources':['candidate/index.html']},
            'widths':[390,1280],'observe':['#count','#increment'],'storage_keys':['counter'],'pixel_tolerance':0,
            'scenarios':[{'id':'click-and-reload','steps':[{'action':'observe'},{'action':'click','selector':'#increment'},{'action':'reload'}]}]}
        write(self.root/'plan.json',self.plan)

    def test_same_visual_and_behavior(self):
        result=compare(self.root,'plan.json','work/first')
        self.assertEqual(result['status'],'pass',result)
        self.assertTrue(all(r['behavior_status']=='pass' and r['visual_status']=='pass' for r in result['cases']))
        self.assertTrue(fresh(self.root,result))
        self.retain('equal',result)

    def test_wrong_behavior_is_not_hidden_by_initial_look(self):
        (self.root/'candidate/index.html').write_text(HTML.replace('CODE',CANDIDATE.replace('x+=1','x+=2')),encoding='utf-8')
        result=compare(self.root,'plan.json','work/bad-behavior')
        self.assertEqual(result['status'],'fail',result)
        self.assertTrue(any(r['behavior_status']=='fail' for r in result['cases']))
        self.assertTrue(any(r['behavior_status']=='pass' for r in result['cases']))
        self.retain('wrong-behavior',result)

    def test_wrong_color_does_not_claim_behavior_failure(self):
        (self.root/'candidate/index.html').write_text(HTML.replace('CODE',CANDIDATE).replace('#2463eb','#db2443'),encoding='utf-8')
        result=compare(self.root,'plan.json','work/bad-look')
        self.assertEqual(result['status'],'fail',result)
        self.assertTrue(all(r['behavior_status']=='pass' for r in result['cases']))
        self.assertTrue(any(r['visual_status']=='fail' for r in result['cases']))
        self.retain('wrong-look',result)

    def test_missing_reference_observation_is_unknown(self):
        self.plan['observe']=['#does-not-exist'];write(self.root/'plan.json',self.plan)
        result=compare(self.root,'plan.json','work/unknown')
        self.assertEqual(result['status'],'unknown',result)
        self.retain('missing-observation',result)

    def controls(self):
        html='''<!doctype html><html><body>
<select id="order"><option value="new">New</option><option value="name">Name</option></select>
<input type="checkbox" id="enabled"><button id="clear">Clear</button><output id="count">0</output>
<script>document.querySelector('#clear').onclick=()=>{if(confirm('Remove all?')){
localStorage.setItem('counter','0');document.querySelector('#count').textContent='cleared';}};</script></body></html>'''
        for side in ('original','candidate'):
            (self.root/side/'index.html').write_text(html+('<!-- independent candidate -->' if side=='candidate' else ''),encoding='utf-8')
        self.plan.update(widths=[390],observe=['#order','#enabled','#count'],scenarios=[{'id':'controls','steps':[
            {'action':'select','selector':'#order','value':'name'},
            {'action':'check','selector':'#enabled','checked':True},
            {'action':'storage','key':'counter','value':'invalid-state'},
            {'action':'dialog','decision':'dismiss','value':''},
            {'action':'click','selector':'#clear'},
            {'action':'dialog','decision':'accept','value':''},
            {'action':'click','selector':'#clear'},
            {'action':'reload'}]}])
        write(self.root/'plan.json',self.plan)

    def test_dropdown_checkbox_storage_and_both_dialog_outcomes(self):
        self.controls()
        result=compare(self.root,'plan.json','work/controls')
        self.assertEqual(result['status'],'pass',result)
        self.assertEqual(len(result['cases']),8)
        self.assertEqual(result['cases'][4]['behavior_status'],'pass')
        self.retain('controls',result)

    def test_changed_dialog_is_a_real_behavior_difference(self):
        self.controls()
        p=self.root/'candidate/index.html';p.write_text(p.read_text(encoding='utf-8').replace('Remove all?','Remove some?'),encoding='utf-8')
        result=compare(self.root,'plan.json','work/wrong-dialog')
        self.assertEqual(result['status'],'fail',result)
        self.assertTrue(any('dialogs' in row['differences'] for row in result['cases']))

    def test_undeclared_dialog_cannot_silently_dismiss_and_pass(self):
        self.controls()
        self.plan['scenarios'][0]['steps']=[{'action':'click','selector':'#clear'}]
        write(self.root/'plan.json',self.plan)
        result=compare(self.root,'plan.json','work/unexpected-dialog')
        self.assertEqual(result['status'],'unknown',result)


if __name__=='__main__':unittest.main()
