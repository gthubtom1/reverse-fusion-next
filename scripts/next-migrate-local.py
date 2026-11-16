"""Qualified, owned local migration with actual legacy restore and reconnect."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from rea_enhanced.deployment import install,rollback,probe,_paths,_region
from rea_enhanced.qualification import release_check
from rea_enhanced.storage import read,write,digest
from reverse_fusion.mcp_probe import StdioMcp,catalog


def outside_hashes(previous=None):
    result={}
    for kind,path in _paths().items():
        if kind=='skill':continue
        payload=path.read_bytes();region=_region(kind,payload,previous)
        outside=payload[:region['start']]+payload[region['end']:] if region else payload
        result[kind]=hashlib.sha256(outside).hexdigest()
    return result


def compact(report):
    return {key:report[key] for key in ('status','repository','registered','server','tools','cleanup','scope')}


def main():
    qualification=release_check(ROOT)
    if qualification['status']!='pass':raise ValueError('Release qualification failed before migration: '+str(qualification['failures']))
    frozen=read(ROOT/'baseline/identity.json');old=Path(frozen['source'])
    for item in frozen['global_files'].values():
        if digest(Path(item['path']))!=item['sha256']:raise ValueError('Frozen user entry changed; inspect current ownership before migration')
    before_outside=outside_hashes(old)
    print('Selecting qualified enhanced entry, then testing real restoration',flush=True)
    first=install(ROOT,replace_from=old)
    if outside_hashes()!=before_outside:raise ValueError('Unrelated bytes changed during migration')
    restored=rollback(first['rollback_receipt'],ROOT)
    for item in frozen['global_files'].values():
        if digest(Path(item['path']))!=item['sha256']:raise ValueError('Legacy entry was not restored byte-for-byte')
    config=tomllib.loads(_paths()['config'].read_text(encoding='utf-8-sig'))
    legacy=[]
    for name,operation in [('reverse-fusion-rea','binary_session'),('reverse-fusion-craft','core_session_show')]:
        entry=config['mcp_servers'][name]
        env=dict(os.environ);env.update(entry.get('env',{}))
        with StdioMcp([entry['command'],*entry['args']],cwd=Path(entry['cwd']),env=env,timeout=60) as client:
            identity=client.initialize();tools=catalog(client)
            response=client.request('tools/call',{'name':operation,'arguments':{}})
            if response.get('isError'):raise ValueError('Restored legacy connection failed: '+name)
        if client.cleanup.get('status')!='verified':raise ValueError('Legacy restored process cleanup incomplete')
        legacy.append({'name':name,'identity':identity['serverInfo'],'tools':len(tools),
            'actual_call':operation,'actual_result':'returned without isError','cleanup':client.cleanup})
    print('Old entry connected after restoration; selecting enhanced entry again',flush=True)
    final=install(ROOT,replace_from=old)
    if outside_hashes()!=before_outside:raise ValueError('Unrelated bytes changed after final selection')
    old_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=old,text=True).strip()
    old_status=subprocess.check_output(['git','status','--porcelain'],cwd=old,text=True)
    if old_head!=frozen['frozen_commit'] or old_status:raise ValueError('Original source changed')
    report={'status':'pass','first_selection':compact(first['mcp_check']),
        'rollback':restored,'old_entries_exactly_restored':True,'legacy_actual_connections':legacy,
        'final_selection':compact(final['mcp_check']),'active_rollback_receipt':final['rollback_receipt'],
        'unrelated_bytes_sha256_before_and_after':before_outside,
        'old_head':old_head,'old_git_status':old_status,'old_source_changed':False,
        'desktop_hot_reload':'not-asserted; current chat may keep prior connections; new/reconnected clients read the registered entry',
        'scope':'Actual owned local Codex entry migration, original connection restoration and final new command connection; no target actions'}
    write(ROOT/'evidence/next/s6/local-migration.json',report)
    print(json.dumps({'status':'pass','old_restore_connected':True,'new_tools':final['mcp_check']['tools'],
        'rollback_receipt':final['rollback_receipt']}))


if __name__=='__main__':main()
