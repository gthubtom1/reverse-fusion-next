"""REA-only provider selection; never discovers Craft or reads credentials."""
import os
import shutil
from pathlib import Path
from reverse_fusion.provider_runtime import PATH_KEYS, _existing, _repository_tools
from .storage import read, write


def providers(root: Path, refresh=False, overrides=None):
    root=root.resolve();p=root/'state/rea-providers.json'
    if refresh:
        previous=read(p) if p.exists() else {'repository_root':str(root),'paths':{},'sources':{}}
        if previous.get('repository_root')!=str(root): raise ValueError('Provider receipt belongs to another checkout')
        selected={};sources={};removed={}
        repository=_repository_tools(root)
        def select(key,value,source,strict=False):
            try:
                path=_existing(key,value)
                if (key in {'REA_WABT_BIN_DIRECTORY','REA_JADX_MCP_JAR'} and path.is_relative_to(root)
                        and repository.get(key)!=str(path)):
                    raise ValueError('Managed provider integrity changed')
                selected[key]=str(path);sources[key]=source
            except (ValueError,OSError) as exc:
                if strict:raise
                removed[key]=str(exc)
        for key,value in previous['paths'].items():
            if key not in PATH_KEYS: raise ValueError('Unsupported saved provider key')
            select(key,value,'saved-tool-path')
        for key,value in repository.items(): selected[key]=value;sources[key]='verified-repository-provider'
        for key in PATH_KEYS:
            if os.environ.get(key):select(key,os.environ[key],'deployment-environment')
        for key,value in (overrides or {}).items():
            if key not in PATH_KEYS:raise ValueError('Unsupported REA provider key')
            select(key,value,'explicit-tool-path',strict=True)
        commands={'REA_ADB_PATH':'adb','REA_APKTOOL_COMMAND':'apktool','REA_ILSPY_CMD_PATH':'ilspycmd',
            'REA_KUNA_COMMAND':'kuna','REA_GDB_COMMAND':'gdb','REA_OBJDUMP_COMMAND':'objdump',
            'REA_TSHARK_COMMAND':'tshark','REA_MITMDUMP_COMMAND':'mitmdump',
            'REA_RIZIN_COMMAND':'rizin','REA_CAPINFOS_COMMAND':'capinfos'}
        for key,command in commands.items():
            value=shutil.which(command)
            if key not in selected and value:select(key,value,'deployment-path')
        java=shutil.which('java')
        if 'JAVA_HOME' not in selected and java:
            select('JAVA_HOME',str(Path(java).resolve().parent.parent),'deployment-path')
        if 'REA_BROWSER_EXECUTABLE' not in selected:
            for base in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
                for suffix in ('Google/Chrome/Application/chrome.exe','Microsoft/Edge/Application/msedge.exe'):
                    value=Path(os.environ[base])/suffix if os.environ.get(base) else None
                    if value and value.is_file():selected['REA_BROWSER_EXECUTABLE']=str(value);sources['REA_BROWSER_EXECUTABLE']='installed-browser';break
                if 'REA_BROWSER_EXECUTABLE' in selected:break
        result={'schema_version':2,'repository_root':str(root),
            'paths':selected,'sources':sources,'removed_unavailable_paths':removed,
            'scope':'Configured paths only; actual selected operations establish health.'}
        write(p,result)
        write_index(root,result)
    else:
        result=read(p) if p.exists() else {'schema_version':2,'repository_root':str(root),'paths':{},'sources':{}}
    if result['repository_root']!=str(root) or set(result['paths'])-set(PATH_KEYS):
        raise ValueError('Provider paths are not bound to this checkout')
    missing={};repository=_repository_tools(root)
    for key,path in result['paths'].items():
        try:
            resolved=_existing(key,path)
            if (key in {'REA_WABT_BIN_DIRECTORY','REA_JADX_MCP_JAR'} and resolved.is_relative_to(root)
                    and repository.get(key)!=str(resolved)):
                raise ValueError('Managed provider integrity changed')
        except (ValueError,OSError) as exc:missing[key]=str(exc)
    return {**result,'unavailable':missing,'status':'configured' if result['paths'] and not missing else 'incomplete'}


def write_index(root,selected):
    """Meet preserved domain readers with current paths, never historical readiness."""
    import sys
    from reverse_fusion.runtime import node_runtime
    node,_=node_runtime(root)
    rows={'python':str(Path(sys.executable).resolve()),'rea':str(root/'vendor/rea/package/scripts/rea.mjs')}
    if node:rows['node']=node
    rows.update(selected['paths'])
    payload={'schema_version':2,'repository_root':str(root),'paths':rows,
        'qualification':'Configured/discovered paths only; operation health is established by actual provider calls',
        'refresh':'python -m rea_enhanced providers --refresh',
        'missing_tools':'Not listed means unselected or unavailable; never infer readiness from embedded historical versions'}
    write(root/'skills/tool-index.json',payload)
    lines=['# 当前工具路径索引','','来自增强REA的保存路径；不是工具操作通过证明。',
        '领域文档中的旧路径/版本仅方法例子，本索引与实际调用结果优先。',
        '未列工具按需发现；不能把JADX MCP JAR当成jadx CLI或把Python Frida当成Node绑定。','',
        '| 路径键 | 当前路径 | 状态 |','|---|---|---|']
    lines += ['| '+key+' | '+value.replace('|','\\|')+' | 路径已选择，操作需实测 |' for key,value in sorted(rows.items())]
    from reverse_fusion.file_updates import atomic_write
    atomic_write(root/'skills/tool-index.md',('\n'.join(lines)+'\n').encode('utf-8'))


def environment(root: Path):
    env={k:v for k,v in os.environ.items() if k not in PATH_KEYS and not k.startswith('REVERSE_FUSION_CRAFT_TOOL_')}
    selected=providers(root)
    # An unavailable optional provider must not prevent unrelated tools starting.
    # Keep its diagnostic in providers(); never pass a stale selected path onward.
    env.update({key: value for key, value in selected['paths'].items()
                if key not in selected['unavailable']})
    env.update(REA_MCP_INPUT_SCHEMA_PROFILE='compact',REA_MCP_OUTPUT_SCHEMA_PROFILE='compact')
    return env
