"""Domain preservation and novice-language routing, independent of models."""
import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from reverse_fusion.case_bridge import dry_run_route
from rea_enhanced.workflow import open_case,record,status

ROOT=Path(__file__).resolve().parents[1]


class DomainMethods(unittest.TestCase):
    def test_fixed_domain_files_and_recorded_adaptations(self):
        manifest=json.loads((ROOT/'components/reverse-core/preservation.json').read_text(encoding='utf-8'))
        for name,value in manifest['files'].items():
            data=(ROOT/name).read_bytes()
            if not name.endswith('.jar'):data=data.replace(b'\r\n',b'\n')
            self.assertEqual(sha256(data).hexdigest(),value['sha256'],name)
        self.assertEqual(len(manifest['files']),603)

    def test_all_domain_descriptors_and_support_are_available(self):
        routes=json.loads((ROOT/'components/reverse-core/routing.json').read_text(encoding='utf-8'))['routes']
        for identity in routes:
            result=dry_run_route('analysis',source='local',primary=identity)
            self.assertEqual(result['status'],'local-route-pass',identity)
            self.assertEqual(result['missing_support'],[],identity)

    def test_chinese_adjacent_technical_names_keep_specialist_routes(self):
        cases=[('分析这个APK，存在反调试和运行时DEX','skills/apk-reverse/SKILL.md'),
            ('逆向分析这个.NET程序集的业务逻辑','skills/dotnet-reverse/SKILL.md'),
            ('分析网页JavaScript加密参数','skills/js-reverse/SKILL.md'),
            ('分析PCAP中的协议帧','skills/protocol-reverse/SKILL.md')]
        for hint,skill in cases:
            result=dry_run_route(hint,source='local');self.assertEqual(result['skill'],skill)
        result=dry_run_route(cases[0][0],source='local')
        self.assertTrue(result['hard_target'])
        self.assertEqual(result['required_reads'], ['RULES.md'])
        self.assertIn('skills/apk-reverse/references/high-difficulty-android-playbook.md',result['method_reads'])

    def test_domain_refinement_keeps_original_goal(self):
        with tempfile.TemporaryDirectory() as td:
            project=Path(td)
            original=open_case(project,'分析这个软件，然后复刻出一个完全一样的可用版本')
            refined=record(project,'work/current-case',{'op':'refine_route','hint':'分析这个APK的反调试'},original['revision'])
            self.assertEqual(refined['original_request'],original['original_request'])
            self.assertEqual(refined['objective'],'reconstruction')
            self.assertEqual(refined['route']['skill'],'skills/apk-reverse/SKILL.md')
            self.assertTrue(all(Path(s).is_absolute() for s in refined['route']['required_read_paths']))
            self.assertFalse(refined['component_entries']['craft_required'])

    def test_plain_analysis_can_deliver_without_building(self):
        with tempfile.TemporaryDirectory() as td:
            project=Path(td);(project/'report.md').write_text('Owned report',encoding='utf-8')
            current=open_case(project,'帮我分析这个程序，暂时不要写复刻版')
            current=record(project,'work/current-case',{'op':'evidence','id':'E1','path':'report.md','authority':'static'},current['revision'])
            current=record(project,'work/current-case',{'op':'deliver_analysis','report':'report.md','evidence':['E1']},current['revision'])
            self.assertEqual(current['status'],'analysis-delivered')
            self.assertFalse(current['features'])

    def test_inherited_routing_corpus(self):
        cases=json.loads((ROOT/'skills/tests/routing-benchmark.json').read_text(encoding='utf-8-sig'))['cases']
        for case in cases:
            self.assertEqual(dry_run_route(case['hint'],source='local')['primary_id'],case['expect'],case['hint'])


if __name__=='__main__':unittest.main()
