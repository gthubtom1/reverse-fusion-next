"""Checksum-bound, checkout-local Windows core bootstrap. No host writes."""
import base64
import hashlib
import http.client
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
import ssl
import time
import urllib.error
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from .storage import digest, read, write


def verify_rea_archive(root, archive):
    """Authenticate every original package file, including bundled execution modules."""
    failures=[]
    with tarfile.open(archive) as source:
        for entry in source:
            if not entry.isfile():continue
            path=(root/'vendor/rea'/entry.name).resolve()
            if not path.is_relative_to((root/'vendor/rea/package').resolve()):
                raise ValueError('REA package member outside package')
            expected=hashlib.sha256(source.extractfile(entry).read()).hexdigest()
            if not path.is_file() or digest(path)!=expected:failures.append(entry.name)
    return failures


def prepare_rea_package(root, archive):
    """Publish a complete verified package; interruptions leave the live path absent."""
    overlay = root/'vendor/rea'
    package = overlay/'package'
    if package.exists():
        changed = verify_rea_archive(root, archive)
        if changed:
            raise ValueError('Original REA package differs from verified archive; existing damage/partial extraction '
                             'has no atomic-preparation ownership proof and is preserved; restore managed package before retry: '
                             + ', '.join(changed[:8]))
        return
    overlay.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.rea-prepare-', dir=overlay) as temporary:
        staging = Path(temporary)
        extract(archive, staging/'vendor/rea')
        changed = verify_rea_archive(staging, archive)
        if changed:
            raise ValueError('Prepared REA package differs from verified archive: '+', '.join(changed[:8]))
        os.replace(staging/'vendor/rea/package', package)


def download_asset(url, temporary):
    """Use bounded ranges when advertised; every archive still needs its full pin."""
    chunk_size = 1024 * 1024
    headers = {'User-Agent': 'Reverse-Fusion-Pinned-Asset/1', 'Accept-Encoding': 'identity',
               'Range': 'bytes=0-' + str(chunk_size - 1)}
    def extent(source):
        value = source.headers.get('Content-Range', '')
        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', value)
        if not match:
            raise ValueError('Invalid pinned asset byte range')
        return tuple(map(int, match.groups()))
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as source:
        if getattr(source, 'status', 200) != 206:
            with temporary.open('wb') as output:
                shutil.copyfileobj(source, output)
            length = getattr(source, 'headers', {}).get('Content-Length')
            if length is not None and temporary.stat().st_size != int(length):
                raise ConnectionError('Incomplete pinned asset transfer')
            return
        start, end, total = extent(source)
        if start != 0 or end != min(total, chunk_size) - 1 or not 0 < total <= 512 * 1024 * 1024:
            raise ValueError('Unexpected pinned asset range or size')
        etag = source.headers.get('ETag')
        first = source.read(chunk_size + 1)
        if len(first) != end + 1:
            raise ConnectionError('Incomplete initial pinned asset range')
    temporary.write_bytes(first)
    def part(offset):
        stop = min(offset + chunk_size, total) - 1
        selected = {**headers, 'Range': f'bytes={offset}-{stop}'}
        if etag:
            selected['If-Range'] = etag
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=selected), timeout=60) as source:
                    if getattr(source, 'status', 200) != 206 or extent(source) != (offset, stop, total):
                        raise ValueError('Pinned asset range changed during transfer')
                    if etag and source.headers.get('ETag') != etag:
                        raise ValueError('Pinned asset identity changed during transfer')
                    data = source.read(chunk_size + 1)
                    if len(data) != stop - offset + 1:
                        raise ConnectionError('Incomplete pinned asset range')
                    return offset, data
            except (urllib.error.URLError, ssl.SSLError, TimeoutError, ConnectionError,
                    http.client.IncompleteRead) as exc:
                if isinstance(exc, urllib.error.HTTPError) and exc.code not in {408,429,500,502,503,504}:
                    raise
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
    pool = ThreadPoolExecutor(max_workers=4)
    try:
        pending = [pool.submit(part, offset) for offset in range(end + 1, total, chunk_size)]
        with temporary.open('r+b') as output:
            for future in as_completed(pending):
                offset, data = future.result()
                output.seek(offset)
                output.write(data)
    finally:
        # A hard identity error must not launch every still-queued range.
        pool.shutdown(wait=True, cancel_futures=True)


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
    for attempt in range(3):
        try:
            download_asset(url, temporary)
            if not valid(temporary): raise ValueError('Pinned asset checksum mismatch: ' + destination.name)
            os.replace(temporary, destination)
            break
        except (urllib.error.URLError,ssl.SSLError,TimeoutError,ConnectionError,http.client.IncompleteRead) as exc:
            if isinstance(exc,urllib.error.HTTPError) and exc.code not in {408,429,500,502,503,504}:raise
            if attempt==2:raise
            time.sleep(attempt+1)
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
    prepare_rea_package(root, rea_archive)
    for name, expected in rea_pin['method_files_sha256'].items():
        if digest(root/'vendor/rea'/name) != expected: raise ValueError('Official REA method changed: '+name)
    overlay = root/'vendor/rea'
    for original, name in [('provider-package.json','package.json'),('provider-package-lock.json','package-lock.json')]:
        shutil.copyfile(root/'components/rea-enhanced'/original, overlay/name)
    pin = read(root/'components/rea-enhanced/provider-bindings.json')
    binding = overlay/'node_modules/frida/build/frida_binding.node'
    overlay_valid=False
    if binding.is_file() and digest(binding)==pin['binding_sha256']:
        probe=subprocess.run([str(node),'--input-type=module','-e','await import("frida"); console.log("loaded")'],
            cwd=overlay,capture_output=True,timeout=15)
        overlay_valid=probe.returncode==0
    if not overlay_valid:
        npm = node.parent/'node_modules/npm/bin/npm-cli.js'
        env = dict(os.environ); env['PATH'] = str(node.parent)+os.pathsep+env.get('PATH','')
        from reverse_fusion.owned_process import run_owned
        run = run_owned([str(node),str(npm),'ci','--ignore-scripts','--no-audit','--no-fund','--prefix',str(overlay)],
            cwd=root,env=env,stdin=b'',timeout=240,memory_mb=2048,max_output_bytes=8*1024*1024)
        (root/'state/npm-provider-install.log').write_bytes(run['stdout']+run['stderr'])
        if run['status']!='observed' or run['exit_code']: raise ValueError('Locked Node provider acquisition failed; see state/npm-provider-install.log')
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
