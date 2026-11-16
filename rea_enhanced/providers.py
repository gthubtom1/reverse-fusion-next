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
        selected={};sources={}
        for key,value in previous['paths'].items():
            if key not in PATH_KEYS: raise ValueError('Unsupported saved provider key')
            try: selected[key]=str(_existing(key,value));sources[key]='saved-tool-path'
            except (ValueError,OSError): pass
        for key,value in _repository_tools(root).items(): selected[key]=value;sources[key]='verified-repository-provider'
        for key in PATH_KEYS:
            if os.environ.get(key):selected[key]=str(_existing(key,os.environ[key]));sources[key]='deployment-environment'
        for key,value in (overrides or {}).items():
            if key not in PATH_KEYS:raise ValueError('Unsupported REA provider key')
            selected[key]=str(_existing(key,value));sources[key]='explicit-tool-path'
        commands={'REA_ADB_PATH':'adb','REA_APKTOOL_COMMAND':'apktool','REA_ILSPY_CMD_PATH':'ilspycmd',
            'REA_KUNA_COMMAND':'kuna','REA_GDB_COMMAND':'gdb','REA_OBJDUMP_COMMAND':'objdump',
            'REA_TSHARK_COMMAND':'tshark','REA_MITMDUMP_COMMAND':'mitmdump',
            'REA_RIZIN_COMMAND':'rizin','REA_CAPINFOS_COMMAND':'capinfos'}
        for key,command in commands.items():
            value=shutil.which(command)
            if key not in selected and value:selected[key]=str(_existing(key,value));sources[key]='deployment-path'
        java=shutil.which('java')
        if 'JAVA_HOME' not in selected and java:
            selected['JAVA_HOME']=str(_existing('JAVA_HOME',str(Path(java).resolve().parent.parent)));sources['JAVA_HOME']='deployment-path'
        if 'REA_BROWSER_EXECUTABLE' not in selected:
            for base in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
                for suffix in ('Google/Chrome/Application/chrome.exe','Microsoft/Edge/Application/msedge.exe'):
                    value=Path(os.environ[base])/suffix if os.environ.get(base) else None
                    if value and value.is_file():selected['REA_BROWSER_EXECUTABLE']=str(value);sources['REA_BROWSER_EXECUTABLE']='installed-browser';break
                if 'REA_BROWSER_EXECUTABLE' in selected:break
        result={'schema_version':2,'repository_root':str(root),
            'paths':selected,'sources':sources,
            'scope':'Configured paths only; actual selected operations establish health.'}
        write(p,result)
    else:
        result=read(p) if p.exists() else {'schema_version':2,'repository_root':str(root),'paths':{},'sources':{}}
    if result['repository_root']!=str(root) or set(result['paths'])-set(PATH_KEYS):
        raise ValueError('Provider paths are not bound to this checkout')
    missing={}
    for key,path in result['paths'].items():
        try:_existing(key,path)
        except (ValueError,OSError) as exc:missing[key]=str(exc)
    return {**result,'unavailable':missing,'status':'configured' if result['paths'] and not missing else 'incomplete'}


def environment(root: Path):
    env={k:v for k,v in os.environ.items() if k not in PATH_KEYS and not k.startswith('REVERSE_FUSION_CRAFT_TOOL_')}
    selected=providers(root)
    if selected['unavailable']:raise ValueError('Configured provider paths changed; refresh and recheck')
    env.update(selected['paths'])
    env.update(REA_MCP_INPUT_SCHEMA_PROFILE='compact',REA_MCP_OUTPUT_SCHEMA_PROFILE='compact')
    return env
