"""Codex entry migration, owned-region rollback and actual registered MCP probe.

Only owned sections are persisted in recovery receipts. Full user configuration
is held in memory during a transaction, never copied to the repository.
"""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tomllib
import uuid
from reverse_fusion.file_updates import atomic_write, file_transaction
from reverse_fusion.global_adapter import (adapter_paths, agents_block, _agents_region,
    _updated_agents, _block_repository)
from .storage import locked, read, write

BEGIN=b'# reverse-fusion:mcp:begin'
END=b'# reverse-fusion:mcp:end'
ROOT=Path(__file__).resolve().parents[1]


def skill_text(root):
    repo=root.resolve().as_posix()
    return f'''---
name: reverse-fusion
description: 分析软件并复刻、APK/网站/原生程序逆向、行为重建、专业安全分析，以及显式Reverse Fusion任务。使用共享Reverse方法和增强REA，保留完整目标。
---

# Reverse Fusion cross-project adapter

The canonical checkout is `{repo}` (enhanced REA v2). Keep the current user project
as the outcome workspace. Ordinary development remains host-native without a case.
Read `{repo}/docs/AGENT-WORKFLOW.md` and `{repo}/RULES.md` before specialist work.

Use MCP `rf_next_case_open` with absolute project_root and the original plain-language
request. Resume the same case on follow-up; record new requirements as supplements.
If MCP is absent in this chat, use the identical CLI:
`& "{repo}/.venv/Scripts/python.exe" "{repo}/scripts/next-cli.py" open --project-root "<outcome project>" --request "<original words>"`.
Its returned domain skill/required_read_paths and official REA skill are mandatory
reads before selecting methods. Do not copy the domain tree or change cwd to the
shared checkout. Tool paths come from saved providers; actual operations determine health.

Read status and readiness before implementation. Preserve the full objective, evidence,
affected unknowns and remaining features in the same case. Current host is the only
reasoning/coding agent and edits/builds in its native tools. Craft is not used; Spec is
optional. Do not start another AI loop. Export the original REA evidence bundle into
the outcome case before ending its investigation and import it on restart. Do not
invent native evidence IDs or call owned comparison receipts official REA proof.

Use existing official REA tools and appropriate installed tools; do not handwrite
replacement decompilers. Refine the domain in the same case as evidence changes.
Authorization/key availability is a dependency, not a fixed instruction to bypass,
debug or dump; choose methods from evidence and the authorized task. Missing facts
block dependent functions while independent work continues. Ask concrete human
questions only for unavailable information or product decisions.

Record features with evidence, dependencies, semantic review and declared checks.
Before delivery, record coverage mapping every original/supplement source to features,
then deliver with actual artifacts after fresh comparisons. Read the operation schemas
from rf_next_case_record or COMPARISON.md; do not guess required fields. A new goal
against an occupied case returns needs-context; choose a new case or explicit supplement.
Run rf_next_compare or CLI compare against an independent reference with a reviewed
finite plan. Separate visual and behavior results. A screenshot, exit zero or candidate
unit test does not close the whole product goal. Changes invalidate old checks. Reuse
unchanged passes, require new information to retry failures, retain unknowns and stop
unproductive loops. Read `{repo}/docs/COMPARISON.md` for schemas and boundaries,
`{repo}/docs/RECOVERY.md` for interruption and recovery. Do not shrink the request to a
demo. Report actual tested scope, remaining requirements and concrete next steps.

Keep the host's judgment and normal tools. Work on independent observable behaviors,
with unknowns limited to affected behavior. Inspect status diagnostics when progress
drifts. Observations default to immutable snapshots; use retention=live for changing
specifications or dependencies. Do not re-register a historical report against a
mutable build-current file. Use the optional record execute operation for expensive
scripts when measured cost/reuse helps; exit zero is never acceptance. Prefer focused
source/API replay for backend changes, affected full-scroll UI checks for UI changes,
and package checks at integration milestones. No screenshot or clean-package loop
is required after every edit. Register product identity before reconstruction delivery.
Record every substantive user supplement; a follow-up is not permission to drop the goal.

Read `{repo}/docs/DISK-MANAGEMENT.md` before operations that can produce large temporary
outputs. Classify outputs when created: tier=persistent for durable material (normal original,
code, evidence and delivery paths also stay persistent); tier=reusable for rebuildable material
with a concrete next use, reuse_key/reuse_reason and input_paths; tier=disposable (default) for
single-operation copies/profiles/intermediate packages. Allocate realistic reserve_bytes and
reconstruction instructions, route output to the returned path, and complete only after all
users/processes stop. Disposable data is reclaimed immediately; other tiers stay. Use reuse
to verify reusable inputs/content and mark a new active use; complete that use afterwards.
At the end of a meaningful operation batch/verification, phase change, resume or space pressure,
use storage review with the corresponding boundary. It reclaims completed disposable data and
returns reusable items needing a host keep/release judgment with a concrete reason. Do not turn
every command into a review ritual. Keep a useful cache for a stated next use; release it when
rebuilding is preferable. Promote completed unreferenced durable material to persistent and use
the returned new path; referenced paths remain stable and protected. Persistent data cannot be
downgraded. Age prompts cache review, never automatic cache deletion. Active work and evidence
protection take priority. Enhanced comparisons/execute manage their own disposable work.
Avoid full copies/packages per edit. Manual allocations remain active until completed. The
connection's timer only reclaims eligible disposable data; it starts no second reasoning agent.
Unregistered folders are retained. These tiers also cover ordinary large builds without a case.

For installation only, follow `{repo}/docs/AGENT-BOOTSTRAP.md`. Never run inherited v1
installers or standalone REA setup over this managed install. One owned MCP endpoint
reverse-fusion-rea serves original tools plus enhancements. mcp-check probes the
registered command; existing chats may require reconnect. No model/config/credential
changes beyond this installer's owned skill, AGENTS block and MCP block.
'''


