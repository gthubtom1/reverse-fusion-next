"""Real stdio compatibility and owned workflow over the enhanced endpoint."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from rea_enhanced.providers import environment
from rea_enhanced.storage import write,read
from reverse_fusion.runtime import node_runtime
from reverse_fusion.mcp_probe import StdioMcp,catalog
from tests_next import test_workflow as fixture

ROOT=Path(__file__).resolve().parents[1]


class LiveMCP(unittest.TestCase):
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
        self.assertEqual(len(actual),len(source)+4)
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
