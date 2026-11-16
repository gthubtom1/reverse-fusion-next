"""One enhanced REA stdio endpoint, forwarding original RPC results unchanged.

Only server identity, instructions and the first tool-catalog page are augmented.
Original evidence records, resources, prompts, canonical schemas and errors stay
with the official backend. No Craft or Spec executable is started.
"""
import json
from pathlib import Path
import sys
import threading
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


TOOLS = [
    _tool('rf_next_case_open','Preserve a plain-language goal or resume its existing case. Ordinary development remains host-native.',
          {'request':{'type':'string'}},['request']),
    _tool('rf_next_case_status','Read original goal, feature readiness, affected unknowns and fresh finite checks. Does not claim whole-product completion.',{},[]),
    _tool('rf_next_case_record','Record evidence, a feature, a dependent unknown or a user supplement with optimistic revision checking. Cannot post a check pass.',
          {'change':{'type':'object'},'expected_revision':{'type':'integer','minimum':1}},['change','expected_revision']),
    _tool('rf_next_compare','Execute the reviewed finite comparison plan in separate working copies. Actual executable effects; not an OS sandbox. Saves full receipts and returns a compact result.',
          {'check_id':{'type':'string'},'plan':{'type':'string'},'output':{'type':'string'}},['check_id','plan','output'])]
NAMES={tool['name'] for tool in TOOLS}


def call_owned(name, args):
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
    result=run_check(project,case,args['check_id'],args['plan'],args['output'])
    if 'comparison' not in result:return result
    receipt=result['comparison']
    return {'status':receipt['status'],'result_path':str(project/(args['output']+'/comparison.json')),
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
    def owned_request(message):
        try:
            params=message.get('params',{})
            result=call_owned(params['name'],params.get('arguments',{}))
            reply={'content':[{'type':'text','text':json.dumps(result,ensure_ascii=True)}],'structuredContent':result}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            reply={'isError':True,'content':[{'type':'text','text':str(exc)}]}
        try:emit({'jsonrpc':'2.0','id':message['id'],'result':reply})
        except (OSError,ValueError):pass
    try:
        for line in sys.stdin.buffer:
            if ended.is_set():break
            try:message=json.loads(line)
            except ValueError:
                emit({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Parse error'}});continue
            params=message.get('params',{})
            if message.get('method')=='tools/call' and params.get('name') in NAMES:
                threading.Thread(target=owned_request,args=(message,),daemon=True).start()
            else:
                method=message.get('method')
                if 'id' in message and method in {'initialize','tools/list'}:
                    kind='tools/list:first' if method=='tools/list' and not params.get('cursor') else method
                    with pending_lock:pending[message['id']]=kind
                forward(message)
    finally:
        owner.close()
        for thread in threads:thread.join(timeout=1)
    return 0
