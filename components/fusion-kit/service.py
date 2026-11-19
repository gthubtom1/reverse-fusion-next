"""Local analysis, reusable evidence, and optional task memory over one MCP connection."""
import json
import os
from pathlib import Path
from runpy import run_path
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
field = run_path(str(ROOT / 'components/field-kit/service.py'))
review = field['review']
materials = field['materials']
from rea_enhanced.server import TOOLS as WORKFLOW_TOOLS, call_owned
from reverse_fusion.mcp_probe import StdioMcp, catalog


PROFILE = json.loads((HERE / 'profile.json').read_bytes())
# Deliberately list supported native operations; a new upstream tool does not
# silently add execution, browser/device control, or network automation.
NATIVE = frozenset('''
    open_binary close_binary inspect_artifact inspect_pe_resources
    inspect_native_exports inspect_elf_notes inspect_pe_imports inspect_macho
    inspect_pe_certificates inspect_sqlite_database inspect_managed_artifact
    inspect_managed_members inspect_apk_signature identify_flutter_build
    inspect_go_binary inspect_rust_binary inspect_wasm_artifact
    inspect_analysis_view compare_artifacts compare_bundles compare_managed_members
    compare_wasm_interfaces get_evidence_bundle export_evidence_bundle import_evidence_bundle
'''.split())
MEMORY_OPS = frozenset(('checkpoint', 'supplement', 'evidence', 'unknown', 'resolve'))
MEMORY = {}
for tool in WORKFLOW_TOOLS:
    if tool['name'] not in ('rf_next_case_open', 'rf_next_case_status', 'rf_next_case_record'):
        continue
    tool = json.loads(json.dumps(tool))
    if tool['name'] == 'rf_next_case_record':
        tool['description'] = 'Save optional task notes, evidence references and unresolved questions.'
        changes = tool['inputSchema']['properties']['change']['oneOf']
        changes[:] = [change for change in changes if change['properties']['op']['const'] in MEMORY_OPS]
    MEMORY[tool['name']] = tool

COMPARE = {
    'name': 'fusion_compare_outputs',
    'description': 'Compare two existing local output files byte for byte. Supply independently obtained outputs for a behavior check. This does not execute either side or establish their origin.',
    'inputSchema': {'type': 'object', 'properties': {
        'reference': {'type': 'string'}, 'candidate': {'type': 'string'}},
        'required': ['reference', 'candidate'], 'additionalProperties': False},
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False},
}

METHODS = {
    'index': ('Reverse Fusion', 'components/field-kit/domain-methods.md'),
    'forensics': ('Reverse Skills', 'skills/digital-forensics/references/forensics-triage.md'),
    'source-identity': ('Reverse Skills', 'skills/digital-forensics/references/distilled-symbols-timeline.md'),
    'sqlite': ('Reverse Fusion', 'components/field-kit/field-guide-database.md'),
    'flutter': ('Reverse Fusion / SEEP-inspired', 'components/host-adapters/review/references/flutter-observations.md'),
    'comparison': ('Reverse Fusion / Craft principles', 'components/field-kit/independent-build.md'),
    'evidence': ('Reverse Fusion / REA protocol', 'components/fusion-kit/rea-evidence.md'),
}
METHOD = {
    'name': 'fusion_read_method',
    'description': 'Read one optional domain reference, or omit topic to list available references. Methods are not a required tool order.',
    'inputSchema': {'type': 'object', 'properties': {'topic': {'type': 'string', 'enum': list(METHODS)}},
                    'additionalProperties': False},
    'annotations': COMPARE['annotations'],
}
FLUTTER = {
    'name': 'fusion_observe_flutter_library',
    'description': 'Read class-to-library references from a local ARM64 Flutter library, and separately obtain official REA ELF notes for the same bytes. For an APK use identify_flutter_build instead. Neither observation executes the app.',
    'inputSchema': {'type': 'object', 'properties': {
        'path': {'type': 'string'}, 'query': {'type': 'string'}},
        'required': ['path'], 'additionalProperties': False},
    'annotations': COMPARE['annotations'],
}


def read_method(args):
    if not args:
        return {'topics': [{'topic': topic, 'source': source, 'file': name}
                           for topic, (source, name) in METHODS.items()]}
    if set(args) != {'topic'} or not isinstance(args['topic'], str) or args['topic'] not in METHODS:
        raise ValueError('Select an advertised method topic.')
    source, name = METHODS[args['topic']]
    _, raw, identity = materials.ordinary(str(ROOT / name))
    method = {'topic': args['topic'], 'source': source, 'file': name,
              'sha256': identity['sha256'], 'text': raw.decode('utf-8-sig')}
    if args['topic'] == 'comparison':
        method['local_replay'] = {
            'argv_prefix': [sys.executable, '-I', str(ROOT / 'fusion.py'), 'replay'],
            'scope': 'Trusted local programs only; not a sandbox or an MCP execution tool.',
        }
    return method


def observe_flutter(args, call_native):
    if (not {'path'} <= args.keys() <= {'path', 'query'} or
            not isinstance(args['path'], str) or not Path(args['path']).is_absolute()):
        raise ValueError('Select an absolute path to an ordinary local Flutter library.')
    from flutter_inventory import observe
    specialty = observe(args['path'], args.get('query', ''))
    response = {'specialty': specialty, 'official': None, 'same_input': None,
                'runtime': 'unobserved', 'scope': 'static file identity and class ownership'}
    try:
        native = call_native('inspect_elf_notes', {'path': args['path']})
    except (EOFError, OSError, ValueError) as exc:
        response['official_issue'] = str(exc)[:480]
        return response
    response['official'] = native
    if native.get('isError') is not True:
        evidence = native.get('structuredContent') or {}
        digest = evidence.get('subject', {}).get('digest', {}).get('sha256')
        if (isinstance(digest, str) and len(digest) == 64 and
                evidence.get('operation') == 'inspect_elf_notes' and evidence.get('evidence_id')):
            response['same_input'] = specialty['file']['sha256'] == digest
    return response