def _paths(home=None):
    paths=adapter_paths(home)
    return {**paths,'config':paths['agents'].parent/'config.toml'}


def _adopt_legacy(payload,parsed,owner):
    """Codex may reserialize TOML and drop ownership comments. Explicit owner only."""
    from reverse_fusion.mcp_adapter import _registrations
    owner=Path(owner).resolve()
    actual=parsed.get('mcp_servers',{})
    names=set(actual)&{'reverse-fusion-rea','reverse-fusion-craft'}
    enhanced=names=={'reverse-fusion-rea'}
    expected={'reverse-fusion-rea':registration(owner)} if enhanced else _registrations(owner)
    if any(actual.get(name)!=value for name,value in expected.items()):
        raise ValueError('Unmarked legacy entries do not exactly match the explicit previous checkout')
    headers=list(re.finditer(rb'(?m)^[ \t]*\[[^\r\n]+\][ \t]*(?:#[^\r\n]*)?(?:\r?\n|$)',payload))
    first=next((m for m in headers if m[0].strip()==b'[mcp_servers.reverse-fusion-rea]'),None)
    last=first if enhanced else next((m for m in headers if m[0].strip()==b'[mcp_servers.reverse-fusion-craft]'),None)
    if not first or not last or last.start()<first.start():raise ValueError('Legacy section layout requires explicit review')
    after=next((m.start() for m in headers if m.start()>last.start()),len(payload))
    end=after
    marker=re.search(rb'(?m)^'+re.escape(END)+rb'(?:\r?\n|$)',payload[first.start():after])
    if marker:end=first.start()+marker.end()
    block=payload[first.start():end]
    own=tomllib.loads(block.decode('utf-8'))
    if own!={'mcp_servers':expected}:raise ValueError('Unmarked legacy span contains unrelated configuration')
    if any(line.lstrip().startswith(b'#') and line.strip()!=END for line in block.splitlines()):
        raise ValueError('Unmarked legacy span has unowned comments; preserve them for review')
    return {'start':first.start(),'end':end,'owner':owner,'existed':True,'separator':0,
        'adopted':'enhanced-exact' if enhanced else 'legacy-exact'}


