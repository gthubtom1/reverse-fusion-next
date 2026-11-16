"""REA-only provider selection; never discovers Craft or reads credentials."""
import os
from pathlib import Path
from reverse_fusion.provider_runtime import PATH_KEYS, discover_providers, _existing
from .storage import read, write


def providers(root: Path, refresh=False, overrides=None):
    root=root.resolve();p=root/'state/rea-providers.json'
    if refresh:
        found=discover_providers(root,persist=False,overrides=overrides)
        result={'schema_version':2,'repository_root':str(root),
            'paths':{k:v for k,v in found['paths'].items() if k in PATH_KEYS},
            'sources':{k:v for k,v in found['sources'].items() if k in PATH_KEYS},
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
