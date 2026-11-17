"""Finite stdio MCP protocol checks; a catalog does not certify every provider."""
from __future__ import annotations

import json
import os
from hashlib import sha256
import queue
import threading
import time
from pathlib import Path

from .mcp_process import McpProcess
from .provider_runtime import ALL_KEYS,provider_status,provider_identities


def runtime_fingerprint(root: Path) -> dict:
    from .craft_mcp import mcp_binary
    from .runtime import node_runtime
    node,_=node_runtime(root)
    paths=[Path(node),mcp_binary(root),root/'scripts/mcp-launch.py',root/'reverse_fusion/provider_runtime.py',
           root/'state/provider-runtime.json',root/'vendor/rea/package/scripts/rea.mjs']
    return {**{str(path):sha256(path.read_bytes()).hexdigest() for path in paths},
            'selected_provider_identities':provider_identities(root)}


def _check_configured_providers(root: Path, session: dict):
    configured=provider_status(root)
    result=session.get('structuredContent',{}).get('result',{})
    if configured['unavailable']: raise ValueError('Previously selected providers are unavailable; refresh/review provider paths')
    if 'GHIDRA_INSTALL_DIR' in configured['paths']:
        ghidra=next((item for item in result.get('analysis_provider_candidates',[]) if item['provider']['id']=='ghidra'),None)
        if not ghidra or ghidra['availability']['status']!='available':
            raise ValueError('Configured Ghidra is not usable by the registered server: '+str(ghidra))
    for key,operation in [('REA_WABT_BIN_DIRECTORY','inspect_wasm_artifact'),('REA_JADX_MCP_JAR','inspect_android_package')]:
        if key in configured['paths']:
            group=next((item for item in result.get('tool_availability',{}).get('groups',[]) if operation in item.get('names',[])),None)
            if not group or not group.get('available'): raise ValueError(f'Configured {key} is not usable by the registered server: {group}')


class StdioMcp:
    def __init__(self, argv: list[str], *, cwd: Path, env=None, timeout=30):
        self.owner = McpProcess(argv, cwd=cwd, env=env)
        self.process = self.owner.process
        self.cleanup = None
        self.timeout = timeout
        self.messages = queue.Queue()
        self.errors = bytearray()
        self.sequence = 0
        def read_stdout():
            try:
                for line in self.process.stdout:
                    try:
                        self.messages.put(json.loads(line))
                    except ValueError:
                        self.messages.put(ValueError('MCP stdout contained a non-JSON message'))
            finally:
                self.messages.put(EOFError('MCP stdout closed'))
        def read_stderr():
            for part in iter(lambda: self.process.stderr.read(4096), b''):
                if len(self.errors) < 65536:
                    self.errors.extend(part[:65536-len(self.errors)])
        self.threads = [threading.Thread(target=read_stdout, daemon=True),
                        threading.Thread(target=read_stderr, daemon=True)]
        for thread in self.threads: thread.start()

    def send(self, message):
        self.process.stdin.write((json.dumps(message, ensure_ascii=True) + '\n').encode('ascii'))
        self.process.stdin.flush()

    def request(self, method, params=None, *, cancel_event=None):
        self.sequence += 1
        identity = self.sequence
        self.send({'jsonrpc': '2.0', 'id': identity, 'method': method, 'params': params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise ValueError('MCP operation cancelled')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'MCP deadline: {method}')
            try: message = self.messages.get(timeout=min(.1, remaining) if cancel_event is not None else remaining)
            except queue.Empty:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'MCP deadline: {method}') from None
                continue
            if isinstance(message, Exception): raise message
            if message.get('id') == identity:
                if 'error' in message: raise ValueError(f'MCP {method}: {message["error"]}')
                return message['result']
            if time.monotonic() >= deadline: raise TimeoutError(f'MCP deadline: {method}')

    def initialize(self):
        result = self.request('initialize', {'protocolVersion': '2025-06-18',
            'capabilities': {}, 'clientInfo': {'name': 'reverse-fusion-deployment-check', 'version': '1'}})
        self.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        return result

    def close(self):
        try:
            self.cleanup = self.owner.close()
        finally:
            for thread in self.threads: thread.join(timeout=1)
            self.process.stdout.close()
            self.process.stderr.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


def catalog(client: StdioMcp, method='tools/list', key='tools'):
    items, cursor, seen = [], None, set()
    for _ in range(100):
        response = client.request(method, {'cursor': cursor} if cursor else {})
        items.extend(response.get(key, []))
        cursor = response.get('nextCursor')
        if not cursor: return items
        if cursor in seen: raise ValueError('MCP repeated pagination cursor')
        seen.add(cursor)
    raise ValueError('MCP catalog exceeded bounded pagination')


