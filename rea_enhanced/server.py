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
from .health import node_identity
from .storage import digest, inside, read

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_META = 'reverse-fusion-next/runtime'
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
    _change('evidence',{'id':TEXT,'path':TEXT,'authority':{'enum':['observed','static','inferred','designed','native-rea-bundle']},'description':TEXT,
                       'retention':{'enum':['snapshot','live'],'default':'snapshot'}},['id','path','authority']),
    _change('feature',{'id':TEXT,'description':TEXT,'evidence':STRINGS,'checks':STRINGS,'dependencies':STRINGS,'review':TEXT},
            ['id','description','evidence','checks','dependencies','review']),
    _change('requirement',{'id':TEXT,'description':TEXT,'checks':STRINGS,'dimensions':STRINGS,
        'source':TEXT,'review':TEXT,'evaluation':{'enum':['automatic','host-review'],'default':'automatic'},
        'subjects':{'type':'object','properties':{'candidate_files':STRINGS,'reference_files':STRINGS},
                    'required':['candidate_files','reference_files'],'additionalProperties':False}},
        ['id','description','checks','dimensions','source','review']),
    _change('checkpoint',{'note':TEXT,'next_action':TEXT,'paths':STRINGS},['note','next_action']),
    _change('output_goal',{'kinds':{'type':'array','minItems':1,'items':{'enum':[
        'analysis-report','independent-reimplementation','specification-implementation','modified-original']}},
        'source':TEXT,'review':TEXT},['kinds','source','review']),
    _change('assessment',{'id':TEXT,'features':STRINGS,'observations':STRINGS,
        'candidate_files':STRINGS,'reference_files':STRINGS,'input_paths':STRINGS,'dimensions':STRINGS,
        'producer':TEXT,'operation':TEXT,'context':TEXT,'scope':TEXT,
        'basis':{'enum':['original-comparison','specification','observation']},
        'outcome':{'enum':['pass','fail','unknown']},'review':TEXT,'limitations':STRINGS,
        'valid_for_seconds':{'type':'integer','minimum':1,'maximum':86400}},
        ['id','features','observations','candidate_files','reference_files','input_paths','dimensions',
         'producer','operation','context','scope','basis','outcome','review','limitations','valid_for_seconds']),
    _change('deliver_reviewed',{'kind':{'enum':['analysis-report','independent-reimplementation',
        'specification-implementation','modified-original']},'scope':{'enum':['full','stage']},
        'features':STRINGS,'summary':TEXT,'artifacts':STRINGS},['kind','scope','features','summary','artifacts']),
    _change('unknown',{'id':TEXT,'question':TEXT,'critical':{'type':'boolean'},'features':STRINGS,'scope':{'enum':['features','case']}},
            ['id','question','critical','features']),
    _change('resolve',{'id':TEXT,'evidence':STRINGS},['id','evidence']),
    _change('refine_route',{'hint':TEXT,'primary':TEXT},['hint']),
    _change('deliver_analysis',{'report':TEXT,'evidence':STRINGS},['report','evidence']),
    _change('product',{'candidate_files':STRINGS,'reference_files':STRINGS,'review':TEXT,
        'kind':{'enum':['independent-reimplementation','specification-implementation','modified-original']}},
            ['candidate_files','reference_files','review']),
    _change('execute',{'id':TEXT,'kind':{'enum':['investigate','verify','visual','package']},
        'features':STRINGS,'argv':STRINGS,'cwd':TEXT,'inputs':STRINGS,'artifacts':STRINGS,
        'purpose':TEXT,'timeout_seconds':{'type':'number','exclusiveMinimum':0,'maximum':600},
        'reusable':{'type':'boolean','default':False},'retry_reason':TEXT,'environment_keys':STRINGS,
        'scratch_bytes':{'type':'integer','minimum':1048576}},
        ['id','kind','features','argv','inputs','purpose']),
    _change('budget',{'max_checks_per_feature':{'type':'integer','minimum':1,'maximum':100},
                      'max_operation_failures':{'type':'integer','minimum':1,'maximum':100},'reason':TEXT},['reason']),
    _change('coverage',{'review':TEXT,'requirements':{'type':'array','minItems':1,'items':{
        'type':'object','properties':{'id':TEXT,'text':TEXT,'source':TEXT,'features':STRINGS},
        'required':['id','text','source','features'],'additionalProperties':False}}},['review','requirements']),
    _change('deliver_stage',{'summary':TEXT,'artifacts':STRINGS,'features':STRINGS},['summary','artifacts','features']),
    _change('deliver',{'summary':TEXT,'artifacts':STRINGS},['summary','artifacts'])]}


