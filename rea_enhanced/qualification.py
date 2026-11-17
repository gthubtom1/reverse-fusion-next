"""Source-bound engineering qualification; never claims arbitrary target success."""
from pathlib import Path
import tomllib
from . import __version__
from .storage import read,digest

ROOT=Path(__file__).resolve().parents[1]
HELPERS=('case_bridge','contracts','runtime','owned_process','global_adapter','mcp_adapter',
         'file_updates','mcp_process','mcp_probe','provider_runtime','__init__','__main__','cli')


def source_identity(root=ROOT):
    names=[p.relative_to(root).as_posix() for p in (root/'rea_enhanced').glob('*.py')]
    names += ['reverse_fusion/'+name+'.py' for name in HELPERS]
    names += ['components/reverse-core/router.py','components/reverse-core/routing.json','components/reverse-core/runtime.json',
        'components/reverse-core/preservation.json','components/rea-enhanced/web-replay.mjs',
        'components/rea-enhanced/provider-package.json','components/rea-enhanced/provider-package-lock.json',
        'components/rea-enhanced/provider-bindings.json','vendor/rea/manifest.json','vendor/node/manifest.json',
        'scripts/install.ps1','pyproject.toml','VERSION']
    names += [p.relative_to(root).as_posix() for p in (root/'tests_next').glob('*.py')]
    names += ['AGENTS.md','RULES.md','README.md','docs/ACTIVE-DOCUMENTS.json',
              'docs/NEXT/REQUIREMENTS.md','scripts/next-clean-install.py',
              'scripts/next-remote-install.py','scripts/next-qualify.py','scripts/next-cli.py']
    # Progress/receipts change after qualification; executable user contracts do not.
    names += [n for n in read(root/'docs/ACTIVE-DOCUMENTS.json')['active']
              if n!='docs/CURRENT-STATE.md']
    # Git checkouts and fresh exports may differ in CRLF spelling, not content.
    from hashlib import sha256
    return {name:sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in sorted(set(names))}


def release_check(root=ROOT,require_deployed=False):
    failures=[]
    try:
        record=read(root/'evidence/next/s6/engineering-tests.json')
        if record.get('status')!='pass' or record.get('source_identity')!=source_identity(root):
            failures.append('Engineering qualification is missing or stale for this source')
        pin=read(root/'components/reverse-core/preservation.json')
        from hashlib import sha256
        for name,entry in pin['files'].items():
            data=(root/name).read_bytes()
            if not name.endswith('.jar'):data=data.replace(b'\r\n',b'\n')
            if sha256(data).hexdigest()!=entry['sha256']:failures.append('Domain origin changed: '+name)
        for name,expected in record.get('evidence_sha256',{}).items():
            if digest(root/name)!=expected:failures.append('Qualified operation evidence changed: '+name)
        for name in ('s2/protocol-qualified.json','s2/native-restart-qualified.json',
                     'tiered-storage/live-proof.json',
                     'final-audit/native-provider.json',
                     *('final-audit/web-'+n+'.json' for n in ('equal','wrong-behavior','wrong-look','missing-observation','controls'))):
            key='evidence/next/'+name
            if key not in record.get('evidence_sha256',{}) or read(root/key).get('status')!='pass':
                failures.append('Required operation was not bound to qualification: '+name)
        clean=read(root/'evidence/next/final-audit/remote-install.json')
        if (clean.get('status')!='pass' or clean.get('source_identity')!=source_identity(root)
                or clean.get('repository')!='https://github.com/gthubtom1/reverse-fusion-next.git'
                or clean.get('source_method')!='git-clone-remote' or not clean.get('source_commit')):
            failures.append('Independent repository clone/install qualification is missing or stale')
        versions=[tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version'],
            read(root/'release/manifest.json')['version'],read(root/'components/official/manifest.json')['version'],
            read(root/'SOURCE-MANIFEST.json')['version'],read(root/'docs/ACTIVE-DOCUMENTS.json')['version'],
            (root/'VERSION').read_text(encoding='utf-8').strip()]
        if any(version!=__version__ for version in versions):failures.append('Current entry versions disagree')
        for name in read(root/'docs/ACTIVE-DOCUMENTS.json')['active']:
            if not (root/name).is_file():failures.append('Active documentation missing: '+name)
    except (ValueError,OSError,KeyError,TypeError) as exc:failures.append(str(exc))
    connection=None
    if require_deployed and not failures:
        from .deployment import probe
        try:connection=probe(root)
        except (ValueError,OSError,TimeoutError,EOFError) as exc:failures.append(str(exc))
    return {'status':'pass' if not failures else 'fail','version':__version__,'failures':failures,
        'connection':connection,'scope':'Source-bound Windows x64 Codex engineering and retained finite evidence',
        'whole_product_acceptance':'not-established; task-specific coverage remains required'}
