"""Register this checkout's Field tools and skills with a local host."""
from pathlib import Path
from runpy import run_path


if __name__ == "__main__":
    installer = Path(__file__).resolve().parent / "scripts" / "review-host.py"
    raise SystemExit(run_path(str(installer))["main"](repository_field=True))
