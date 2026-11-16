"""Actual finite browser replay with separate behavior and pixel verdicts."""
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image,ImageChops
from reverse_fusion.owned_process import run_owned
from reverse_fusion.runtime import node_runtime
from .storage import digest,inside,read,write
from .providers import providers,environment

ROOT=Path(__file__).resolve().parents[1]


def compare_web(project,plan_name,output,cancel_event=None):
    from .comparison import tree,engine_identity
    project=project.resolve();plan_path=inside(project,plan_name);destination=inside(project,output)
    plan=read(plan_path)
    expected={'version','kind','scope','original','candidate','scenarios','widths','observe','storage_keys','pixel_tolerance'}
    if set(plan)!=expected or plan['version']!=1 or plan['kind']!='web' or not isinstance(plan['scope'],str) or not plan['scope'].strip():
        raise ValueError('Web replay requires the declared version 1 finite contract')
    if (not isinstance(plan['widths'],list) or not 1<=len(plan['widths'])<=3
            or any(type(w) is not int or not 320<=w<=1920 for w in plan['widths'])
            or len(set(plan['widths']))!=len(plan['widths'])):
        raise ValueError('Declare 1..3 distinct viewport widths from 320 to 1920')
    if (type(plan['pixel_tolerance']) not in (int,float) or not 0<=plan['pixel_tolerance']<=1):
        raise ValueError('Pixel tolerance must be a predeclared fraction')
    for key in ('observe','storage_keys'):
        if (not isinstance(plan[key],list) or len(plan[key])>50
                or any(not isinstance(s,str) or not s or len(s)>500 for s in plan[key])):
            raise ValueError('Bounded explicit selector/storage allowlists are required')
    if not plan['observe']:raise ValueError('Visual similarity alone is insufficient: declare behavioral observations')
    if not isinstance(plan['scenarios'],list) or not 1<=len(plan['scenarios'])<=10:raise ValueError('Declare 1..10 scenarios')
    ids=set();steps_count=0
    for scenario in plan['scenarios']:
        if not isinstance(scenario,dict) or set(scenario)!={'id','steps'}:raise ValueError('Scenario requires id and steps')
        sid=scenario['id']
        if (not isinstance(sid,str) or not sid or sid in ids or len(sid)>80
                or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in sid)):
            raise ValueError('Unique portable scenario IDs required')
        ids.add(sid)
        if not isinstance(scenario['steps'],list) or not 1<=len(scenario['steps'])<=20:raise ValueError('Declare 1..20 steps')
        steps_count+=len(scenario['steps'])
        for step in scenario['steps']:
            allowed={'action'}
            action=step.get('action')
            if action in {'click','fill','press'}:allowed.add('selector')
            if action in {'fill','press'}:allowed.add('value')
            if action=='wait':allowed.add('ms')
            if action not in {'click','fill','press','reload','wait','observe'} or set(step)!=allowed:
                raise ValueError('Unsupported or malformed web action')
            if action=='wait' and (type(step['ms']) is not int or not 0<=step['ms']<=1000):raise ValueError('Wait must be 0..1000ms')
            if any(not isinstance(step[k],str) or len(step[k])>10000 for k in ('selector','value') if k in step):raise ValueError('Bounded action strings required')
    if steps_count*len(plan['widths'])>60:raise ValueError('At most 60 width/step observations per side')
    trees={};sources={}
    for side in ('original','candidate'):
        config=plan[side]
        if set(config)!={'url','cwd','sources'}:raise ValueError('Each web side requires URL, bounded cwd and declared sources')
        url=urlsplit(config['url'])
        if url.scheme not in {'http','https'} or not url.hostname or url.username or url.password:raise ValueError('Explicit HTTP(S) URL without embedded credentials required')
        cwd=inside(project,config['cwd'])
        if destination.is_relative_to(cwd):raise ValueError('Output cannot be inside a source tree')
        trees[side]={'cwd':config['cwd'],'files':tree(cwd)}
        if not isinstance(config['sources'],list) or not config['sources']:raise ValueError('Source identity is required')
        for name in config['sources']:
            p=inside(project,name)
            if not p.is_file() or not p.is_relative_to(cwd):raise ValueError('Source outside side cwd')
            sources[name]=digest(p)
    a,b=plan['original'],plan['candidate']
    if (a['url']==b['url'] or set(a['sources']) & set(b['sources'])
            or {sources[n] for n in a['sources']}=={sources[n] for n in b['sources']}):
        raise ValueError('Independent reference/candidate URLs and source identities required')
    if destination.exists():raise ValueError('Preserve earlier runs; use a new output path')
    selected=providers(ROOT);browser=selected['paths'].get('REA_BROWSER_EXECUTABLE')
    if not browser:raise ValueError('Browser provider unavailable; configure its explicit path')
    node,_=node_runtime(ROOT)
    plan_sha=digest(plan_path);engine=engine_identity(web=True);destination.mkdir(parents=True)
    for side in ('original','candidate'):
        cwd=inside(project,plan[side]['cwd'])
        for name in plan[side]['sources']:
            source=inside(project,name)
            target=destination/'source-snapshot'/side/source.relative_to(cwd)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    request=destination/'request.json';write(request,{'plan':plan,'output':str(destination),'browser':browser})
    result=run_owned([node,str(ROOT/'components/rea-enhanced/web-replay.mjs'),str(ROOT),str(request)],
        cwd=ROOT,stdin=b'',timeout=180,memory_mb=1536,max_output_bytes=8*1024*1024,env=environment(ROOT),cancel_event=cancel_event)
    try:captured=json.loads(result['stdout'])
    except (ValueError,UnicodeError):captured={'records':[],'error':'Browser did not produce complete JSON'}
    write(destination/'capture.json',captured)
    records={(r['scenario'],r['width'],r['step'],r['side']):r for r in captured.get('records',[])}
    cases=[]
    for scenario in plan['scenarios']:
        for width in plan['widths']:
            for index,_ in enumerate(scenario['steps']):
                left=records.get((scenario['id'],width,index,'original'))
                right=records.get((scenario['id'],width,index,'candidate'))
                case={'scenario':scenario['id'],'width':width,'step':index,'differences':[],
                      'behavior_status':'unknown','visual_status':'unknown'}
                if (left and right and not left.get('error') and left.get('observations')
                        and not any(item.get('missing') for item in left['observations'])):
                    if right.get('error'):
                        case['behavior_status']='fail';case['differences'].append('candidate-action')
                    else:
                        for channel in ('observations','storage'):
                            if left[channel]!=right[channel]:case['differences'].append(channel)
                        case['behavior_status']='fail' if case['differences'] else 'pass'
                    try:
                        lp,rp=inside(destination,left['screenshot']),inside(destination,right['screenshot'])
                        with Image.open(lp) as li,Image.open(rp) as ri:
                            a,b=li.convert('RGB'),ri.convert('RGB')
                            if a.size!=b.size:
                                fraction=1.0
                            else:
                                different=sum(pixel!=(0,0,0) for pixel in ImageChops.difference(a,b).getdata())
                                fraction=different/(a.width*a.height)
                        case['changed_pixel_fraction']=fraction
                        case['visual_status']='pass' if fraction<=plan['pixel_tolerance'] else 'fail'
                        if case['visual_status']=='fail':case['differences'].append('pixels')
                    except (OSError,ValueError,TypeError,KeyError):
                        case['visual_status']='unknown'
                states=(case['behavior_status'],case['visual_status'])
                case['status']='fail' if 'fail' in states else 'unknown' if 'unknown' in states else 'pass'
                cases.append(case)
    changed=[]
    for side,conf in trees.items():
        try:
            if tree(inside(project,conf['cwd']))!=conf['files']:changed.append(side)
        except (OSError,ValueError):changed.append(side)
    if not plan_path.is_file() or digest(plan_path)!=plan_sha:changed.append(plan_name)
    if engine_identity(web=True)!=engine:changed.append('comparison-engine')
    state=('unknown' if changed or result['status']!='observed' or result['exit_code']!=0 or captured.get('error')
           else 'fail' if any(c['status']=='fail' for c in cases)
           else 'unknown' if any(c['status']=='unknown' for c in cases) else 'pass')
    report={'schema_version':2,'operation':'independent-web-replay','status':state,'scope':plan['scope'],
        'plan':plan_name,'plan_sha256':plan_sha,'engine':engine,'sources':sources,'input_trees':trees,'cases':cases,
        'changed_inputs':changed,'browser_executable':browser,'browser_sha256':digest(Path(browser)),
        'process':{k:v for k,v in result.items() if k not in {'stdout','stderr'}},
        'capture_path':output+'/capture.json','elapsed_ms':result['elapsed_ms'],
        'rea_native_proof':'not-performed','whole_product_acceptance':'not-established',
        'limitations':['Only declared actions/selectors/storage keys/viewport screenshots were compared.',
            'Source-to-served-URL correspondence is declared by the host, not automatically authenticated.',
            'No unobserved server, API, device or whole-program equivalence established.',
            'Disposable browser contexts and owned process cleanup are not OS/network isolation.']}
    write(destination/'comparison.json',report)
    return report
