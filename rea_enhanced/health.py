"""Actual core identity and selected provider checks, separate from target acceptance."""
from pathlib import Path
import json
import subprocess
import hashlib
import base64
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
    package_check={'status':'not-verified'}
    if manifest.get('integrity'):
        archive=root/'state/downloads/rea.tgz'
        try:
            algorithm,expected=manifest['integrity'].split('-',1)
            h=hashlib.new(algorithm)
            with archive.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
            if h.digest()!=base64.b64decode(expected):raise ValueError('Pinned REA archive identity changed')
            from .bootstrap import verify_rea_archive
            changed=verify_rea_archive(root,archive)
            package_check={'status':'verified' if not changed else 'changed','changed':changed[:20]}
            if changed:failures.append('Original REA executable package missing or changed')
        except (OSError,ValueError) as exc:
            failures.append('REA archive/package verification unavailable: '+str(exc))
    selected=providers(root)
    binding=root/'vendor/rea/node_modules/frida/build/frida_binding.node'
    pin=read(root/'components/rea-enhanced/provider-bindings.json')
    frida={'status':'unavailable','scope':'Node binding identity only; actual enumeration is a separate live operation'}
    if binding.is_file():
        frida['status']='installed' if digest(binding)==pin['binding_sha256'] else 'changed'
    if frida['status']!='installed':failures.append('Required separate Node Frida binding missing or changed')
    return {'status':'installed' if not failures else 'incomplete','failures':failures,
        'core':{'package':manifest['package'],'version':manifest['version'],'node':node,'node_version':version,
            'runtime_source':source,'original_methods':methods,'package_integrity':package_check},'providers':selected,'frida':frida,
        'craft_required':False,'spec_required':False,'target_acceptance':'not-assessed'}
