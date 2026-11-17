"""Static final-form inspection only; never import/execute the product or tests."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'evidence/next/autonomy-final'

def sha(path, normalize=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if normalize else data).hexdigest()

paths = sorted([*ROOT.glob('rea_enhanced/*.py'), *ROOT.glob('reverse_fusion/*.py'),
                *ROOT.glob('tests_next/*.py'), ROOT/'components/reverse-core/router.py'])
trees = {}
for path in paths:
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    compile(tree, str(path), 'exec')
    trees[path.relative_to(ROOT).as_posix()] = tree
server = trees['rea_enhanced/server.py']
tools = [node.args[0].value for node in ast.walk(server)
         if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
         and node.func.id == '_tool' and node.args and isinstance(node.args[0], ast.Constant)]
assert len(tools) == 5 and set(tools) == {'rf_next_case_open', 'rf_next_case_status',
    'rf_next_case_record', 'rf_next_compare', 'rf_next_storage'}
changes = {}
for node in ast.walk(server):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_change':
        name = node.args[0].value
        properties = {key.value for key in node.args[1].keys}
        required = set(ast.literal_eval(node.args[2]))
        assert required <= properties
        changes[name] = {'properties': sorted(properties), 'required': sorted(required)}
assert {'checkpoint', 'output_goal', 'assessment', 'deliver_reviewed', 'requirement'} <= set(changes)
assert {'evaluation'} <= set(changes['requirement']['properties'])
workflow_text = (ROOT/'rea_enhanced/workflow.py').read_text(encoding='utf-8')
assert all("op == '"+name+"'" in workflow_text for name in ('checkpoint', 'output_goal', 'assessment', 'deliver_reviewed'))
# A reviewed outcome must not write either automatic checks or native records.
review_tree = trees['rea_enhanced/evidence_review.py']
for node in ast.walk(review_tree):
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Constant):
                    assert child.slice.value not in {'checks', 'normalized_result', 'evidence_id'}
assert not any(isinstance(n, ast.ImportFrom) and n.module == 'workflow' for n in review_tree.body)

json_files = ['docs/ACTIVE-DOCUMENTS.json', 'docs/NEXT/STATUS.json',
              'components/reverse-core/runtime.json', 'components/reverse-core/routing.json',
              'components/reverse-core/preservation.json', 'vendor/rea/manifest.json', 'vendor/node/manifest.json']
for name in json_files:
    json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
active = json.loads((ROOT/'docs/ACTIVE-DOCUMENTS.json').read_text(encoding='utf-8'))['active']
assert all((ROOT/name).is_file() for name in active)
preserved = json.loads((ROOT/'components/reverse-core/preservation.json').read_text(encoding='utf-8'))['files']
assert all(sha(ROOT/name, not name.endswith('.jar')) == entry['sha256'] for name, entry in preserved.items())
official = json.loads((ROOT/'vendor/rea/manifest.json').read_text(encoding='utf-8'))['method_files_sha256']
assert all(sha(ROOT/'vendor/rea'/name) == expected for name, expected in official.items())
entries = json.loads((ROOT/'evidence/next/slim/deployment-preservation.json').read_text(encoding='utf-8'))['before']
assert all(sha(Path(name)) == expected for name, expected in entries.items())
# Render only the known AST literal/f-string pieces, never exec skill_text.
fn = next(n for n in trees['rea_enhanced/deployment.py'].body if isinstance(n, ast.FunctionDef) and n.name == 'skill_text')
value = next(n.value for n in ast.walk(fn) if isinstance(n, ast.Return))
def static_skill(root):
    pieces = []
    for item in value.values:
        if isinstance(item, ast.Constant):
            pieces.append(item.value)
        else:
            assert isinstance(item, ast.FormattedValue) and isinstance(item.value, ast.Name) and item.value.id == 'repo'
            pieces.append(root)
    return ''.join(pieces).encode('utf-8')
parts = {name: (ROOT/name).stat().st_size for name in ('RULES.md', 'docs/AGENT-WORKFLOW.md')}
parts['owned_skill'] = len(static_skill(ROOT.as_posix()))
long_root = 'D:/tmp/reverse-next-slim-55fuatfp/source'
long_total = sum(v for k, v in parts.items() if k != 'owned_skill') + len(static_skill(long_root))
assert sum(parts.values()) <= 6144 and long_total <= 6144
archive = ROOT/'state/autonomy-final-20261118/pre-change-source.zip'
identity = json.loads((archive.parent/'identity.json').read_text(encoding='utf-8'))['files']
with zipfile.ZipFile(archive) as source:
    assert len(source.namelist()) == len(identity)
    assert all(hashlib.sha256(source.read(name)).hexdigest() == checksum for name, checksum in identity.items())
diff = subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True)
assert diff.returncode == 0, diff.stdout.decode(errors='replace')
specs = sum(isinstance(n, ast.FunctionDef) and n.name.startswith('test_')
            for n in ast.walk(trees['tests_next/test_autonomy.py']))
report = {'date': '2026-11-18', 'status': 'static-checks-pass; runtime-not-executed',
    'scope': 'Final autonomous optional-support implementation, not release or model-effect acceptance',
    'python_parse_compile_files': len(paths), 'json_contract_files': len(json_files),
    'owned_tool_names': tools, 'owned_record_operations': changes,
    'new_regression_specifications': specs, 'regression_specifications_executed': 0,
    'external_review_contract': 'Separate assessment/reviewed_delivery; no writes to automatic checks/native Evidence',
    'public_instruction_bytes': parts, 'public_instruction_total': sum(parts.values()),
    'long_checkout_example_total': long_total, 'instruction_limit_bytes': 6144,
    'preserved_domain_files': len(preserved), 'official_method_files': len(official),
    'user_entry_files_unchanged': len(entries), 'diff_check': 'pass',
    'baseline_archive': archive.relative_to(ROOT).as_posix(), 'baseline_archive_sha256': sha(archive),
    'baseline_archive_members_rehashed': len(identity),
    'source_identity': {name: sha(ROOT/name, True) for name in trees},
    'active_contract_identity': {name: sha(ROOT/name, True) for name in active if name != 'docs/CURRENT-STATE.md'},
    'execution': {'installations': 0, 'functional_tests': 0, 'target_or_provider_starts': 0,
                  'mcp_servers_started': 0, 'model_experiments': 0},
    'historical_179': 'Previous slim source only; not current source qualification',
    'semantic_limits': ['Static inspection does not establish runtime behavior or source authenticity of arbitrary external results.',
        'Host-reviewed wording and evidence association remain semantic judgments, not automatically authenticated proof.',
        'No current device/service state, hidden-target success or model superiority established.']}
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({key: report[key] for key in ('status', 'python_parse_compile_files', 'json_contract_files',
    'new_regression_specifications', 'regression_specifications_executed', 'public_instruction_total',
    'long_checkout_example_total', 'preserved_domain_files', 'official_method_files',
    'user_entry_files_unchanged', 'baseline_archive_members_rehashed', 'diff_check')}, ensure_ascii=False))