def probe_registered(root: Path) -> dict:
    """Read the actual registered commands; no target or model is started."""
    import tomllib
    from .mcp_adapter import inspect_mcp, SERVERS
    from .file_updates import atomic_write
    registration = inspect_mcp(root)
    if not registration.get('enabled'):
        raise ValueError('Current checkout MCP registrations are missing or stale')
    config = tomllib.loads(Path(registration['config']).read_text(encoding='utf-8-sig'))
    results = []
    for server in SERVERS:
        entry = config['mcp_servers'][server]
        started = time.monotonic()
        # Deliberately remove terminal-only provider variables: app startup must
        # recover saved paths, rather than borrowing this diagnostic shell.
        environment={key:value for key,value in os.environ.items() if key not in ALL_KEYS}
        environment.update(entry.get('env',{}))
        with StdioMcp([entry['command'], *entry.get('args', [])], cwd=Path(entry['cwd']),
                      env=environment, timeout=60) as client:
            identity = client.initialize()
            tools = catalog(client)
            operation = 'binary_session' if server.endswith('-rea') else 'core_session_show'
            response = client.request('tools/call', {'name': operation, 'arguments': {}})
            if response.get('isError'):
                raise ValueError(f'{server}: actual status tool failed')
            if server.endswith('-rea'): _check_configured_providers(root,response)
            expected = 'rea' if server.endswith('-rea') else 'craft-anything'
            if identity['serverInfo']['name'] != expected or not any(t['name'] == operation for t in tools):
                raise ValueError(f'{server}: unexpected identity/catalog')
            prompts = catalog(client, 'prompts/list', 'prompts')
        results.append({'server': server, 'registration': entry, 'server_info': identity['serverInfo'],
            'binary_sha256': sha256(Path(entry['command']).read_bytes()).hexdigest(),
            'entry_sha256': sha256((root / 'vendor/rea/package/scripts/rea.mjs').read_bytes()).hexdigest()
                              if server.endswith('-rea') else None,
            'tools': len(tools), 'tool_names': [tool['name'] for tool in tools], 'prompts': len(prompts),
            'called': operation, 'result': response, 'cleanup': client.cleanup,
            'elapsed_seconds': time.monotonic()-started})
    result = {'schema_version': 1, 'status': 'pass', 'repository': str(root.resolve()), 'servers': results,
              'runtime_inputs':runtime_fingerprint(root), 'provider_paths':provider_status(root),
              'scope': 'exact registered stdio initialize/catalog/target-free call; not desktop hot-load, every provider or target acceptance'}
    atomic_write(root / 'state/mcp-runtime.json', (json.dumps(result, ensure_ascii=True, indent=2)+'\n').encode('ascii'))
    return result


def connection_status(root: Path) -> dict:
    """Reject old command/binary observations after changing the installation."""
    try:
        import tomllib
        from .mcp_adapter import inspect_mcp, SERVERS
        registration = inspect_mcp(root)
        if not registration.get('enabled'): raise ValueError('MCP registration missing or stale')
        entries = tomllib.loads(Path(registration['config']).read_text(encoding='utf-8-sig'))['mcp_servers']
        saved = json.loads((root / 'state/mcp-runtime.json').read_text(encoding='utf-8'))
        if (saved['status'] != 'pass' or Path(saved['repository']).resolve() != root.resolve()
                or {item['server'] for item in saved['servers']} != set(SERVERS)):
            raise ValueError('MCP protocol verification missing')
        for item in saved['servers']:
            entry = entries[item['server']]
            if item.get('cleanup', {}).get('status') != ('verified' if os.name == 'nt' else 'observed'):
                raise ValueError('MCP owned process cleanup observation is missing or incomplete')
            if item['registration'] != entry or sha256(Path(entry['command']).read_bytes()).hexdigest() != item['binary_sha256']:
                raise ValueError('MCP launch configuration or binary changed')
            if item['server'].endswith('-rea') and item['entry_sha256'] != sha256((root/'vendor/rea/package/scripts/rea.mjs').read_bytes()).hexdigest():
                raise ValueError('Official REA entry changed')
        if saved.get('runtime_inputs')!=runtime_fingerprint(root):
            raise ValueError('MCP provider paths, launcher or actual runtime identities changed; rerun mcp-check')
        if provider_status(root)['unavailable']:
            raise ValueError('Selected provider files are unavailable; prior qualification is stale')
        return {'status': 'pass', 'scope': saved['scope'], 'servers': [
            {key: item[key] for key in ('server', 'server_info', 'tools', 'prompts', 'called')} for item in saved['servers']]}
    except (OSError, KeyError, ValueError, TypeError) as exc:
        return {'status': 'fail', 'reason': str(exc)}
