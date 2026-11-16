"""Checksum-bound, checkout-local Windows core bootstrap. No host writes."""
import base64
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from .storage import digest, read, write


def acquire(url, destination, algorithm='sha256', expected=None):
    if not url.startswith('https://'):
        raise ValueError('Pinned assets require HTTPS')
    destination.parent.mkdir(parents=True, exist_ok=True)
    def valid(path):
        h = hashlib.new(algorithm)
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
        return h.hexdigest() == expected
    if destination.is_file() and valid(destination): return destination
    temporary = destination.with_suffix(destination.suffix + '.partial')
    try:
        with urllib.request.urlopen(url, timeout=60) as source, temporary.open('wb') as output:
            shutil.copyfileobj(source, output)
        if not valid(temporary): raise ValueError('Pinned asset checksum mismatch: ' + destination.name)
        os.replace(temporary, destination)
    finally: temporary.unlink(missing_ok=True)
    return destination


def extract(archive, destination):
    """Reject links, special files, ambiguous names and escaping paths before writes."""
    destination = destination.resolve()
    def target(name):
        if '\\' in name or ':' in name or name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Unsafe archive member')
        path = (destination / name).resolve()
        if not path.is_relative_to(destination): raise ValueError('Archive leaves destination')
        return path
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                target(entry.filename)
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Archive links are not accepted')
            for entry in source.infolist():
                path = target(entry.filename)
                if entry.is_dir(): path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(entry) as incoming, path.open('wb') as output: shutil.copyfileobj(incoming, output)
    else:
        with tarfile.open(archive) as source:
            entries = source.getmembers()
            for entry in entries:
                target(entry.name)
                if not entry.isfile() and not entry.isdir(): raise ValueError('Archive special/link member rejected')
            for entry in entries:
                path = target(entry.name)
                if entry.isdir(): path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with source.extractfile(entry) as incoming, path.open('wb') as output: shutil.copyfileobj(incoming, output)


def bootstrap(root):
    root = root.resolve()
    if platform.system() != 'Windows' or platform.machine().lower() not in {'amd64','x86_64'}:
        raise ValueError('This pinned bootstrap is qualified for Windows x64; other platforms need explicit asset adaptation')
    cache = root / 'state/downloads'
    node_pin = read(root/'vendor/node/manifest.json')
    node_archive = acquire(node_pin['url'], cache/'node.zip', expected=node_pin['sha256'])
    node = root/'vendor/node'/node_pin['entry']
    with zipfile.ZipFile(node_archive) as archive:
        node_expected=hashlib.sha256(archive.read(node_pin['entry'])).hexdigest()
    if not node.is_file(): extract(node_archive, root/'vendor/node')
    if digest(node)!=node_expected:raise ValueError('Managed Node differs from the verified archive')
    # Node's exact extracted identity is recorded; archive always authenticates the source.
    rea_pin = read(root/'vendor/rea/manifest.json')
    algorithm, value = rea_pin['integrity'].split('-',1)
    rea_archive = acquire(rea_pin['source'], cache/'rea.tgz', algorithm, base64.b64decode(value).hex())
    package = root/'vendor/rea/package'
    with tarfile.open(rea_archive) as archive:
        entry_expected=hashlib.sha256(archive.extractfile('package/scripts/rea.mjs').read()).hexdigest()
    if not (package/'scripts/rea.mjs').is_file(): extract(rea_archive, root/'vendor/rea')
    if digest(package/'scripts/rea.mjs')!=entry_expected:raise ValueError('REA entry differs from the verified archive')
    for name, expected in rea_pin['method_files_sha256'].items():
        if digest(root/'vendor/rea'/name) != expected: raise ValueError('Official REA method changed: '+name)
    overlay = root/'vendor/rea'
    for original, name in [('provider-package.json','package.json'),('provider-package-lock.json','package-lock.json')]:
        shutil.copyfile(root/'components/rea-enhanced'/original, overlay/name)
    pin = read(root/'components/rea-enhanced/provider-bindings.json')
    binding = overlay/'node_modules/frida/build/frida_binding.node'
    if not binding.is_file() or digest(binding) != pin['binding_sha256']:
        npm = node.parent/'node_modules/npm/bin/npm-cli.js'
        env = dict(os.environ); env['PATH'] = str(node.parent)+os.pathsep+env.get('PATH','')
        run = subprocess.run([str(node),str(npm),'ci','--ignore-scripts','--no-audit','--no-fund','--prefix',str(overlay)],
                             cwd=root, env=env, capture_output=True, timeout=240)
        (root/'state/npm-provider-install.log').write_bytes(run.stdout+run.stderr)
        if run.returncode: raise ValueError('Locked Node provider acquisition failed; see state/npm-provider-install.log')
        archive = acquire(pin['url'], cache/'frida.tar.gz', expected=pin['sha256'])
        extract(archive, overlay/'node_modules/frida')
    if digest(binding) != pin['binding_sha256']: raise ValueError('Frida binding identity mismatch')
    write(root/'state/rea-runtime.json',{'schema_version':1,'repository_root':str(root),'node':str(node),
        'node_sha256':digest(node),'official_entry_sha256':digest(package/'scripts/rea.mjs')})
    # Portable domain providers, acquired independently of any prior checkout.
    wabt = read(root/'vendor/wabt/1.0.42/manifest.json')
    directory = root/'vendor/wabt/1.0.42/windows-x64'
    if not all((directory/'wabt-1.0.42/bin'/name).is_file() for name in wabt['required_tools']):
        extract(acquire(wabt['source'],cache/'wabt.tar.gz',expected=wabt['archive_sha256']),directory)
    for name, expected in wabt['bin_sha256'].items():
        if digest(directory/'wabt-1.0.42/bin'/name) != expected: raise ValueError('WABT identity mismatch')
    jadx = read(root/'vendor/jadx-headless-mcp/0.7.1/manifest.json')
    acquire(jadx['source'],root/'vendor/jadx-headless-mcp/0.7.1'/jadx['artifact'],expected=jadx['sha256'])
    from .providers import providers
    from .health import inspect
    providers(root,refresh=True)
    report=inspect(root)
    if report['status']!='installed' or report['frida']['status']!='installed':
        raise ValueError('Core health failed: '+str(report['failures']))
    write(root/'state/bootstrap-next.json',report)
    return report