def _mcp_region(payload,legacy_owner=None,current_owner=None):
    parsed=tomllib.loads(payload.decode('utf-8-sig'))
    selected_owner=current_owner or legacy_owner
    if selected_owner and payload.count(BEGIN)==0 and payload.count(END)<=1:
        if any(name in parsed.get('mcp_servers',{}) for name in ('reverse-fusion-rea','reverse-fusion-craft')):
            return _adopt_legacy(payload,parsed,selected_owner)
    # Codex may move a retired end comment to EOF. With no registration and no
    # begin block it owns nothing; retain the harmless original comment bytes.
    if (payload.count(BEGIN)==0 and payload.count(END)<=1
            and not {'reverse-fusion-rea','reverse-fusion-craft'} & set(parsed.get('mcp_servers',{}))):
        return None
    if BEGIN not in payload and END not in payload:return None
    if payload.count(BEGIN)!=1 or payload.count(END)<1:raise ValueError('Duplicate/incomplete MCP ownership markers')
    match=re.search(rb'^'+re.escape(BEGIN)+rb'\r?\n',payload,re.M)
    # A Codex rewrite may have moved the old orphan end comment to EOF. It is
    # outside our exact replacement span and must remain untouched, not counted
    # as a second owned block. Match this begin's first following terminator.
    end=re.compile(rb'^'+re.escape(END)+rb'(?:\r?\n|$)',re.M).search(payload,match.end()) if match else None
    if not match or not end or end.start()<=match.start():raise ValueError('Invalid MCP marker order')
    block=payload[match.start():end.end()]
    def meta(name):
        values=re.findall(rb'^# reverse-fusion:mcp:'+name.encode()+rb' = ([^\r\n]+)',block,re.M)
        if len(values)!=1:raise ValueError('Invalid MCP ownership metadata')
        return json.loads(values[0])
    owner=meta('repository'); separator=meta('added-separator'); existed=meta('original-config-existed')
    if not isinstance(owner,str) or not Path(owner).is_absolute() or type(separator)!=int or separator not in (0,1) or type(existed)!=bool:
        raise ValueError('Invalid MCP ownership identity')
    if b'# reverse-fusion:mcp:format = 2' not in block:
        from reverse_fusion.mcp_adapter import _managed
        old=_managed(payload,parsed)
        return {'start':old.start,'end':old.end,'owner':old.repository,'existed':old.original_existed,'separator':old.separator}
    owned=tomllib.loads(block.decode('utf-8'))
    registrations=owned.get('mcp_servers',{})
    if set(owned)!={'mcp_servers'} or set(registrations)!={'reverse-fusion-rea'}:
        raise ValueError('Unrelated content in owned MCP block')
    canonical=json.dumps(registrations,sort_keys=True,separators=(',',':')).encode()
    if sha256(canonical).hexdigest()!=meta('sha256'):raise ValueError('Owned MCP block changed; preserve for review')
    entry=registrations['reverse-fusion-rea']
    if parsed.get('mcp_servers',{}).get('reverse-fusion-rea')!=entry or entry.get('cwd')!=owner:
        raise ValueError('Owned MCP entry extended outside block or changed owner')
    start=match.start()-separator
    if start<0 or separator and payload[start:match.start()]!=b'\n':raise ValueError('MCP append separator changed')
    return {'start':start,'end':end.end(),'owner':Path(owner).resolve(),'existed':existed,'separator':separator}


def _region(kind,payload,legacy_owner=None,current_owner=None):
    if kind=='skill':return {'start':0,'end':len(payload)} if payload else None
    if kind=='config':return _mcp_region(payload,legacy_owner,current_owner)
    region=_agents_region(payload)
    if region:
        region['owner']=_block_repository(region['block'])
        region['existed']=region.get('metadata',{}).get('original_existed',True) if region.get('metadata') else True
    return region


def _skill_owner(payload):
    if b'# Reverse Fusion cross-project adapter' not in payload:raise ValueError('Existing skill is unmanaged')
    match=re.search(rb'The canonical checkout is `([^`]+)`',payload)
    if not match or not Path(match[1].decode()).is_absolute():raise ValueError('Skill checkout identity missing')
    return Path(match[1].decode()).resolve()


def registration(root):
    python=root/'.venv/Scripts/python.exe'
    if not python.is_file():raise ValueError('Repository Python environment missing')
    return {'command':str(python),'args':['-m','rea_enhanced','mcp'],'cwd':str(root),
            'startup_timeout_sec':60,'tool_timeout_sec':600}


