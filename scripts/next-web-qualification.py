"""Retain actual browser screenshots and separate channel verdicts for review."""
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests_next.test_web import HTML,REFERENCE,CANDIDATE,Quiet
from rea_enhanced.comparison import compare
from rea_enhanced.storage import write
root=Path(__file__).resolve().parents[1];area=root/'evidence/next/s3/web'
if area.exists():raise SystemExit('Preserve old qualification; select a new output directory')
area.mkdir(parents=True)
servers=[]
try:
 for side,code in [('original',REFERENCE),('candidate',CANDIDATE)]:
  source=area/side;source.mkdir();(source/'index.html').write_text(HTML.replace('CODE',code),encoding='utf-8')
  server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(source)))
  servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
 plan={'version':1,'kind':'web','scope':'Owned click/reload persistence and visuals',
  'original':{'url':f'http://127.0.0.1:{servers[0].server_port}/','cwd':'original','sources':['original/index.html']},
  'candidate':{'url':f'http://127.0.0.1:{servers[1].server_port}/','cwd':'candidate','sources':['candidate/index.html']},
  'widths':[390,1280],'observe':['#count','#increment'],'storage_keys':['counter'],'pixel_tolerance':0,
  'scenarios':[{'id':'state','steps':[{'action':'observe'},{'action':'click','selector':'#increment'},{'action':'reload'}]}]}
 write(area/'plan.json',plan)
 good=compare(area,'plan.json','good')
 assert good['status']=='pass',good
 (area/'candidate/index.html').write_text(HTML.replace('CODE',CANDIDATE.replace('x+=1','x+=2')),encoding='utf-8')
 bad_behavior=compare(area,'plan.json','wrong-behavior')
 assert bad_behavior['status']=='fail'
 (area/'candidate/index.html').write_text(HTML.replace('CODE',CANDIDATE).replace('#2463eb','#db2443'),encoding='utf-8')
 bad_visual=compare(area,'plan.json','wrong-visual')
 assert bad_visual['status']=='fail' and all(c['behavior_status']=='pass' for c in bad_visual['cases'])
 (area/'candidate/index.html').write_text(HTML.replace('CODE',CANDIDATE),encoding='utf-8')
 write(area/'qualification.json',{'status':'pass','correct':good['status'],'bad_behavior':bad_behavior['status'],
  'bad_visual':bad_visual['status'],'behavior_preserved_in_visual_only_failure':True,
  'scope':'Actual owned browser replay; finite selectors/storage and screenshots, not whole websites or model A/B'})
 print('Browser qualification: correct pass; wrong behavior fail; wrong visuals fail with behavior pass.')
finally:
 for server in servers:server.shutdown();server.server_close()
