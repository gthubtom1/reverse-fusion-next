"""Static-only inspection receipt: no product imports, tests, servers or providers."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'evidence/next/static-recheck'

def checksum(path, normalized=False):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n', b'\n') if normalized else data).hexdigest()

files = sorted([*ROOT.glob('rea_enhanced/*.py'), *ROOT.glob('reverse_fusion/*.py'),
                *ROOT.glob('tests_next/*.py'), ROOT/'components/reverse-core/router.py'])
parsed = {}
for path in files:
    text = path.read_text(encoding='utf-8-sig')
    tree = ast.parse(text, filename=str(path))
    compile(tree, str(path), 'exec')  # compile only; never exec/import product code
    parsed[path.relative_to(ROOT).as_posix()] = tree
server = parsed['rea_enhanced/server.py']
tool_names = [node.args[0].value for node in ast.walk(server)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == '_tool' and node.args and isinstance(node.args[0], ast.Constant)]
assert set(tool_names) == {'rf_next_case_open', 'rf_next_case_status', 'rf_next_case_record',
                           'rf_next_compare', 'rf_next_storage'}
assert len(tool_names) == 5
changes = {node.args[0].value for node in ast.walk(server)
           if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
           and node.func.id == '_change' and node.args and isinstance(node.args[0], ast.Constant)}
assert {'requirement', 'feature', 'product', 'coverage', 'deliver_stage', 'deliver', 'execute'} <= changes
json_paths = ['docs/ACTIVE-DOCUMENTS.json', 'docs/NEXT/STATUS.json',
              'components/reverse-core/runtime.json', 'components/reverse-core/routing.json',
              'components/reverse-core/preservation.json', 'vendor/rea/manifest.json', 'vendor/node/manifest.json']
for name in json_paths:
    json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
active = json.loads((ROOT/'docs/ACTIVE-DOCUMENTS.json').read_text(encoding='utf-8'))['active']
assert all((ROOT/name).is_file() for name in active)
manifest = json.loads((ROOT/'components/reverse-core/preservation.json').read_text(encoding='utf-8'))
assert all(checksum(ROOT/name, not name.endswith('.jar')) == entry['sha256']
           for name, entry in manifest['files'].items())
methods = json.loads((ROOT/'vendor/rea/manifest.json').read_text(encoding='utf-8'))['method_files_sha256']
assert all(checksum(ROOT/'vendor/rea'/name) == expected for name, expected in methods.items())
entry_record = json.loads((ROOT/'evidence/next/slim/deployment-preservation.json').read_text())['before']
assert all(checksum(Path(name)) == expected for name, expected in entry_record.items())
diff = subprocess.run(['git', 'diff', '--check'], cwd=ROOT, capture_output=True)
assert diff.returncode == 0, diff.stdout.decode(errors='replace')
new_tests = sum(isinstance(node, ast.FunctionDef) and node.name.startswith('test_')
                for node in ast.walk(parsed['tests_next/test_static_recheck.py']))
report = {'date': '2026-11-18', 'status': 'static-checks-pass; runtime-unverified',
    'mode': 'AST parse and compile only, JSON decode, file/hash/contract inspection and git diff --check',
    'python_files': len(files), 'json_contract_files': len(json_paths), 'new_regression_specs': new_tests,
    'regression_specs_executed': 0, 'owned_tools': tool_names, 'record_operations': sorted(changes),
    'preserved_domain_files': len(manifest['files']), 'official_method_files': len(methods),
    'user_entry_files_unchanged': len(entry_record), 'git_diff_check': 'pass',
    'source_sha256': {name: checksum(ROOT/name, True) for name in parsed},
    'active_contract_sha256': {name: checksum(ROOT/name, True) for name in active if name != 'docs/CURRENT-STATE.md'},
    'baseline_archive': 'state/static-recheck-20261118/pre-repair-source.zip',
    'baseline_archive_sha256': checksum(ROOT/'state/static-recheck-20261118/pre-repair-source.zip'),
    'prohibited_work_executed': {'installation': False, 'functional_tests': False,
        'target_execution': False, 'server_or_provider_start': False, 'real_model_conversations': False},
    'prior_179_scope': 'Historical source-bound regressions only; not evidence for the new static repairs'}
OUT.mkdir(parents=True, exist_ok=True)
(OUT/'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({k: report[k] for k in ('status', 'python_files', 'json_contract_files', 'new_regression_specs',
    'regression_specs_executed', 'preserved_domain_files', 'official_method_files', 'user_entry_files_unchanged', 'git_diff_check')}, ensure_ascii=False))