def _render(root, separator, existed):
    registrations={'reverse-fusion-rea':registration(root)}
    checksum=sha256(json.dumps(registrations,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    q=lambda x:json.dumps(x,ensure_ascii=False)
    lines=[BEGIN.decode(),'# reverse-fusion:mcp:format = 2',
        '# reverse-fusion:mcp:repository = '+q(str(root)),
        '# reverse-fusion:mcp:added-separator = '+str(separator),
        '# reverse-fusion:mcp:original-config-existed = '+str(existed).lower(),
        '# reverse-fusion:mcp:sha256 = '+q(checksum),'','[mcp_servers.reverse-fusion-rea]']
    lines.extend(key+' = '+q(value) for key,value in registrations['reverse-fusion-rea'].items())
    return b'\n'*separator+('\n'.join(lines)+'\n'+END.decode()+'\n').encode()


def probe(root=ROOT,home=None):
    from reverse_fusion.mcp_probe import StdioMcp,catalog
    from .providers import environment
    path=_paths(home)['config'];payload=path.read_bytes();region=_mcp_region(payload,current_owner=root)
    if not region or region['owner']!=root.resolve():raise ValueError('Selected checkout is not the registered MCP owner')
    entries=tomllib.loads(payload.decode('utf-8-sig'))['mcp_servers']
    entry=entries['reverse-fusion-rea']
    if entry!=registration(root.resolve()):raise ValueError('Registered command differs from this release')
    with StdioMcp([entry['command'],*entry['args']],cwd=Path(entry['cwd']),env=environment(root),timeout=60) as client:
        identity=client.initialize();tools=catalog(client)
        if identity['serverInfo']['name']!='rea-enhanced':raise ValueError('Unexpected enhanced REA server')
        if not {'binary_session','rf_next_case_open','rf_next_compare','rf_next_storage'}<={t['name'] for t in tools}:raise ValueError('Required tool interfaces missing')
        observed={}
        for name in ('binary_session','list_frida_devices'):
            result=client.request('tools/call',{'name':name,'arguments':{}})
            if result.get('isError'):raise ValueError('Registered operation failed: '+name)
            observed[name]=result
    if client.cleanup.get('status')!='verified':raise ValueError('MCP child cleanup not verified')
    report={'status':'pass','repository':str(root),'registered':entry,'server':identity['serverInfo'],
        'tools':len(tools),'operations':observed,'cleanup':client.cleanup,
        'scope':'Actual registered stdio connection and target-free calls, not desktop hot reload or all provider operations'}
    write(root/'state/next-mcp-check.json',report)
    return report


def install(root=ROOT, home=None, replace_from=None, check=True):
    root=root.resolve();paths=_paths(home);allowed={root}
    if replace_from:allowed.add(Path(replace_from).resolve())
    with locked(paths['config'].parent/'reverse-fusion-install.json'):
        originals={k:p.read_bytes() if p.is_file() else b'' for k,p in paths.items()}
        skill_owner=_skill_owner(originals['skill']) if originals['skill'] else None
        agents_region=_region('agents',originals['agents'])
        current_owner=root if skill_owner==root and agents_region and agents_region.get('owner')==root else None
        regions={k:_region(k,value,replace_from,current_owner) for k,value in originals.items()}
        for kind,payload in originals.items():
            region=regions[kind]
            owner=_skill_owner(payload) if kind=='skill' and payload else region.get('owner') if region else None
            if payload and kind=='skill' or region:
                if owner not in allowed:raise ValueError('Entry belongs to another checkout; explicit --replace-from is required')
        config=originals['config'];parsed=tomllib.loads(config.decode('utf-8-sig'))
        current=regions['config'];servers=parsed.get('mcp_servers',{})
        if not current and any(k in servers for k in ('reverse-fusion-rea','reverse-fusion-craft')):
            raise ValueError('Conflicting unmanaged MCP registration')
        fragment=_render(root,current['separator'] if current else int(bool(config) and not config.endswith(b'\n')),
                         current['existed'] if current else paths['config'].is_file())
        updated={'skill':skill_text(root).encode(),
            'agents':_updated_agents(originals['agents'],agents_block(root),root,original_existed=paths['agents'].is_file()),
            'config':config[:current['start']]+fragment+config[current['end']:] if current else config+fragment}
        snapshot={'schema_version':2,'repository':str(root),'status':'prepared','files':{},
            'previous_repository':str(Path(replace_from).resolve()) if replace_from else None}
        for kind,after in updated.items():
            before=originals[kind];b=regions[kind];a=_region(kind,after)
            snapshot['files'][kind]={'path':str(paths[kind]),'file_existed':paths[kind].is_file(),
                'before':base64.b64encode(before[b['start']:b['end']] if b else b'').decode(),
                'after_sha256':sha256(after[a['start']:a['end']]).hexdigest()}
            if kind=='config':snapshot['files'][kind]['after_registration']=registration(root)
        receipt=root/'state/migrations'/(uuid.uuid4().hex+'.json')
        write(receipt,snapshot)
        try:
            for kind,data in updated.items():atomic_write(paths[kind],data)
            checked=probe(root,home) if check else {'status':'not-run'}
        except Exception as exc:
            for kind,p in paths.items():
                current_payload=p.read_bytes() if p.is_file() else b''
                if current_payload==originals[kind]:continue
                region=_region(kind,current_payload,replace_from,root)
                if not region or sha256(current_payload[region['start']:region['end']]).hexdigest()!=snapshot['files'][kind]['after_sha256']:
                    raise ValueError('Deployment interrupted and owned entry changed; use prepared recovery receipt: '+str(receipt)) from exc
                restored=current_payload[:region['start']]+base64.b64decode(snapshot['files'][kind]['before'])+current_payload[region['end']:]
                if restored or snapshot['files'][kind]['file_existed']:atomic_write(p,restored)
                else:p.unlink(missing_ok=True)
            snapshot.update(status='failed-restored',error_type=type(exc).__name__);write(receipt,snapshot)
            raise ValueError('Deployment connection failed; previous owned entries restored: '+str(exc)) from exc
        snapshot['status']='installed';write(receipt,snapshot)
        return {'status':'installed','repository':str(root),'rollback_receipt':str(receipt),'mcp_check':checked,
            'desktop_reconnect_required':True,'owned_servers':['reverse-fusion-rea']}


def uninstall(root=ROOT,home=None):
    """Remove this exact owner's entry; retain source/runtime and every unrelated byte."""
    root=root.resolve();paths=_paths(home)
    with locked(paths['config'].parent/'reverse-fusion-install.json'):
        originals={k:p.read_bytes() if p.is_file() else b'' for k,p in paths.items()}
        skill_owner=_skill_owner(originals['skill']) if originals['skill'] else None
        agents_region=_region('agents',originals['agents'])
        current=root if skill_owner==root and agents_region and agents_region.get('owner')==root else None
        regions={k:_region(k,v,root,current) for k,v in originals.items()}
        if originals['skill'] and skill_owner!=root:raise ValueError('Skill belongs to another checkout')
        if originals['skill'].replace(b'\r\n',b'\n')!=skill_text(root).encode().replace(b'\r\n',b'\n') and originals['skill']:
            raise ValueError('Owned skill changed; preserve it for review')
        for kind in ('agents','config'):
            if regions[kind] and regions[kind]['owner']!=root:raise ValueError('Entry belongs to another checkout')
        if agents_region:
            from reverse_fusion.global_adapter import _agents_digest
            metadata=agents_region.get('metadata')
            if not metadata or _agents_digest(agents_region['block'])!=metadata['block_sha256']:
                raise ValueError('Owned AGENTS instructions changed; preserve them for review')
        updated={}
        for kind,payload in originals.items():
            region=regions[kind]
            if region:
                updated[kind]=payload[:region['start']]+payload[region['end']:]
        with file_transaction(paths.values()):
            for kind,payload in updated.items():
                existed=regions[kind].get('existed',False)
                if payload or existed:atomic_write(paths[kind],payload)
                else:paths[kind].unlink(missing_ok=True)
        return {'status':'uninstalled','repository':str(root),'removed_owned_regions':sorted(updated),
            'unrelated_before_sha256':{k:sha256(v[:regions[k]['start']]+v[regions[k]['end']:] if regions[k] else v).hexdigest()
                                      for k,v in originals.items() if k!='skill'},
            'scope':'Owned entries only; runtime/source retained for recovery. Existing desktop connections require closing/reconnecting.'}


def rollback(receipt,root=ROOT):
    snapshot=read(Path(receipt));root=root.resolve()
    if snapshot.get('repository')!=str(root) or snapshot.get('status') not in {'installed','prepared'}:
        raise ValueError('Recovery receipt is not an active transaction from this checkout')
    records=snapshot['files'];paths=[Path(r['path']) for r in records.values()]
    with locked(paths[-1].parent/'reverse-fusion-install.json'):
        outputs={}
        for kind,record in records.items():
            path=Path(record['path']);payload=path.read_bytes() if path.is_file() else b''
            # Original entries in a partially written transaction use the old owner.
            # An installed enhanced entry can be recognized after Codex drops comments.
            selected=root if snapshot['status']=='installed' else None
            region=_region(kind,payload,snapshot.get('previous_repository'),selected)
            if snapshot['status']=='prepared':
                before=base64.b64decode(record['before'])
                if (region and payload[region['start']:region['end']]==before) or (not region and not before):continue
            semantic_config=(kind=='config' and region and region.get('adopted')=='enhanced-exact'
                and record.get('after_registration')==registration(root))
            if not region or (sha256(payload[region['start']:region['end']]).hexdigest()!=record['after_sha256'] and not semantic_config):
                raise ValueError('Owned entry changed after installation; preserve it for review')
            outputs[path]=(payload[:region['start']]+base64.b64decode(record['before'])+payload[region['end']:],record['file_existed'])
        with file_transaction(paths):
            for path,(data,existed) in outputs.items():
                if not data and not existed:path.unlink()
                else:atomic_write(path,data)
        snapshot['status']='rolled-back';write(Path(receipt),snapshot)
    return {'status':'rolled-back','receipt':str(receipt),'scope':'Owned regions restored; current unrelated bytes retained'}
