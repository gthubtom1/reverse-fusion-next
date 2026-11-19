"""Actual core identity and selected provider checks, separate from target acceptance."""
from pathlib import Path
import subprocess
import hashlib
import base64
import tarfile
import shutil
import zipfile
from .storage import read,digest
from .providers import providers
from reverse_fusion.runtime import node_runtime

ROOT=Path(__file__).resolve().parents[1]


def node_identity(root=ROOT, *, node=None, source=None, enforce_prepared=False):
    """Read-only startup guard; configured runtimes remain distinct from certification.

    No version subprocess is launched. A prepared checkout enforces its saved
    Node SHA even for environment/PATH selections. Certification additionally
    authenticates that SHA against the fixed ZIP; an absent cache does not by
    itself prevent ordinary execution of the still-matching prepared runtime.
    """
    root=root.resolve()
    if node is None:node,source=node_runtime(root)
    selected=Path(node) if node and Path(node).is_absolute() else Path(shutil.which(node) or '') if node else None
    configured=bool(selected and selected.is_file())
    report={'status':'configured' if configured else 'unavailable','configured':configured,
        'certified':False,'prepared':(root/'state/rea-runtime.json').exists(),
        'node':str(selected.resolve()) if configured else node,'runtime_source':source,
        'diagnostics':[]}
    selected_sha=None;receipt_sha=None;receipt_valid=False;contradicted=False;authenticated=False
    try:
        if configured:selected_sha=digest(selected)
        report['node_sha256']=selected_sha
        pin=read(root/'vendor/node/manifest.json')
        report['expected_version']=pin['version']
        if not report['prepared']:raise ValueError('Managed Node runtime receipt missing; configured only')
        receipt=read(root/'state/rea-runtime.json')
        managed=(root/'vendor/node'/pin['entry']).resolve()
        receipt_sha=receipt.get('node_sha256')
        if (receipt.get('schema_version')!=1 or not Path(receipt['repository_root']).is_absolute()
                or Path(receipt['repository_root']).resolve()!=root
                or not Path(receipt['node']).is_absolute() or Path(receipt['node']).resolve()!=managed
                or not managed.is_relative_to((root/'vendor/node').resolve())
                or not isinstance(receipt_sha,str) or len(receipt_sha)!=64
                or any(c not in '0123456789abcdef' for c in receipt_sha)):
            raise ValueError('Managed Node runtime receipt identity invalid')
        receipt_valid=True;report['expected_sha256']=receipt_sha
        if selected_sha!=receipt_sha:
            report['status']='changed'
            report['diagnostics'].append('Selected Node identity differs from the managed runtime receipt')
        archive=root/'state/downloads/node.zip'
        if digest(archive)!=pin['sha256']:raise ValueError('Fixed Node archive checksum mismatch')
        with zipfile.ZipFile(archive) as original:
            expected=hashlib.sha256(original.read(pin['entry'])).hexdigest()
        if expected!=receipt_sha:
            contradicted=True
            raise ValueError('Managed Node receipt SHA differs from the authenticated fixed archive')
        authenticated=True
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as exc:
        report['diagnostics'].append(str(exc))
    report['certified']=bool(authenticated and configured and selected_sha==receipt_sha)
    if report['certified']:report['status']='matched'
    report['execution_allowed']=bool(configured and (not report['prepared']
        or receipt_valid and not contradicted and selected_sha==receipt_sha))
    if enforce_prepared and report['prepared'] and not report['execution_allowed']:
        raise ValueError('Selected Node differs from prepared managed identity: '+'; '.join(report['diagnostics']))
    return report


def inspect(root=ROOT):
    root=root.resolve();manifest=read(root/'vendor/rea/manifest.json');node,source=node_runtime(root)
    runtime_pin=node_identity(root,node=node,source=source)
    failures=[];version=None
    if not node:failures.append('Selected Node runtime missing')
    elif not runtime_pin['execution_allowed']:
        failures.append('Prepared/unavailable Node identity check blocked the version probe')
    else:
        try:
            run=subprocess.run([runtime_pin['node'],'--version'],capture_output=True,text=True,timeout=5)
            version=run.stdout.strip()
            v=tuple(int(s) for s in version.lstrip('v').split('.'))
            if run.returncode or not ((v[0]==22 and v>=(22,23,4)) or (v[0]==24 and v>=(24,22,1)) or v>=(26,12,1)):
                failures.append('Node version does not satisfy the pinned REA engine')
        except (ValueError,OSError,subprocess.TimeoutExpired):failures.append('Node version probe failed')
    runtime_pin['selected_version']=version
    if runtime_pin.get('expected_version') is None:
        failures.append('Fixed Node runtime identity verification unavailable')
    elif version is not None and version!='v'+runtime_pin['expected_version']:
        runtime_pin['status']='mismatch';runtime_pin['certified']=False
        failures.append('Selected Node version differs from the fixed installation pin')
    if not runtime_pin['certified']:
        failures.append('Selected Node runtime identity is configured/unavailable, not certified against the fixed archive')
        failures.extend(runtime_pin['diagnostics'])
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
        except (OSError,ValueError,tarfile.TarError) as exc:
            failures.append('REA archive/package verification unavailable: '+str(exc))
    else:
        failures.append('Fixed REA archive integrity missing')
    core_failures=list(failures)
    selected=providers(root)
    binding=root/'vendor/rea/node_modules/frida/build/frida_binding.node'
    frida={'status':'unavailable','required_for':'full-windows-install',
        'scope':'Node binding identity only; actual enumeration is a separate live operation'}
    try:
        pin=read(root/'components/rea-enhanced/provider-bindings.json')
        if binding.is_file():
            frida['status']='installed' if digest(binding)==pin['binding_sha256'] else 'changed'
    except (OSError,ValueError,KeyError) as exc:
        frida['diagnostic']=str(exc)
    if frida['status']!='installed':failures.append('Required separate Node Frida binding missing or changed')
    return {'status':'installed' if not failures else 'incomplete','failures':failures,
        'installation_profile':'full-windows-install',
        'core':{'status':'installed' if not core_failures else 'incomplete','failures':core_failures,
            'package':manifest['package'],'version':manifest['version'],'node':node,'node_version':version,
            'runtime_pin':runtime_pin,
            'runtime_source':source,'original_methods':methods,'package_integrity':package_check},'providers':selected,'frida':frida,
        'craft_required':False,'spec_required':False,'target_acceptance':'not-assessed'}
