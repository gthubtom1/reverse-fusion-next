"""Next-generation CLI. All target paths belong to the selected outcome project."""
import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .storage import read
from .workflow import open_case, record, status, run_check
from .comparison import compare


def main(argv=None):
    parser = argparse.ArgumentParser(prog='rea-enhanced')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('mcp')
    commands.add_parser('doctor')
    provider_parser=commands.add_parser('providers')
    provider_parser.add_argument('--refresh',action='store_true')
    for name in ('open', 'record', 'status', 'compare'):
        p = commands.add_parser(name)
        p.add_argument('--project-root', type=Path, default=Path.cwd())
        p.add_argument('--case-root', default='work/current-case')
        if name == 'open':
            p.add_argument('--request', required=True)
        if name == 'record':
            p.add_argument('--change-file', type=Path, required=True)
            p.add_argument('--revision', type=int, required=True)
        if name == 'compare':
            p.add_argument('--plan', required=True)
            p.add_argument('--output', required=True)
            p.add_argument('--check-id')
    args = parser.parse_args(argv)
    try:
        if args.command == 'mcp':
            from .server import serve
            return serve()
        if args.command == 'doctor':
            from .health import inspect
            result=inspect()
            print(json.dumps(result,ensure_ascii=True,indent=2))
            return 0 if result['status']=='installed' else 2
        if args.command == 'providers':
            from .providers import providers
            result=providers(Path(__file__).resolve().parents[1],refresh=args.refresh)
            print(json.dumps(result,ensure_ascii=True,indent=2))
            return 0 if not result['unavailable'] else 2
        if args.command == 'open':
            result = open_case(args.project_root, args.request, args.case_root)
        elif args.command == 'record':
            result = record(args.project_root, args.case_root, read(args.change_file), args.revision)
        elif args.command == 'status':
            result = status(args.project_root, args.case_root)
        else:
            result = (run_check(args.project_root, args.case_root, args.check_id, args.plan, args.output)
                if args.check_id else compare(args.project_root, args.plan, args.output))
        print(json.dumps(result, ensure_ascii=True, indent=2))
        state = result.get('comparison', result).get('status')
        return 1 if state == 'fail' else 2 if state in {'unknown', 'unavailable', 'needs-context', 'superseded'} else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=True))
        return 2


if __name__ == '__main__':
    sys.exit(main())
