"""One enhanced REA stdio endpoint, forwarding original RPC results unchanged.

Only server identity, instructions and the first tool-catalog page are augmented.
Original evidence records, resources, prompts, canonical schemas and errors stay
with the official backend. No Craft or Spec executable is started.
"""
import json
from pathlib import Path
import sys
import threading
import queue
import time
from . import __version__
from .workflow import open_case, record, status, run_check
from reverse_fusion.mcp_process import McpProcess
from .providers import environment as launch_environment
from reverse_fusion.runtime import node_runtime

ROOT = Path(__file__).resolve().parents[1]
BASE = {'type':'object','properties':{'project_root':{'type':'string','description':'Absolute outcome-project directory'},
    'case_root':{'type':'string','default':'work/current-case'}},'required':['project_root'],'additionalProperties':False}


def _tool(name, description, properties, required):
    schema=json.loads(json.dumps(BASE));schema['properties'].update(properties);schema['required']+=required
    return {'name':name,'description':description,'inputSchema':schema}


def _change(op, properties, required):
    return {'type':'object','properties':{'op':{'const':op},**properties},
        'required':['op',*required],'additionalProperties':False}


TEXT={'type':'string','minLength':1}
STRINGS={'type':'array','items':TEXT}
CHANGE={'oneOf':[
    _change('supplement',{'text':TEXT},['text']),
    _change('evidence',{'id':TEXT,'path':TEXT,'authority':{'enum':['observed','static','inferred','designed','native-rea-bundle']},'description':TEXT},['id','path','authority']),
    _change('feature',{'id':TEXT,'description':TEXT,'evidence':STRINGS,'checks':STRINGS,'dependencies':STRINGS,'review':TEXT},
            ['id','description','evidence','checks','dependencies','review']),
    _change('unknown',{'id':TEXT,'question':TEXT,'critical':{'type':'boolean'},'features':STRINGS,'scope':{'enum':['features','case']}},
            ['id','question','critical','features']),
    _change('resolve',{'id':TEXT,'evidence':STRINGS},['id','evidence']),
    _change('refine_route',{'hint':TEXT,'primary':TEXT},['hint']),
    _change('deliver_analysis',{'report':TEXT,'evidence':STRINGS},['report','evidence']),
    _change('budget',{'max_checks_per_feature':{'type':'integer','minimum':1,'maximum':100},'reason':TEXT},['max_checks_per_feature','reason']),
    _change('coverage',{'review':TEXT,'requirements':{'type':'array','minItems':1,'items':{
        'type':'object','properties':{'id':TEXT,'text':TEXT,'source':TEXT,'features':STRINGS},
        'required':['id','text','source','features'],'additionalProperties':False}}},['review','requirements']),
    _change('deliver',{'summary':TEXT,'artifacts':STRINGS},['summary','artifacts'])]}


TOOLS = [
    _tool('rf_next_case_open','Preserve a plain-language goal or resume its existing case. Ordinary development remains host-native.',
          {'request':{'type':'string'}},['request']),
    _tool('rf_next_case_status','Read original goal, feature readiness, affected unknowns and fresh finite checks. Does not claim whole-product completion.',{},[]),
    _tool('rf_next_case_record','Record evidence, a feature, a dependent unknown or a user supplement with optimistic revision checking. Cannot post a check pass.',
          {'change':CHANGE,'expected_revision':{'type':'integer','minimum':1}},['change','expected_revision']),
    _tool('rf_next_compare','Execute the reviewed finite comparison plan in separate working copies. Actual executable effects; not an OS sandbox. Saves full receipts and returns a compact result.',
          {'check_id':{'type':'string'},'plan':{'type':'string'},'output':{'type':'string'},'retry_reason':{'type':'string'}},['check_id','plan','output'])]
NAMES={tool['name'] for tool in TOOLS}


def call_owned(name, args, cancel_event=None):
    if not isinstance(args,dict):raise ValueError('Tool arguments must be an object')
    schema=next(t['inputSchema'] for t in TOOLS if t['name']==name)
    if set(args)-set(schema['properties']) or any(k not in args for k in schema['required']):
        raise ValueError('Missing or extra tool arguments')
    project=Path(args['project_root'])
    if not project.is_absolute() or not project.is_dir() or project.resolve()==ROOT.resolve():
        raise ValueError('Select an existing absolute outcome project, not the shared tool checkout')
    case=args.get('case_root','work/current-case')
    if name=='rf_next_case_open':return open_case(project,args['request'],case)
    if name=='rf_next_case_status':return status(project,case)
    if name=='rf_next_case_record':return record(project,case,args['change'],args['expected_revision'])
    result=run_check(project,case,args['check_id'],args['plan'],args['output'],cancel_event=cancel_event,retry_reason=args.get('retry_reason'))
    if 'comparison' not in result:return result
    receipt=result['comparison']
    return {'status':receipt['status'],'result_path':str(project/result['receipt_path']), 'reused':result.get('reused',False),
        'differences':[{'scenario':r['scenario'],'step':r['step'],'channels':r['differences'],'status':r['status']}
            for r in receipt['cases'] if r['status']!='pass'][:20],
        'workflow':result['workflow'],'rea_native_proof':'not-performed'}