TOOLS = [
    _tool('rf_next_case_open','Optional goal memory. Use native host records when sufficient; skip creates no case, case explicitly opts in. Route hints are advisory.',
          {'request':{'type':'string'},'case_root':{'type':'string','description':'Explicit case location. Omit to discover the only existing case on continuation.'},
           'recording':{'enum':['auto','case','skip'],'default':'auto'}},['request']),
    _tool('rf_next_case_status','Read optional task memory, acceptance diagnostics, automatic checks and separately labeled external host reviews. Readiness never forbids native investigation or editing.',{},[]),
    _tool('rf_next_case_record','Optional checkpoint, requirement, external evidence assessment or explicit output agreement/delivery. Optimistic revisions; host review never writes automatic/native pass.',
          {'change':CHANGE,'expected_revision':{'type':'integer','minimum':1}},['change','expected_revision']),
    _tool('rf_next_compare','Optional finite process/web comparison or public REA verification adapter. Source execution uses owned copies where applicable; not an OS sandbox. Other tools and host-reviewed external evidence remain available.',
          {'check_id':{'type':'string'},'plan':{'type':'string'},'output':{'type':'string'},'retry_reason':{'type':'string'}},['check_id','plan','output']),
    _tool('rf_next_storage','Allocate persistent/reusable/disposable outputs at creation. Complete after all users stop; review at natural operation boundaries reclaims completed disposable data and requests host keep/release decisions for reusable data. Reuse verifies dependencies/content; promote returns a new persistent path. Persistent, active and protected data survive cleanup. Status is read-only; never adopt old folders.',
          {'action':{'enum':['status','sweep','allocate','complete','policy','protect','unprotect','review','reuse','promote'],'default':'status'},
           'purpose':TEXT,'rebuild':TEXT,'reserve_bytes':{'type':'integer','minimum':1},'id':TEXT,
           'cleanup':{'type':'boolean','default':True},
           'generation':{'type':'integer','minimum':1,'description':'Echo the allocation or reuse generation to bind complete/reuse to that use.'},
           'tier':{'enum':['persistent','reusable','disposable'],'default':'disposable'},
           'reuse_key':TEXT,'reuse_reason':TEXT,'input_paths':STRINGS,
           'boundary':{'enum':['operation-end','verification-end','stage-change','task-end','space-pressure','resume']},
           'decisions':{'type':'array','items':{'type':'object','properties':{
               'id':TEXT,'decision':{'enum':['keep','release']},'reason':TEXT},
               'required':['id','decision','reason'],'additionalProperties':False}},
           'paths':STRINGS,'policy':{'type':'object','properties':{
               'max_temporary_bytes':{'type':'integer','minimum':1},'minimum_free_bytes':{'type':'integer','minimum':0},
               'max_reusable_bytes':{'type':'integer','minimum':0},'reuse_review_seconds':{'type':'integer','minimum':0},
               'minimum_free_fraction':{'type':'number','minimum':0,'maximum':.5},
               'completed_ttl_seconds':{'type':'integer','minimum':0},'interrupted_ttl_seconds':{'type':'integer','minimum':0}},
               'additionalProperties':False}},[])]
NAMES={tool['name'] for tool in TOOLS}


def connection_identity(root=ROOT):
    names=[p.relative_to(root).as_posix() for p in (root/'rea_enhanced').glob('*.py')]
    names += [p.relative_to(root).as_posix() for p in (root/'reverse_fusion').glob('*.py')]
    names+=['components/rea-enhanced/web-replay.mjs','components/reverse-core/router.py',
            'components/reverse-core/runtime.json','components/reverse-core/routing.json',
            'vendor/rea/manifest.json','vendor/node/manifest.json']
    return {name:digest(root/name) for name in sorted(names)}


def require_current_connection(initial,root=ROOT):
    if connection_identity(root)!=initial:
        raise ValueError('needs-reconnect: enhanced runtime changed since this connection started. Reconnect MCP before using this connection; the absolute scripts/next-cli.py entry reads the current version. No old workflow operation was executed.')


