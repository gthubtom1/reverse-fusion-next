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
import tempfile
import tomllib
import uuid
from reverse_fusion.global_adapter import (adapter_paths, agents_block, _agents_region,
    _updated_agents, _block_repository)
from .storage import locked, read, write

BEGIN=b'# reverse-fusion:mcp:begin'
END=b'# reverse-fusion:mcp:end'
ROOT=Path(__file__).resolve().parents[1]


def _payload(path):
    return path.read_bytes() if path.is_file() else None


class _ConcurrentCommit(ValueError):
    """A non-cooperating writer raced the commit; its actual bytes are retained."""
    def __init__(self, path, backup):
        self.backup = str(backup)
        super().__init__('Concurrent configuration save detected during replacement: '
                         +str(path)+'; displaced bytes retained at '+str(backup))


def _replace_windows(path, temporary, backup):
    import ctypes
    from ctypes import wintypes
    replace = ctypes.WinDLL('kernel32', use_last_error=True).ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                       wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL
    if not replace(str(path), str(temporary), str(backup), 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def _replace_checked(path, expected, data):
    """Stage first, then check the preimage immediately before replacing it.

    The install lock coordinates our writers. Other editors are not lock-aware;
    a changed preimage is a conflict, never a reason to restore a stale full file.
    """
    temporary = None;backup = None;retain_backup = False
    try:
        if data is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.rf-update-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        if _payload(path) != expected:
            raise ValueError('Concurrent configuration save detected before replacement: '+str(path))
        if os.name == 'nt' and expected is not None:
            # ReplaceFile records the actual displaced preimage atomically.
            # This also detects saves in the final check-to-replace window.
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.rf-previous-', delete=False) as stream:
                backup = Path(stream.name)
            backup.unlink()
            retain_backup = True
            try:
                if data is None:
                    os.rename(path, backup)
                else:
                    _replace_windows(path, temporary, backup)
                if backup.read_bytes() != expected:
                    raise _ConcurrentCommit(path, backup)
                retain_backup = False
            except OSError:
                if backup.exists():
                    retain_backup = True
                    raise _ConcurrentCommit(path, backup)
                raise
        elif data is None:
            path.unlink(missing_ok=True)
        elif os.name == 'nt':
            # Windows rename fails if another writer creates this absent path.
            try:os.rename(temporary, path)
            except FileExistsError as exc:
                raise ValueError('Concurrent configuration save detected before creation: '+str(path)) from exc
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if backup is not None and not retain_backup:
            backup.unlink(missing_ok=True)


def _restore_record(path, payload, region, replacement=b''):
    remaining=payload[:region['start']]+payload[region['end']:]
    return {'path':str(path),'owned':base64.b64encode(payload[region['start']:region['end']]).decode(),
        'replacement':base64.b64encode(replacement).decode(),'offset':region['start'],
        'remaining_size':len(remaining),'remaining_sha256':sha256(remaining).hexdigest()}


def _restore_owned(snapshot, receipt, root):
    """Undo owned-region removals without restoring an unrelated full-file snapshot."""
    conflicts=[];backups=[]
    for kind,record in reversed(list(snapshot['files'].items())):
        try:
            path=Path(record['path']);state=_payload(path);payload=state or b''
            desired=base64.b64decode(record['owned']);replacement=base64.b64decode(record['replacement'])
            try:region=_region(kind,payload,current_owner=root)
            except ValueError:
                region=_region(kind,payload,legacy_owner=snapshot.get('previous_repository'))
            actual=payload[region['start']:region['end']] if region else b''
            if actual==desired:continue
            if actual!=replacement:
                raise ValueError('Owned entry changed during recovery')
            if region:
                data=payload[:region['start']]+desired+payload[region['end']:]
            else:
                # A changed residual is retained. Only an unchanged original
                # prefix/suffix identifies where the removed fragment belongs.
                size=record['remaining_size'];checksum=record['remaining_sha256']
                starts=[]
                for start in {0,len(payload)-size}:
                    if start>=0 and sha256(payload[start:start+size]).hexdigest()==checksum:
                        starts.append(start)
                if size==0:starts=[0]
                if len(starts)!=1 or record['offset']>size:
                    raise ValueError('Unrelated configuration changed at the recovery anchor')
                offset=starts[0]+record['offset']
                data=payload[:offset]+desired+payload[offset:]
            restored=_region(kind,data,current_owner=root)
            if not restored or data[restored['start']:restored['end']]!=desired:
                raise ValueError('Restored ownership span differs')
            _replace_checked(path,state,data)
        except (OSError,ValueError) as exc:
            conflicts.append(kind)
            if isinstance(exc,_ConcurrentCommit):backups.append(exc.backup)
    if conflicts:
        snapshot['recovery_conflicts']=conflicts
        if backups:snapshot.setdefault('conflict_backups',[]).extend(backups)
        write(receipt,snapshot)
        raise ValueError('Owned-entry recovery has configuration conflicts; retry recovery receipt: '+str(receipt))
    snapshot['status']='restored';snapshot.pop('recovery_conflicts',None)
    write(receipt,snapshot)


def _restore_receipt(root, records, previous_repository=None, lock_path=None):
    snapshot={'schema_version':2,'repository':str(root),'status':'prepared',
        'operation':'restore-owned-entries','files':records,'previous_repository':previous_repository}
    if lock_path:snapshot['lock_path']=str(lock_path)
    receipt=root/'state/migrations'/(uuid.uuid4().hex+'.json')
    write(receipt,snapshot)
    return receipt,snapshot


def skill_text(root):
    repo=root.resolve().as_posix()
    return f"""---
name: reverse-fusion
description: 软件/APK/网站分析与复刻；官方REA、按需Reverse和薄任务适配，保留完整目标。
---

# Reverse Fusion cross-project adapter

The canonical checkout is `{repo}`. Outcomes stay in the user's project.
Read `{repo}/RULES.md`; operations: `{repo}/docs/AGENT-WORKFLOW.md`.
The host chooses methods, order and tools. REA, Reverse and rf_next_* are optional support,
not a required controller. Reuse reliable host records; no mandatory case/workitem or repeated
bookkeeping. Use case/checkpoint only when useful for full-goal retention and recovery.
Readiness describes acceptance gaps, never permission to investigate or edit. Methods load
on demand. Keep official Evidence unchanged; external observations may receive an explicitly
labeled host review, never automatic/native pass. Separate independent source, spec-based
implementation, analysis and modified-original outputs; no silent goal substitution.
Schemas: COMPARISON.md; recovery: RECOVERY.md. Large outputs: DISK-MANAGEMENT.md.
MCP: reverse-fusion-rea; optional CLI: `{repo}/scripts/next-cli.py` with the checkout Python.
Install only through AGENT-BOOTSTRAP.md; retain unrelated configuration and rollback.
No Craft runtime, mandatory Spec or product-internal model loop.
"""


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
    from .server import RUNTIME_META
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
        'runtime':identity.get('_meta',{}).get(RUNTIME_META),
        'tools':len(tools),'operations':observed,'cleanup':client.cleanup,
        'scope':'Actual registered stdio connection and target-free calls, not desktop hot reload or all provider operations'}
    write(root/'state/next-mcp-check.json',report)
    return report


