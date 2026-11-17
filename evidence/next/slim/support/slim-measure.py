from pathlib import Path
import ast,hashlib,json,os,subprocess,sys,tempfile,zipfile
ROOT=Path('D:/Project/reverse-next');info=json.loads((ROOT/'evidence/next/slim/baseline.json').read_text(encoding='utf-8'))
archive=ROOT/info['archive'];area=Path(tempfile.mkdtemp(prefix='reverse-slim-rollback-'));restored=area/'restored';restored.mkdir()
with zipfile.ZipFile(archive) as z:
 for item in z.infolist():
  p=restored/item.filename
  if not p.resolve().is_relative_to(restored.resolve()):raise ValueError('archive path')
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(item))
actual={p.relative_to(restored).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in restored.rglob('*') if p.is_file()}
expected=info.get('files',info.get('source_sha256'))
if not isinstance(expected,dict):raise ValueError('Check baseline digest field before extracting')
assert actual==expected

def skill_at(root):
 tree=ast.parse((root/'rea_enhanced/deployment.py').read_text(encoding='utf-8'))
 fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='skill_text')
 namespace={};exec(compile(ast.Module(body=[fn],type_ignores=[]),'owned-skill-render','exec'),namespace)
 return namespace['skill_text'](ROOT).encode()

def context(root):
 sizes={n:len((root/n).read_bytes()) for n in ['RULES.md','docs/AGENT-WORKFLOW.md']}
 sizes['owned_entry_skill']=len(skill_at(root))
 runtime=json.loads((root/'components/reverse-core/runtime.json').read_text(encoding='utf-8'))
 methods=list(dict.fromkeys([*runtime['base_reads'],'skills/apk-reverse/SKILL.md',*runtime['hard_target']['common_reads'],*runtime['hard_target']['route_reads']['R1']]))
 mandatory=runtime['base_reads'] if runtime.get('method_loading')=='on-demand' else methods
 return {'public_contract_bytes':sum(sizes.values()),'public_contract_parts':sizes,'difficult_apk_required_files':mandatory,
  'difficult_apk_required_bytes':sum(len((root/n).read_bytes()) for n in mandatory),'technical_methods_retained':all((root/n).is_file() for n in methods)}
report={'status':'pass','scope':'Mechanical instructions/recording fixture only; no model quality/cost/speed experiment',
 'rollback':{'status':'extracted-and-rehashed','files':len(actual),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'restored':str(restored)},
 'baseline':context(restored),'candidate':context(ROOT),'model_effectiveness':'not-established'}
(ROOT/'state/slim-measure-location.json').write_text(json.dumps({'path':str(area)}))
(ROOT/'evidence/next/slim/mechanical.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=True),flush=True)