def call_owned(name, args, cancel_event=None):
    if not isinstance(args,dict):raise ValueError('Tool arguments must be an object')
    schema=next(t['inputSchema'] for t in TOOLS if t['name']==name)
    if set(args)-set(schema['properties']) or any(k not in args for k in schema['required']):
        raise ValueError('Missing or extra tool arguments')
    project=Path(args['project_root'])
    if not project.is_absolute() or not project.is_dir() or project.resolve()==ROOT.resolve():
        raise ValueError('Select an existing absolute outcome project, not the shared tool checkout')
    case=args.get('case_root','work/current-case')
    if name=='rf_next_storage':
        from .disk import dispatch
        return dispatch(project, **{k:v for k,v in args.items() if k not in {'project_root','case_root'}})
    if name=='rf_next_case_open':return open_case(project,args['request'],args.get('case_root'),recording=args.get('recording','auto'))
    if name=='rf_next_case_status':return status(project,case)
    if name=='rf_next_case_record':
        if not isinstance(args['change'], dict) or not isinstance(args['change'].get('op'), str):
            raise ValueError('change must be an object with a string operation')
        if args['change'].get('op') == 'execute':
            from .operations import execute
            return execute(project,case,args['change'],args['expected_revision'],cancel_event=cancel_event)
        return record(project,case,args['change'],args['expected_revision'])
    result=run_check(project,case,args['check_id'],args['plan'],args['output'],cancel_event=cancel_event,retry_reason=args.get('retry_reason'))
    if 'comparison' not in result:return result
    receipt=result['comparison']
    return {'status':receipt['status'],'result_path':str(project/result['receipt_path']), 'reused':result.get('reused',False),
        'differences':[{'scenario':r['scenario'],'step':r['step'],'channels':r['differences'],'status':r['status']}
            for r in receipt['cases'] if r['status']!='pass'][:20],
        'workflow':result['workflow'],'rea_native_proof':receipt.get('rea_native_proof','not-performed')}


def startup_runtime(root):
    identity = node_identity(root, enforce_prepared=True)
    entry = inside(root / 'vendor/rea', read(root / 'vendor/rea/manifest.json')['entry'])
    if not identity['configured'] or not entry.is_file():
        raise ValueError('Install the pinned REA runtime in this checkout first')
    entry_sha = digest(entry)
    if identity['prepared'] and entry_sha != read(root / 'state/rea-runtime.json').get('official_entry_sha256'):
        raise ValueError('Selected REA entry differs from the prepared installation')
    return {
        'node': identity['node'], 'runtime_source': identity['runtime_source'],
        'node_sha256': identity['node_sha256'], 'node_pin_status': identity['status'],
        'official_entry': str(entry), 'official_entry_sha256': entry_sha,
    }


def serve():
    loaded_identity=connection_identity()
    runtime = startup_runtime(ROOT)
    environment=launch_environment(ROOT)
    environment.update(REA_MCP_INPUT_SCHEMA_PROFILE='compact',REA_MCP_OUTPUT_SCHEMA_PROFILE='compact')
    owner=McpProcess([runtime['node'],runtime['official_entry'],'mcp'],cwd=ROOT,env=environment)
    upstream=owner.process
    output_lock, input_lock, pending_lock = threading.Lock(), threading.Lock(), threading.Lock()
    pending={}
    ended=threading.Event()
    from .disk import maintenance_loop
    janitor=threading.Thread(target=maintenance_loop,args=(ended,),
        kwargs={'guard':lambda: connection_identity()==loaded_identity},daemon=True)
    janitor.start()
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
                        result.setdefault('_meta', {})[RUNTIME_META] = runtime
                        result['instructions']=result.get('instructions','')+'\nOriginal REA tools and Evidence are unchanged. rf_next_* is optional task memory/check support, not a required tool order. Use native/other suitable tools directly. Readiness is acceptance guidance only. External host-reviewed results are distinct from automatic/native proof. Upstream: '+str(original.get('name'))+' '+str(original.get('version'))
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
            require_current_connection(loaded_identity)
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
            if message.get('method') == 'tools/call' and not isinstance(params.get('name'), str):
                emit({'jsonrpc':'2.0','id':identity,'error':{'code':-32602,'message':'Tool name must be a string'}})
                continue
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
        janitor.join(timeout=2)
    return 0