def result(value, error=False):
    return {'content': [{'type': 'text', 'text': review.encode(value)}],
            'structuredContent': value, 'isError': error}


def compare_outputs(args):
    if (set(args) != {'reference', 'candidate'} or
            any(not isinstance(path, str) for path in args.values())):
        raise ValueError('Supply two explicit local output paths.')
    left, expected, origin = materials.ordinary(args['reference'])
    right, observed, candidate = materials.ordinary(args['candidate'])
    if left.samefile(right):
        raise ValueError('Select two distinct outputs, not two references to the same file.')
    offset = None
    if expected != observed:
        offset = next((i for i, (a, b) in enumerate(zip(expected, observed)) if a != b),
                      min(len(expected), len(observed)))
    return {'basis': 'owned-byte-comparison', 'reference': origin, 'candidate': candidate,
            'bytes_equal': offset is None, 'first_differing_byte_offset': offset,
            'execution_observed': False, 'independence_verified': False}


class FusionServer(review.Server):
    def __init__(self):
        super().__init__()
        self.native = None
        self.native_tools = None
        self.native_problem = None
        self.scratch = None

    def close(self):
        try:
            if self.native is not None:
                self.native.close()
        finally:
            self.native = None
            if self.scratch is not None:
                self.scratch.cleanup()
                self.scratch = None

    def upstream(self):
        if self.native_problem is not None:
            raise ValueError(self.native_problem)
        if self.native is not None:
            return self.native
        runtime = review.runtime.checked()
        self.scratch = tempfile.TemporaryDirectory(prefix='reverse-fusion-rea-')
        cwd = Path(self.scratch.name)
        env = {key: value for key, value in os.environ.items()
               if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP'}}
        env.update(HOME=str(cwd), USERPROFILE=str(cwd), CI='1', DO_NOT_TRACK='1', NO_COLOR='1')
        try:
            self.native = StdioMcp([runtime['node'], runtime['entry'], 'mcp'], cwd=cwd, env=env, timeout=20)
            identity = self.native.initialize()['serverInfo']
            if identity.get('name') != 'rea' or identity.get('version') != runtime['rea_version']:
                raise ValueError('Registered official REA identity differs from the locked release.')
            selected = {tool['name']: tool for tool in catalog(self.native) if tool['name'] in NATIVE}
            if selected.keys() != NATIVE:
                raise ValueError('The selected native tools do not match this official release.')
            self.native_tools = selected
            return self.native
        except BaseException:
            self.close()
            raise

    def call_native(self, name, args):
        try:
            return self.upstream().request('tools/call', {'name': name, 'arguments': args})
        except (EOFError, TimeoutError, BrokenPipeError) as exc:
            self.native_problem = 'Official REA connection lost. Reconnect and reimport saved evidence.'
            self.close()
            raise ValueError(self.native_problem) from exc

    def dispatch(self, method, params):
        if method == 'initialize':
            response = super().dispatch(method, params)
            response['serverInfo'] = {'name': PROFILE['profile'], 'version': PROFILE['version']}
            response['instructions'] = (
                'Local analysis, official REA Evidence, and optional task memory. '
                'Use ordinary tools where sufficient. The native catalog is a selected local-analysis subset. '
                'Field readings and output comparisons have their own provenance.')
            return response
        if not self.initialized or method not in ('tools/list', 'tools/call'):
            return super().dispatch(method, params)
        if method == 'tools/list':
            response = super().dispatch(method, params)
            if self.native_tools is None:
                try:
                    self.upstream()
                except (OSError, ValueError, KeyError, EOFError) as exc:
                    self.native_problem = f'Official REA unavailable: {str(exc)[:480]}'
                    # Keep the advertised catalog stable for this connection.
                    self.native_tools = {}
            response['tools'].extend(self.native_tools.values())
            response['tools'].extend((*MEMORY.values(), COMPARE, METHOD, FLUTTER))
            return response
        name = params.get('name')
        if not isinstance(name, str) or name in review.SPECS:
            response = super().dispatch(method, params)
            if name == 'review_info' and not response.get('isError'):
                value = response['structuredContent']
                value['fusion'] = {**PROFILE, 'official_rea': (
                    {'status': 'unavailable', 'reason': self.native_problem} if self.native_problem else
                    {'status': 'connected' if self.native else 'not-yet-connected'})}
                return result(value)
            return response
        args = params.get('arguments', {})
        if not isinstance(args, dict):
            review.rpc_error(-32602, 'Tool arguments must be an object.')
        try:
            if name in NATIVE:
                return self.call_native(name, args)
            if name == METHOD['name']:
                return result(read_method(args))
            if name == FLUTTER['name']:
                return result(observe_flutter(args, self.call_native))
            if name == COMPARE['name']:
                return result(compare_outputs(args))
            if name in MEMORY:
                if name == 'rf_next_case_record':
                    change = args.get('change')
                    if not isinstance(change, dict) or change.get('op') not in MEMORY_OPS:
                        raise ValueError('This profile accepts notes and evidence, not execution operations.')
                return result(call_owned(name, args))
        except (EOFError, OSError, ValueError, KeyError, TypeError) as exc:
            return result({'error': {'message': str(exc)[:640]}}, error=True)
        review.rpc_error(-32602, 'Unknown fusion tool.')


def main():
    if sys.argv[1:] != ['mcp']:
        return review.main()
    server = FusionServer()
    try:
        review.serve(server=server)
    finally:
        server.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