def _verify_skill(payload, owner, path):
    """Accept the canonical skill or a byte-exact skill from an installed receipt."""
    if payload.replace(b'\r\n', b'\n') == skill_text(owner).encode().replace(b'\r\n', b'\n'):
        return
    for receipt in (owner/'state/migrations').glob('*.json'):
        saved = read(receipt)
        entry = saved.get('files', {}).get('skill', {})
        if (saved.get('status') == 'installed' and saved.get('repository') == str(owner)
                and entry.get('path') == str(path) and entry.get('after_sha256') == sha256(payload).hexdigest()):
            return
    # Explicit migration from the preserved v1 adapter still checks its full text.
    from reverse_fusion.global_adapter import skill_text as legacy_skill_text
    if payload.replace(b'\r\n', b'\n') == legacy_skill_text(owner).encode().replace(b'\r\n', b'\n'):
        return
    raise ValueError('Owned skill changed; preserve it for review before installation')


def install(root=ROOT, home=None, replace_from=None, check=True):
    root=root.resolve();paths=_paths(home);allowed={root}
    if replace_from:allowed.add(Path(replace_from).resolve())
    with locked(paths['config'].parent/'reverse-fusion-install.json'):
        original_states={k:_payload(p) for k,p in paths.items()}
        originals={k:value if value is not None else b'' for k,value in original_states.items()}
        skill_owner=_skill_owner(originals['skill']) if originals['skill'] else None
        agents_region=_region('agents',originals['agents'])
        current_owner=root if skill_owner==root and agents_region and agents_region.get('owner')==root else None
        regions={k:_region(k,value,replace_from,current_owner) for k,value in originals.items()}
        for kind,payload in originals.items():
            region=regions[kind]
            owner=_skill_owner(payload) if kind=='skill' and payload else region.get('owner') if region else None
            if payload and kind=='skill' or region:
                if owner not in allowed:raise ValueError('Entry belongs to another checkout; explicit --replace-from is required')
        if originals['skill']:
            _verify_skill(originals['skill'], skill_owner, paths['skill'])
        config=originals['config'];parsed=tomllib.loads(config.decode('utf-8-sig'))
        current=regions['config'];servers=parsed.get('mcp_servers',{})
        if not current and any(k in servers for k in ('reverse-fusion-rea','reverse-fusion-craft')):
            raise ValueError('Conflicting unmanaged MCP registration')
        fragment=_render(root,current['separator'] if current else int(bool(config) and not config.endswith(b'\n')),
                         current['existed'] if current else original_states['config'] is not None)
        updated={'skill':skill_text(root).encode(),
            'agents':_updated_agents(originals['agents'],agents_block(root),root,original_existed=original_states['agents'] is not None),
            'config':config[:current['start']]+fragment+config[current['end']:] if current else config+fragment}
        snapshot={'schema_version':2,'repository':str(root),'status':'prepared','files':{},
            'previous_repository':str(Path(replace_from).resolve()) if replace_from else None}
        for kind,after in updated.items():
            before=originals[kind];b=regions[kind];a=_region(kind,after)
            snapshot['files'][kind]={'path':str(paths[kind]),'file_existed':original_states[kind] is not None,
                'before':base64.b64encode(before[b['start']:b['end']] if b else b'').decode(),
                'after_sha256':sha256(after[a['start']:a['end']]).hexdigest()}
            if kind=='config':snapshot['files'][kind]['after_registration']=registration(root)
        receipt=root/'state/migrations'/(uuid.uuid4().hex+'.json')
        write(receipt,snapshot)
        applied=[]
        try:
            for kind,data in updated.items():
                _replace_checked(paths[kind],original_states[kind],data)
                applied.append(kind)
            checked=probe(root,home) if check else {'status':'not-run'}
        except Exception as exc:
            conflicts=[];backups=[]
            for kind in reversed(applied):
                p=paths[kind]
                try:
                    current_state=_payload(p);current_payload=current_state or b''
                    if current_state==original_states[kind]:continue
                    region=_region(kind,current_payload,replace_from,root)
                    if not region or sha256(current_payload[region['start']:region['end']]).hexdigest()!=snapshot['files'][kind]['after_sha256']:
                        raise ValueError('Owned entry changed')
                    restored=current_payload[:region['start']]+base64.b64decode(snapshot['files'][kind]['before'])+current_payload[region['end']:]
                    _replace_checked(p,current_state,restored if restored or snapshot['files'][kind]['file_existed'] else None)
                except (OSError,ValueError) as recovery_error:
                    conflicts.append(kind)
                    if isinstance(recovery_error,_ConcurrentCommit):backups.append(recovery_error.backup)
            if isinstance(exc,_ConcurrentCommit):backups.append(exc.backup)
            if backups:snapshot['conflict_backups']=backups
            if conflicts:
                snapshot['recovery_conflicts']=conflicts;write(receipt,snapshot)
                raise ValueError('Deployment interrupted with configuration conflicts; use prepared recovery receipt: '+str(receipt)) from exc
            if isinstance(exc,_ConcurrentCommit):
                write(receipt,snapshot)
                raise ValueError(str(exc)+'; use prepared recovery receipt: '+str(receipt)) from exc
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
        if originals['skill']:
            _verify_skill(originals['skill'], root, paths['skill'])
        for kind in ('agents','config'):
            if regions[kind] and regions[kind]['owner']!=root:raise ValueError('Entry belongs to another checkout')
        if agents_region:
            from reverse_fusion.global_adapter import _agents_digest
            metadata=agents_region.get('metadata')
            if not metadata or _agents_digest(agents_region['block'])!=metadata['block_sha256']:
                raise ValueError('Owned AGENTS instructions changed; preserve them for review')
        updated={};records={}
        for kind,payload in originals.items():
            region=regions[kind]
            if region:
                updated[kind]=payload[:region['start']]+payload[region['end']:]
                records[kind]=_restore_record(paths[kind],payload,region)
        receipt,snapshot=_restore_receipt(root,records,lock_path=paths['config'].parent/'reverse-fusion-install.json')
        try:
            for kind,payload in updated.items():
                existed=regions[kind].get('existed',False)
                _replace_checked(paths[kind],originals[kind],payload if payload or existed else None)
            snapshot['status']='uninstalled';write(receipt,snapshot)
        except Exception as exc:
            snapshot['status']='prepared'
            try:_restore_owned(snapshot,receipt,root)
            except (OSError,ValueError) as recovery_error:
                raise ValueError('Uninstall interrupted; recover owned entries with receipt: '+str(receipt)
                    +': '+str(recovery_error)) from exc
            raise
        return {'status':'uninstalled','repository':str(root),'removed_owned_regions':sorted(updated),
            'recovery_receipt':str(receipt),
            'unrelated_before_sha256':{k:sha256(v[:regions[k]['start']]+v[regions[k]['end']:] if regions[k] else v).hexdigest()
                                      for k,v in originals.items() if k!='skill'},
            'scope':'Owned entries only; runtime/source retained for recovery. Existing desktop connections require closing/reconnecting.'}


