"""Use this checkout's unified local-analysis profile with one host."""
import argparse
import json
from pathlib import Path
from runpy import run_path
import sys


ROOT = Path(__file__).resolve().parent


def replay(argv):
    parser = argparse.ArgumentParser(prog="fusion.py replay",
                                     description="Compare declared behavior of two trusted local programs.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--plan", required=True, help="Project-relative finite replay plan")
    parser.add_argument("--output", required=True, help="New project-relative results directory")
    parser.add_argument("--trusted-local", action="store_true",
                        help="The plan and both programs are trusted; working copies are not a sandbox.")
    args = parser.parse_args(argv)
    if not args.trusted_local:
        parser.error("Use --trusted-local only after reviewing the plan and both programs.")
    sys.path.insert(0, str(ROOT))
    from rea_enhanced.comparison import compare
    try:
        if not args.project_root.is_dir():
            raise ValueError("Project root must be an existing directory.")
        report = compare(args.project_root, args.plan, args.output, finite_only=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        return 2
    print(json.dumps({"status": report["status"], "receipt": args.output + "/comparison.json",
                      "basis": report["operation"], "official_rea_evidence": False}))
    return {"pass": 0, "fail": 1, "unknown": 2}[report["status"]]


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"]:
        raise SystemExit(replay(sys.argv[2:]))
    installer = ROOT / "scripts" / "review-host.py"
    raise SystemExit(run_path(str(installer))["main"](repository_fusion=True))
