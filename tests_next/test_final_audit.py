"""User-visible failures found by the final audit, using real independent processes."""
from pathlib import Path
import shutil
import sys
import unittest
from tests_next import test_workflow as fixture
from rea_enhanced.workflow import open_case, status, run_check
from rea_enhanced.comparison import compare, fresh
from rea_enhanced.storage import read, write


class FinalAudit(unittest.TestCase):
    setUp = fixture.OwnedCase.setUp
    prepare = fixture.OwnedCase.prepare

    def test_different_new_target_is_not_silently_discarded(self):
        self.prepare()
        result = open_case(self.root, '分析另一个APK并复刻登录和导出功能')
        self.assertEqual(result['status'], 'needs-context')
        self.assertEqual(result['incoming_request'], '分析另一个APK并复刻登录和导出功能')
        self.assertNotIn('APK', status(self.root)['original_request'])

    def test_plain_continue_with_new_requirement_is_preserved(self):
        self.prepare()
        result = open_case(self.root, '继续，再加上导出功能，前面的也要保留')
        self.assertIn('继续，再加上导出功能，前面的也要保留', result['supplements'])
        self.assertEqual(result['original_request'], '分析这个程序，然后复刻完整的计数和错误处理功能')

    def test_resolution_does_not_follow_replaced_evidence(self):
        add = self.prepare()
        add({'op':'unknown','id':'U1','question':'Runtime dependency?', 'critical':True,'features':['F1']})
        add({'op':'resolve','id':'U1','evidence':['E1']})
        self.assertEqual(status(self.root)['ready_features'], ['F1'])
        add({'op':'evidence','id':'E1','path':'research.md','authority':'inferred'})
        self.assertFalse(status(self.root)['ready_features'])

    def test_critical_unknown_cannot_have_no_affected_scope(self):
        add = self.prepare()
        with self.assertRaisesRegex(ValueError, 'scope|affected'):
            add({'op':'unknown','id':'U1','question':'Unknown whole goal', 'critical':True,'features':[]})

    def test_modified_failure_receipt_cannot_be_reused_as_pass(self):
        self.prepare()
        p = self.root/'candidate/app.py'
        p.write_text(fixture.CANDIDATE.replace('n=n+int(data["value"])','n=n+abs(int(data["value"]))'),encoding='utf-8')
        run_check(self.root,'work/current-case','C1','plan.json','work/fail')
        receipt=self.root/'work/fail/comparison.json'; result=read(receipt)
        result['status']='pass';write(receipt,result)
        checked=run_check(self.root,'work/current-case','C1','plan.json','work/recheck')
        self.assertFalse(checked.get('reused',False))
        self.assertEqual(checked['comparison']['status'],'fail')

    def test_external_runtime_change_invalidates_comparison(self):
        # Copy the real interpreter under a unique filename beside its DLLs.
        runtime=Path(sys.executable).parent/'rf-audit-runtime.exe'
        self.assertFalse(runtime.exists())
        shutil.copy2(sys.executable,runtime)
        self.addCleanup(lambda: runtime.unlink(missing_ok=True))
        for side in ('original','candidate'):
            self.plan[side]['argv'][0]=str(runtime)
        write(self.root/'plan.json',self.plan)
        result=compare(self.root,'plan.json','work/run')
        self.assertEqual(result['status'],'pass')
        with runtime.open('ab') as stream:stream.write(b'changed-executable')
        self.assertFalse(fresh(self.root,result))

    def test_application_environment_change_invalidates_success(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ,{'RF_OWNED_APP_MODE':'first'}):
            result=compare(self.root,'plan.json','work/env')
            self.assertTrue(fresh(self.root,result))
        with patch.dict(os.environ,{'RF_OWNED_APP_MODE':'second'}):
            self.assertFalse(fresh(self.root,result))

    def test_external_script_cannot_substitute_both_real_sides(self):
        other=self.root.parent/('external-'+self.root.name+'.py')
        other.write_text('print("same output")',encoding='utf-8')
        self.addCleanup(lambda:other.unlink(missing_ok=True))
        for side in ('original','candidate'):
            self.plan[side]['argv']=[sys.executable,str(other)]
        write(self.root/'plan.json',self.plan)
        with self.assertRaisesRegex(ValueError,'external|source|argv'):
            compare(self.root,'plan.json','work/external')

    def test_delivery_requires_whole_goal_review_and_invalidates_on_supplement(self):
        add=self.prepare()
        run_check(self.root,'work/current-case','C1','plan.json','work/pass')
        delivery={'op':'deliver','summary':'Counter source delivery','artifacts':['candidate/app.py']}
        with self.assertRaisesRegex(ValueError,'coverage'):
            add(delivery)
        add({'op':'coverage','requirements':[{'id':'R1','text':'Full count and error handling',
            'source':'original','features':['F1']}], 'review':'Compared original wording with ordered count, persistence and invalid input; no export requested.'})
        result=add(delivery)
        self.assertEqual(result['status'],'reviewed-delivery')
        self.assertEqual(result['delivery']['status'],'current')
        result=add({'op':'supplement','text':'还要导出CSV'})
        self.assertEqual(result['coverage']['status'],'stale')
        self.assertEqual(result['delivery']['status'],'stale')
        with self.assertRaisesRegex(ValueError,'coverage'):
            add(delivery)

    def test_partial_coverage_and_changed_artifacts_cannot_close(self):
        add=self.prepare()
        add({'op':'supplement','text':'继续保留错误处理'})
        row={'id':'R1','text':'Counter','source':'original','features':['F1']}
        with self.assertRaisesRegex(ValueError,'every'):
            add({'op':'coverage','requirements':[row],'review':'Partial mapping'})
        run_check(self.root,'work/current-case','C1','plan.json','work/pass')
        add({'op':'coverage','requirements':[row,{'id':'R2','text':'Error handling',
            'source':'supplement:1','features':['F1']}],'review':'All wording reviewed against count and errors.'})
        add({'op':'deliver','summary':'Full declared delivery','artifacts':['candidate/app.py','research.md']})
        (self.root/'research.md').write_text('Changed evidence and delivered report',encoding='utf-8')
        self.assertEqual(status(self.root)['delivery']['status'],'stale')

    def test_case_scoped_unknown_blocks_current_and_future_features(self):
        add=self.prepare()
        result=add({'op':'unknown','id':'U1','question':'Whole target identity?',
                    'critical':True,'features':[],'scope':'case'})
        self.assertEqual(result['ready_features'],[])
        result=add({'op':'feature','id':'F2','description':'Future feature','evidence':['E1'],
                    'checks':['C2'],'dependencies':[],'review':'Bound to same target'})
        self.assertEqual(result['ready_features'],[])

    def test_mcp_reused_result_points_to_real_original_receipt(self):
        from rea_enhanced.server import call_owned
        self.prepare()
        arguments={'project_root':str(self.root),'check_id':'C1','plan':'plan.json','output':'work/first'}
        first=call_owned('rf_next_compare',arguments)
        arguments['output']='work/not-created'
        second=call_owned('rf_next_compare',arguments)
        self.assertTrue(second['reused'])
        self.assertEqual(first['result_path'],second['result_path'])
        self.assertTrue(Path(second['result_path']).is_file())

    def test_dependency_evidence_replacement_invalidates_dependent_pass(self):
        add=self.prepare()
        (self.root/'dependency.md').write_text('Dependency behavior',encoding='utf-8')
        add({'op':'evidence','id':'E2','path':'dependency.md','authority':'observed'})
        add({'op':'feature','id':'F2','description':'Dependency','evidence':['E2'],
            'checks':['C2'],'dependencies':[],'review':'Observed dependency'})
        add({'op':'feature','id':'F1','description':'Counter depending on F2','evidence':['E1'],
            'checks':['C1'],'dependencies':['F2'],'review':'Uses observed F2 state'})
        run_check(self.root,'work/current-case','C1','plan.json','work/dependency')
        (self.root/'dependency.md').write_text('Changed dependency behavior',encoding='utf-8')
        add({'op':'evidence','id':'E2','path':'dependency.md','authority':'observed'})
        self.assertEqual(status(self.root)['features']['F1']['checks']['C1'],'stale')

    def test_analysis_report_is_invalidated_by_new_request(self):
        from rea_enhanced.workflow import record
        (self.root/'report.md').write_text('Owned static observations',encoding='utf-8')
        result=open_case(self.root,'先分析这个软件，不要复刻')
        def add(change):
            return record(self.root,'work/current-case',change,status(self.root)['revision'])
        add({'op':'evidence','id':'E1','path':'report.md','authority':'static'})
        result=add({'op':'deliver_analysis','report':'report.md','evidence':['E1']})
        self.assertEqual(result['status'],'analysis-delivered')
        result=add({'op':'supplement','text':'还要分析远程协议'})
        self.assertNotEqual(result['status'],'analysis-delivered')

    def test_returned_cli_works_outside_checkout_with_colliding_module(self):
        import subprocess,json
        (self.root/'rea_enhanced.py').write_text('raise RuntimeError("target module collision")',encoding='utf-8')
        shadowed=subprocess.run([sys.executable,'-m','rea_enhanced','status','--project-root',str(self.root)],
            cwd=self.root,capture_output=True,timeout=10)
        self.assertNotEqual(shadowed.returncode,0)
        opened=open_case(self.root,'帮我分析这个软件并复刻')
        run=subprocess.run([*opened['component_entries']['enhanced_cli'],'status','--project-root',str(self.root)],
            cwd=self.root,capture_output=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['original_request'],opened['original_request'])

    def test_shared_dependency_graph_does_not_explode_saved_inputs(self):
        import json
        from rea_enhanced.workflow import _feature_inputs
        add=self.prepare()
        for i in range(2,16):
            add({'op':'feature','id':'F'+str(i),'description':'Layer '+str(i),'evidence':['E1'],
                'checks':['C'+str(i)],'dependencies':['F'+str(j) for j in range(1,i)],
                'review':'Shared dependent behavior; retain one copy of each input.'})
        inputs=_feature_inputs(read(self.root/'work/current-case/case-v2.json'),'F15')
        self.assertLess(len(json.dumps(inputs)),20000)


if __name__=='__main__':unittest.main()
