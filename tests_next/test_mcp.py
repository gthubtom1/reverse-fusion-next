"""Real stdio compatibility and owned workflow over the enhanced endpoint."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import shutil
import subprocess
from rea_enhanced.providers import environment
from rea_enhanced.storage import write,read
from reverse_fusion.runtime import node_runtime
from reverse_fusion.mcp_probe import StdioMcp,catalog
from tests_next import test_workflow as fixture

ROOT=Path(__file__).resolve().parents[1]


class LiveMCP(unittest.TestCase):
    def test_old_connection_cannot_silently_apply_changed_workflow(self):
        from rea_enhanced.server import connection_identity,require_current_connection
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for name in connection_identity(ROOT):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
            initial=connection_identity(root)
            require_current_connection(initial,root)
            with (root/'rea_enhanced/workflow.py').open('ab') as stream:stream.write(b'\n# updated runtime\n')
            with self.assertRaisesRegex(ValueError,'needs-reconnect'):
                require_current_connection(initial,root)

    def test_actual_native_provider_and_new_server_bundle_roundtrip(self):
        compiler=shutil.which('gcc')
        self.assertIsNotNone(compiler,'This native qualification requires the selected external GCC fixture compiler')
        area=ROOT/'work/final-native-provider';area.mkdir(parents=True,exist_ok=True)
        target=area/'owned-reference.exe'
        subprocess.run([compiler,str(ROOT/'fixtures/owned-native/guarded.c'),'-g','-O0','-o',str(target)],check=True,capture_output=True,timeout=30)
        bundle=area/'native-bundle.json'; restored=area/'restored-bundle.json'
        client=StdioMcp([sys.executable,'-m','rea_enhanced','mcp'],cwd=ROOT,timeout=150)
        with client:
            client.initialize()
            def call(name,args):
                result=client.request('tools/call',{'name':name,'arguments':args})
                self.assertFalse(result.get('isError'),result)
                return result
            opened=call('open_binary',{'path':str(target)})
            analyzed=call('analyze_function',{'procedure':'main','detail':'summary'})
            self.assertTrue(analyzed['structuredContent']['normalized_result']['summary']['pseudocode']['available'])
            exported=call('export_evidence_bundle',{'path':str(bundle),'overwrite':True})
            self.assertGreater(exported['structuredContent']['result']['records'],0)
        with StdioMcp([sys.executable,'-m','rea_enhanced','mcp'],cwd=ROOT,timeout=45) as second:
            second.initialize()
            imported=second.request('tools/call',{'name':'import_evidence_bundle','arguments':{'path':str(bundle)}})
            exported_again=second.request('tools/call',{'name':'export_evidence_bundle','arguments':{'path':str(restored),'overwrite':True}})
        self.assertFalse(imported.get('isError'),imported)
        self.assertFalse(exported_again.get('isError'),exported_again)
        self.assertEqual(read(bundle)['records'],read(restored)['records'])
        self.assertEqual(client.cleanup['status'],'verified')
        self.assertEqual(second.cleanup['status'],'verified')
        write(ROOT/'evidence/next/final-audit/native-provider.json',{'status':'pass',
            'open':opened,'analysis':analyzed,'export':exported,'import':imported,
            'records_equal':True,'compiler':compiler,'cleanup':[client.cleanup,second.cleanup],
            'scope':'Actual selected native provider on a repository-owned PE, original evidence and restart. Not a hostile/protected third-party target.'})

    def test_original_catalog_preserved_and_frida_actually_enumerates(self):
        node,_=node_runtime(ROOT);env=environment(ROOT)
        original=StdioMcp([node,str(ROOT/'vendor/rea/package/scripts/rea.mjs'),'mcp'],cwd=ROOT,env=env,timeout=45)
        with original:
            source_identity=original.initialize();source=catalog(original)
            prompts=catalog(original,'prompts/list','prompts')
        enhanced=StdioMcp([sys.executable,'-m','rea_enhanced','mcp'],cwd=ROOT,timeout=45)
        with enhanced:
            info=enhanced.initialize();actual=catalog(enhanced)
            actual_prompts=catalog(enhanced,'prompts/list','prompts')
            frida=enhanced.request('tools/call',{'name':'list_frida_devices','arguments':{}})
        original_by={t['name']:t for t in source};actual_by={t['name']:t for t in actual}
        self.assertEqual({name:actual_by[name] for name in original_by},original_by)
        self.assertEqual(len(actual),len(source)+5)
        self.assertEqual(prompts,actual_prompts)
        self.assertFalse(frida.get('isError'),frida)
        self.assertTrue(any(d['type']=='local' for d in frida['structuredContent']['devices']))
        self.assertEqual(enhanced.cleanup['status'],'verified')
        write(ROOT/'evidence/next/s2/protocol-qualified.json',{'status':'pass',
            'source_server':source_identity['serverInfo'],'enhanced_server':info['serverInfo'],
            'official_tool_count':len(source),'enhanced_tool_count':len(actual),
            'canonical_tools_equal':True,'prompts_equal':True,'frida':frida,
            'original_cleanup':original.cleanup,'enhanced_cleanup':enhanced.cleanup,
            'scope':'Actual catalog/protocol, target-free provider enumeration; not every tool or target acceptance'})

    def test_owned_workflow_via_mcp(self):
        with tempfile.TemporaryDirectory() as td:
            project=Path(td);client=StdioMcp([sys.executable,'-m','rea_enhanced','mcp'],cwd=ROOT,timeout=45)
            with client:
                client.initialize()
                def call(name,arguments):
                    r=client.request('tools/call',{'name':name,'arguments':{'project_root':str(project),**arguments}})
                    self.assertFalse(r.get('isError'),r)
                    return r['structuredContent']
                opened=call('rf_next_case_open',{'request':'先分析这个程序，再复刻相同功能'})
                result=call('rf_next_case_status',{})
                self.assertEqual(opened['original_request'],result['original_request'])
                result=call('rf_next_case_record',{'expected_revision':result['revision'],
                    'change':{'op':'supplement','text':'完整目标保留，增加持久化验证'}})
                self.assertEqual(len(result['supplements']),1)
                script=project/'verify-owned.py'
                script.write_text('from pathlib import Path\nPath("result.txt").write_text("observed")\n',encoding='utf-8')
                result=call('rf_next_case_record',{'expected_revision':result['revision'],
                    'change':{'op':'evidence','id':'E1','path':'verify-owned.py','authority':'static'}})
                result=call('rf_next_case_record',{'expected_revision':result['revision'],
                    'change':{'op':'feature','id':'F1','description':'Owned observation',
                        'evidence':['E1'],'checks':['C1'],'dependencies':[],'review':'Actual script output; not product comparison.'}})
                result=call('rf_next_case_record',{'expected_revision':result['revision'],
                    'change':{'op':'execute','id':'observe','kind':'verify','features':['F1'],
                        'argv':[sys.executable,'verify-owned.py'],'inputs':['verify-owned.py'],
                        'artifacts':['result.txt'],'purpose':'Verify measured MCP operation','reusable':True}})
                self.assertEqual(result['operation']['exit_code'],0)
                self.assertFalse(result['workflow']['features']['F1']['complete'])
                allocation=call('rf_next_storage',{'action':'allocate','purpose':'Owned MCP storage test',
                    'rebuild':'Rerun this test','reserve_bytes':1048576})
                temporary=Path(allocation['path']);(temporary/'tmp').write_bytes(b'owned temporary')
                observed=call('rf_next_storage',{'action':'status'})
                self.assertEqual(observed['entries'][0]['state'],'active')
                completed=call('rf_next_storage',{'action':'complete','id':allocation['id']})
                self.assertGreater(completed['reclaimed_bytes'],0)
                self.assertFalse(temporary.exists())
            self.assertEqual(client.cleanup['status'],'verified')

    def test_native_bundle_survives_new_server(self):
        path=ROOT/'evidence/next/s2/native-bundle.json'
        self.assertTrue(path.is_file(),'Run the owned native provider qualification first')
        destination=ROOT/'state/next-native-restored.json'
        client=StdioMcp([sys.executable,'-m','rea_enhanced','mcp'],cwd=ROOT,timeout=45)
        with client:
            client.initialize()
            imported=client.request('tools/call',{'name':'import_evidence_bundle','arguments':{'path':str(path)}})
            exported=client.request('tools/call',{'name':'export_evidence_bundle','arguments':{'path':str(destination),'overwrite':True}})
        self.assertFalse(imported.get('isError'),imported)
        self.assertFalse(exported.get('isError'),exported)
        before,after=read(path),read(destination)
        self.assertEqual(before['records'],after['records'])
        write(ROOT/'evidence/next/s2/native-restart-qualified.json',{'status':'pass','records_equal':True,
            'import':imported,'export':exported,'cleanup':client.cleanup})


    def test_cancelled_owned_comparison_cleans_up_and_stays_unknown(self):
        import threading,time
        helper=fixture.OwnedCase();helper.setUp();self.addCleanup(helper.doCleanups)
        helper.prepare()
        (helper.root/'candidate/app.py').write_text('import time;time.sleep(10)',encoding='utf-8')
        helper.plan['timeout_seconds']=15
        helper.plan['scenarios']=helper.plan['scenarios'][:1]
        helper.plan['scenarios'][0]['steps']=helper.plan['scenarios'][0]['steps'][:1]
        write(helper.root/'plan.json',helper.plan)
        client=StdioMcp([sys.executable,'-m','rea_enhanced','mcp'],cwd=ROOT,timeout=20)
        with client:
            client.initialize();identity=client.sequence+1
            timer=threading.Timer(.5,lambda:client.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':identity,'reason':'Owned cancellation test'}}))
            started=time.monotonic();timer.start()
            result=client.request('tools/call',{'name':'rf_next_compare','arguments':{'project_root':str(helper.root),
                'check_id':'C1','plan':'plan.json','output':'work/cancelled'}})
            timer.join()
            self.assertFalse(result.get('isError'),result)
            self.assertEqual(result['structuredContent']['status'],'unknown')
            self.assertLess(time.monotonic()-started,5)
        self.assertEqual(client.cleanup['status'],'verified')


if __name__=='__main__':unittest.main()