def rollback(receipt,root=ROOT):
    snapshot=read(Path(receipt));root=root.resolve()
    if snapshot.get('repository')!=str(root) or snapshot.get('status') not in {'installed','prepared'}:
        raise ValueError('Recovery receipt is not an active transaction from this checkout')
    records=snapshot['files']
    lock_path=(Path(snapshot['lock_path']) if snapshot.get('lock_path')
               else Path(records['config']['path']).parent/'reverse-fusion-install.json')
    with locked(lock_path):
        if snapshot.get('operation')=='restore-owned-entries':
            _restore_owned(snapshot,Path(receipt),root)
            return {'status':'restored','receipt':str(receipt),'scope':'Owned entries restored; current unrelated bytes retained'}
        outputs={};restore_records={}
        for kind,record in records.items():
            path=Path(record['path']);current_state=_payload(path);payload=current_state or b''
            # Original entries in a partially written transaction use the old owner.
            # An installed enhanced entry can be recognized after Codex drops comments.
            selected=root
            try:
                region=_region(kind,payload,snapshot.get('previous_repository'),selected)
            except ValueError:
                if snapshot['status']!='prepared' and not snapshot.get('rollback_in_progress'):raise
                region=_region(kind,payload,snapshot.get('previous_repository'))
            if snapshot['status']=='prepared' or snapshot.get('rollback_in_progress'):
                before=base64.b64decode(record['before'])
                if (region and payload[region['start']:region['end']]==before) or (not region and not before):continue
            semantic_config=(kind=='config' and region and region.get('adopted')=='enhanced-exact'
                and record.get('after_registration')==registration(root))
            if not region or (sha256(payload[region['start']:region['end']]).hexdigest()!=record['after_sha256'] and not semantic_config):
                raise ValueError('Owned entry changed after installation; preserve it for review')
            outputs[path]=(current_state,payload[:region['start']]+base64.b64decode(record['before'])+payload[region['end']:],record['file_existed'])
            restore_records[kind]=_restore_record(path,payload,region,base64.b64decode(record['before']))
        # A partial rollback stays resumable. Never use a full-file transaction
        # restore: it could erase an unrelated save made after this read.
        previous_snapshot=dict(snapshot)
        snapshot['rollback_in_progress']=True;write(Path(receipt),snapshot)
        try:
            for path,(expected,data,existed) in outputs.items():
                _replace_checked(path,expected,data if data or existed else None)
        except (OSError,ValueError) as exc:
            if isinstance(exc,_ConcurrentCommit):
                snapshot.setdefault('conflict_backups',[]).append(exc.backup);write(Path(receipt),snapshot)
            raise ValueError('Rollback interrupted; current bytes retained; retry recovery receipt: '+str(receipt)+': '+str(exc)) from exc
        snapshot.pop('rollback_in_progress',None)
        snapshot['status']='rolled-back'
        try:write(Path(receipt),snapshot)
        except (OSError,ValueError) as exc:
            # Terminal receipt failure has the old transactional contract:
            # restore the installed owned fragments, retaining external saves.
            recovery,recovery_snapshot=_restore_receipt(root,restore_records,snapshot.get('previous_repository'),lock_path)
            try:
                _restore_owned(recovery_snapshot,recovery,root)
                write(Path(receipt),previous_snapshot)
            except (OSError,ValueError) as recovery_error:
                raise ValueError('Rollback receipt failed; recover installed entries with receipt: '+str(recovery)
                    +': '+str(recovery_error)) from exc
            raise
    return {'status':'rolled-back','receipt':str(receipt),'scope':'Owned regions restored; current unrelated bytes retained'}
