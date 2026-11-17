from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,tempfile,unittest,time
R=Path('D:/Project/reverse-next')
if len(sys.argv)>1:
 B=Path(sys.argv[1]);S=B/'source'
else:
 B=Path(tempfile.mkdtemp(prefix='reverse-next-slim-'));S=B/'source'
 for folder in ('vendor/rea/package','vendor/rea/node_modules','vendor/node'):
  shutil.copytree(R/folder,S/folder,dirs_exist_ok=True)
 (S/'state').mkdir(exist_ok=True)
 (S/'state/rea-runtime.json').write_text(json.dumps({'schema_version':1,'repository_root':str(S),'node':str(S/'vendor/node/node-v24.22.1-win-x64/node.exe')}))
 (S/'state/rea-providers.json').write_text(json.dumps({'schema_version':2,'repository_root':str(S),'paths':{'REA_BROWSER_EXECUTABLE':'C:/Program Files/Google/Chrome/Application/chrome.exe'},'sources':{}}))
 subprocess.run([sys.executable,'-I','-B','-m','venv','--system-site-packages',str(S/'.venv')],check=True)
 home=Path.home();ch=Path(os.environ.get('CODEX_HOME',str(home/'.codex')))
 names=[home/'.agents/skills/reverse-fusion/SKILL.md',ch/'AGENTS.md',ch/'config.toml']
 (B/'deployment-before.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in names if p.is_file()}))
files={n for n in subprocess.check_output(['git','ls-files','-z'],cwd=R).decode().split('\0') if n}
files.update(n for n in subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=R).decode().split('\0') if n.startswith(('rea_enhanced/','tests_next/','docs/NEXT/','evidence/next/slim/','docs/DOMAIN-METHODS.md')))
for name in files:
 if (R/name).is_file():
  p=S/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/name,p)
(B/'source-identity.json').write_text(json.dumps({n:hashlib.sha256((S/n).read_bytes()).hexdigest() for n in sorted(files) if (S/n).is_file()}))
os.environ['RF_NEXT_DISK_STATE']=str(B/'coordinator');os.environ['PYTHONDONTWRITEBYTECODE']='1'
T=B/'temp';T.mkdir(exist_ok=True)
for key in ('TEMP','TMP','TMPDIR'):os.environ[key]=str(T)
sys.dont_write_bytecode=True;sys.path.insert(0,str(S));start=time.monotonic()
loader=unittest.TestLoader();suite=unittest.TestSuite();excluded=[]
full='--full' in sys.argv
modules=sorted((S/'tests_next').glob('test_*.py')) if full else [S/'tests_next/test_slim.py']
def walk(s):
 for t in s:
  if isinstance(t,unittest.TestSuite):yield from walk(t)
  else:yield t
for p in modules:
 for t in walk(loader.loadTestsFromName('tests_next.'+p.stem)):
  if t.id().endswith('test_actual_native_provider_and_new_server_bundle_roundtrip'):
   excluded.append(t.id())
  elif not full and '.SlimInstructions.' in t.id():pass
  else:suite.addTest(t)
name='regression' if full else 'native-focused'
with (B/(name+'.txt')).open('w',encoding='utf-8') as out:
 result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
report={'project':str(B),'tests':result.testsRun,'failures':[(t.id(),e) for t,e in result.failures],
 'errors':[(t.id(),e) for t,e in result.errors],'skipped':result.skipped,'excluded_native_provider':excluded,'elapsed_seconds':round(time.monotonic()-start,3)}
(B/(name+'.json')).write_text(json.dumps(report,indent=2));(R/'state/slim-test-location.json').write_text(json.dumps({'path':str(B)}));print(json.dumps(report),flush=True)
raise SystemExit(0 if result.wasSuccessful() else 1)