def serve():
    node,_=node_runtime(ROOT)
    entry=ROOT/'vendor/rea/package/scripts/rea.mjs'
    if not node or not entry.is_file():raise ValueError('Install the pinned REA runtime in this checkout first')
    environment=launch_environment(ROOT)
    environment.update(REA_MCP_INPUT_SCHEMA_PROFILE='compact',REA_MCP_OUTPUT_SCHEMA_PROFILE='compact')
    owner=McpProcess([node,str(entry),'mcp'],cwd=ROOT,env=environment)
    upstream=owner.process
    output_lock, input_lock, pending_lock = threading.Lock(), threading.Lock(), threading.Lock()
    pending={}
    ended=threading.Event()
    def emit(message):
        with output_lock:
            sys.stdout.buffer.write((json.dumps(message,ensure_ascii=True)+'\n').encode('ascii'))
            sys.stdout.buffer.flush()
    def forward(message):
        with input_lock:
            upstream.stdin.write((json.dumps(message,ensure_ascii=True)+'\n').encode('ascii'));upstream.stdin.flush()
    def incoming():
        try:
            for raw in upstream.stdout:
                message=json.loads(raw)
                with pending_lock:kind=pending.pop(message.get('id'),None)
                if isinstance(message.get('result'),dict):
                    result=message['result']
                    if kind=='initialize':
                        original=result.get('serverInfo',{})
                        result['serverInfo']={'name':'rea-enhanced','version':__version__}
                        result['instructions']=result.get('instructions','')+'\nEnhanced REA retains original tools and evidence. rf_next_* manages one outcome case and finite checks. Current host remains the only coding agent. Upstream: '+str(original.get('name'))+' '+str(original.get('version'))
                    elif kind=='tools/list:first':
                        if any(t['name'] in NAMES for t in result.get('tools',[])):
                            raise ValueError('Upstream tool names collide with owned enhancement names')
                        result.setdefault('tools',[]).extend(TOOLS)
                emit(message)
        except (OSError,ValueError,TypeError) as exc:
            print('Enhanced REA upstream transport stopped: '+str(exc),file=sys.stderr)
        finally:
            ended.set()
    def errors():
        for part in iter(lambda:upstream.stderr.read(4096),b''):
            sys.stderr.buffer.write(part);sys.stderr.buffer.flush()
    threads=[threading.Thread(target=incoming,daemon=True),threading.Thread(target=errors,daemon=True)]
    for thread in threads:thread.start()
    own_events={}
    workers=[]
    slots=threading.BoundedSemaphore(4)
    def owned_request(message,event):
        try:
            params=message.get('params',{})
            result=call_owned(params['name'],params.get('arguments',{}),cancel_event=event)
            reply={'content':[{'type':'text','text':json.dumps(result,ensure_ascii=True)}],'structuredContent':result}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            reply={'isError':True,'content':[{'type':'text','text':str(exc)}]}
        try:emit({'jsonrpc':'2.0','id':message['id'],'result':reply})
        except (OSError,ValueError):ended.set()
        finally:
            with pending_lock:own_events.pop(message['id'],None)
            slots.release()
    incoming_lines=queue.Queue(maxsize=128)
    def host_reader():
        try:
            for line in sys.stdin.buffer:
                while not ended.is_set():
                    try:incoming_lines.put(line,timeout=.1);break
                    except queue.Full:pass
                if ended.is_set():break
        finally:
            while not ended.is_set():
                try:incoming_lines.put(None,timeout=.1);break
                except queue.Full:pass
    threading.Thread(target=host_reader,daemon=True).start()
    try:
        while not ended.is_set():
            try:line=incoming_lines.get(timeout=.1)
            except queue.Empty:continue
            if line is None:break
            try:message=json.loads(line)
            except ValueError:
                emit({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}});continue
            if not isinstance(message,dict) or message.get('jsonrpc')!='2.0':
                emit({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request'}});continue
            identity=message.get('id')
            if identity is not None and type(identity) not in (int,str):
                emit({'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request ID'}});continue
            params=message.get('params',{})
            if not isinstance(params,dict):
                emit({'jsonrpc':'2.0','id':identity,'error':{'code':-32602,'message':'Parameters must be an object'}});continue
            if message.get('method')=='notifications/cancelled':
                cancel_id=params.get('requestId')
                if type(cancel_id) in (int,str):
                    with pending_lock:event=own_events.get(cancel_id)
                    if event:
                        event.set();continue
            if message.get('method')=='tools/call' and params.get('name') in NAMES:
                if identity is None:continue
                if not slots.acquire(blocking=False):
                    emit({'jsonrpc':'2.0','id':identity,'result':{'isError':True,
                        'content':[{'type':'text','text':'Owned operation capacity reached; wait for an active call.'}]}})
                    continue
                event=threading.Event()
                with pending_lock:own_events[identity]=event
                worker=threading.Thread(target=owned_request,args=(message,event),daemon=True)
                workers=[w for w in workers if w.is_alive()];workers.append(worker);worker.start()
            else:
                method=message.get('method')
                if 'id' in message and method in {'initialize','tools/list'}:
                    kind='tools/list:first' if method=='tools/list' and not params.get('cursor') else method
                    with pending_lock:pending[identity]=kind
                forward(message)
    finally:
        ended.set()
        with pending_lock:
            for event in own_events.values():event.set()
        deadline=time.monotonic()+10
        for worker in workers:worker.join(timeout=max(0,deadline-time.monotonic()))
        owner.close()
        for thread in threads:thread.join(timeout=1)
    return 0
