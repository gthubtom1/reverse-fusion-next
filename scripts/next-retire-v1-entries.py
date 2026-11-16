"""Retire the explicit old install entry list in the independent v2 checkout."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
names=('core','craft','craft-mcp','spec','rea','node','jadx','wabt')
for name in names:
    path=root/'scripts'/('bootstrap-'+name+'.ps1')
    path.write_text("throw 'Historical v1 bootstrap retired. Use scripts/install.ps1 or Python -m rea_enhanced bootstrap; see docs/AGENT-BOOTSTRAP.md.'\n",encoding='utf-8')
for name in ('install.sh','uninstall.sh'):
    (root/'scripts'/name).write_text('#!/bin/sh\necho "v2 automatic installation is qualified for Windows x64 Codex. See docs/AGENT-BOOTSTRAP.md; the v1 installer is retired." >&2\nexit 2\n',encoding='utf-8')
(root/'reverse_fusion/cli.py').write_text('"""Compatibility command name; v1 installation chain is retired."""\nfrom rea_enhanced.cli import main\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n',encoding='utf-8')
(root/'scripts/uninstall.ps1').write_text("param([Parameter(Mandatory=$true)][string]$Receipt)\n& (Join-Path $PSScriptRoot '..\\.venv\\Scripts\\python.exe') -m rea_enhanced rollback --receipt $Receipt\nexit $LASTEXITCODE\n",encoding='utf-8')
