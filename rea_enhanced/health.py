"""Actual core identity and selected provider checks, separate from target acceptance."""
from pathlib import Path
import json
import subprocess
from .storage import read,digest
from .providers import providers,environment
from reverse_fusion.runtime import node_runtime

ROOT=Path(__file__).resolve().parents[1]


def inspect(root=ROOT):
    root=root.resolve();manifest=read(root/'vendor/rea/manifest.json');node,source=node_runtime(root)
    failures=[];version=None
    if not node:failures.append('Selected Node runtime missing')
    else:
        try:
            run=subprocess.run([node,'--version'],capture_output=True,text=True,timeout=5)
            version=run.stdout.strip()
            v=tuple(int(s) for s in version.lstrip('v').split('.'))
            if run.returncode or not ((v[0]==22 and v>=(22,23,4)) or (v[0]==24 and v>=(24,22,1)) or v>=(26,12,1)):
                failures.append('Node version does not satisfy the pinned REA engine')
        except (ValueError,OSError,subprocess.TimeoutExpired):failures.append('Node version probe failed')
    methods={}
    for name,expected in manifest['method_files_sha256'].items():
        p=root/'vendor/rea'/name
        methods[name]=p.is_file() and digest(p)==expected
    if not all(methods.values()):failures.append('Fixed official skill/method identity missing or changed')
    entry=root/'vendor/rea/package/scripts/rea.mjs'
    if not entry.is_file():failures.append('REA entry missing')
    selected=providers(root)
    binding=root/'vendor/rea/node_modules/frida/build/frida_binding.node'
    pin=read(root/'components/rea-enhanced/provider-bindings.json')
    frida={'status':'unavailable','scope':'Node binding identity only; actual enumeration is a separate live operation'}
    if binding.is_file():
        frida['status']='installed' if digest(binding)==pin['binding_sha256'] else 'changed'
    return {'status':'installed' if not failures else 'incomplete','failures':failures,
        'core':{'package':manifest['package'],'version':manifest['version'],'node':node,'node_version':version,
            'runtime_source':source,'original_methods':methods},'providers':selected,'frida':frida,
        'craft_required':False,'spec_required':False,'target_acceptance':'not-assessed'}
