"""Set up or attach the shared evidence-review profile to one local agent host."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from typing import NamedTuple

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path[:0] = [str(SCRIPTS), str(ROOT)]
from rea_enhanced.deployment import _replace_checked
from rea_enhanced.storage import locked
from review_host_config import NAME, has_registration, update


HOSTS = ("codex", "pi", "claude", "opencode")
TEMPLATE = ROOT / "components/host-adapters/review"
FIELD = NAME == "reverse-fusion-field"
REVIEW = SCRIPTS / ("field-service.py" if FIELD else "next-review.py")
SAMPLE = ROOT / "evidence/next/s2/native-bundle.json"
RECEIPT = ".reverse-fusion-install.json"


class Layout(NamedTuple):
    name: str
    service: Path
    skill: Path
    methods: Path
    profile: Path | None


DEFAULT = Layout(NAME, REVIEW, TEMPLATE / "SKILL.md", TEMPLATE / "references",
                 SCRIPTS / "field-release.json" if FIELD else None)
FIELD_SOURCE = ROOT / "components/field-kit"
CHECKOUT = Layout("reverse-fusion-field", FIELD_SOURCE / "service.py", FIELD_SOURCE / "SKILL.md",
                  FIELD_SOURCE, FIELD_SOURCE / "profile.json")
FUSION_SOURCE = ROOT / "components/fusion-kit"
FUSION = Layout("reverse-fusion", FUSION_SOURCE / "service.py", FUSION_SOURCE / "SKILL.md",
                FIELD_SOURCE, FUSION_SOURCE / "profile.json")
FIELD_TOOLS = {"field_observe", "field_compare_files", "field_decode_records", "field_rea_identify"}
FUSION_MINIMUM = {"inspect_pe_imports", "inspect_sqlite_database",
                  "export_evidence_bundle", "import_evidence_bundle", "fusion_compare_outputs",
                  "fusion_read_method", "fusion_observe_flutter_library",
                  "rf_next_case_open", "rf_next_case_record", "rf_next_case_status"}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def reject_link(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"An entry is a link or reparse point: {path}")


def existing(path):
    reject_link(path)
    return path.read_bytes() if path.exists() else None


def paths(host, home=None, *, opencode_version=1, layout=DEFAULT):
    """An explicit home models a new user; normal installs honor host overrides."""
    profile = Path(home).resolve() if home else Path.home()

    def location(variable, default):
        value = None if home else os.environ.get(variable)
        return Path(value).expanduser().resolve() if value else default

    if host == "codex":
        directory = location("CODEX_HOME", profile / ".codex")
        return directory / "skills" / layout.name, directory / "config.toml"
    if host == "claude":
        return location("CLAUDE_CONFIG_DIR", profile / ".claude") / "skills" / layout.name, None
    if host == "pi":
        directory = location("PI_CODING_AGENT_DIR", profile / ".pi/agent")
        return directory / "skills" / layout.name, directory / "mcp.json"
    default = location("XDG_CONFIG_HOME", profile / ".config") / "opencode"
    directory = location("OPENCODE_CONFIG_DIR", default)
    override = location("OPENCODE_CONFIG", None)
    # The v2 native global MCP command writes opencode.json.
    config = override or directory / ("opencode.json" if opencode_version == 2 else "opencode.jsonc")
    return directory / "skills" / layout.name, config


def command(layout=DEFAULT):
    return [str(Path(sys.executable).resolve()), "-B", "-I", str(layout.service), "mcp"]


def opencode_version(host):
    if host != "opencode":
        return 1
    try:
        completed = subprocess.run(["opencode", "--version"], capture_output=True, text=True, timeout=10)
        match = re.search(r"\b(\d+)\.", completed.stdout + completed.stderr)
        return 2 if match and int(match.group(1)) >= 2 else 1
    except (OSError, subprocess.TimeoutExpired):
        return 1


GUIDE_NAME = re.compile(r"field-guide-[a-z0-9-]+\.md")
CLAUDE_MANIFEST = ".claude-plugin/plugin.json"
CLAUDE_SERVER = ".mcp.json"


def fixed_skill_sources(layout):
    sources = {name: TEMPLATE / name for name in
               ("references/reporting.md", "references/flutter-observations.md")}
    sources["SKILL.md"] = layout.skill
    for name in ("forensics-triage.md", "distilled-symbols-timeline.md"):
        sources["references/" + name] = ROOT / "skills/digital-forensics/references" / name
    sources["references/Reverse-Skills-LICENSE"] = ROOT / "skills/LICENSE"
    if layout.profile is not None:
        for name in ("independent-build.md", "domain-methods.md", "raw-materials.md"):
            sources["references/" + name] = layout.methods / name
    if layout.name == FUSION.name:
        sources["references/rea-evidence.md"] = layout.skill.with_name("rea-evidence.md")
    return sources


def skill_files(host, argv, layout=DEFAULT):
    files = {name: source.read_bytes() for name, source in fixed_skill_sources(layout).items()}
    if layout.profile is not None:
        field_profile = json.loads(layout.profile.read_bytes())
        if field_profile.get("profile") != layout.name:
            raise ValueError(f"Invalid Field profile in {layout.profile}")
        release_version = field_profile["version"]
        guide_profile = (json.loads(CHECKOUT.profile.read_bytes())
                         if layout.name == FUSION.name else field_profile)
        guides = guide_profile.get("field_guides", [])
        if not isinstance(guides, list) or any(not isinstance(n, str) or not GUIDE_NAME.fullmatch(n) for n in guides):
            raise ValueError("Invalid field guide list")
        for name in guides:
            files["references/" + name] = (layout.methods / name).read_bytes()
    if host == "claude":
        files[CLAUDE_MANIFEST] = encoded({"name": layout.name, "version": release_version if layout.profile else "1.0.0",
            "description": "Observe local artifacts and compare independent implementations" if layout.profile else "Review local REA evidence bundles"})
        files[CLAUDE_SERVER] = encoded({"mcpServers": {"review": {"command": argv[0], "args": argv[1:]}}})
    return files


def receipt_files(record, host, layout):
    """Accept only paths the installer can own, including retired Field guides."""
    owned = record.get("files")
    fixed = set(fixed_skill_sources(layout))
    if host == "claude":
        fixed.update((CLAUDE_MANIFEST, CLAUDE_SERVER))
    if not isinstance(owned, dict) or "SKILL.md" not in owned:
        raise ValueError("Invalid installed file inventory in receipt.")
    for name, digest in owned.items():
        if name not in fixed and not (layout.profile and name.startswith("references/")
                                      and GUIDE_NAME.fullmatch(name[len("references/"):])):
            raise ValueError(f"Unrecognized file in installation receipt: {name}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid installed digest for {name}")
    return owned


def check_transport(argv, layout=DEFAULT):
    calls = [
        ("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                        "clientInfo": {"name": "review-host-check", "version": "1"}}),
        ("notifications/initialized", {}),
        ("tools/list", {}),
        ("tools/call", {"name": "review_summary", "arguments": {"path": str(SAMPLE)}}),
        ("tools/call", {"name": "review_rea_import", "arguments": {"path": str(SAMPLE)}}),
    ]
    if layout.name == FUSION.name:
        calls.append(("tools/call", {"name": "inspect_pe_imports", "arguments": {"path": str(Path(sys.executable).resolve())}}))
    messages = [{"jsonrpc": "2.0", "method": method, "params": args,
                 **({} if method.startswith("notifications/") else {"id": i})}
                for i, (method, args) in enumerate(calls)]
    sent = "".join(json.dumps(message) + "\n" for message in messages)
    result = subprocess.run(argv, input=sent.encode("utf-8"), capture_output=True, timeout=35,
                            cwd=SAMPLE.parent)
    if result.returncode:
        raise ValueError("The registered reviewer did not start. Run setup again from its checkout.")
    replies = {m["id"]: m for m in map(json.loads, result.stdout.splitlines())}
    for i in (0, 2, 3, 4):
        reply = replies.get(i, {}).get("result", {})
        if not reply or reply.get("isError"):
            detail = reply.get("structuredContent", {}).get("error", {})
            raise ValueError(f"Review connection failed at {calls[i][0]}. {detail.get('message', '')} "
                             "Use setup to prepare the shared REA runtime.")
    tools = [item["name"] for item in replies[2]["result"]["tools"]]
    expected = {"review_info", "review_summary", "review_compare", "review_rea_import", "review_rea_compare"}
    if layout.profile is not None:
        expected.update(FIELD_TOOLS)
    if layout.name == FUSION.name:
        if not expected | FUSION_MINIMUM <= set(tools) or len(set(tools)) != len(tools):
            raise ValueError("Fusion is missing required tools or returned duplicate names.")
        native = replies.get(5, {}).get("result", {})
        evidence = native.get("structuredContent", {})
        if native.get("isError") or not evidence.get("evidence_id") or "normalized_result" not in evidence:
            raise ValueError("The native REA inspection did not return official Evidence.")
    elif set(tools) != expected:
        raise ValueError("The reviewer returned an unexpected tool catalog.")
    counts = replies[3]["result"]["structuredContent"]["section_counts"]
    official = replies[4]["result"]["structuredContent"]["official"]
    payload = official["payload"]
    if (counts["records"] != 2 or official["implementation"] != "rea-agents"
            or official["command"] != "evidence-import" or official["exit_code"] != 0
            or payload != {"imported": 2, "total": 2, "unknowns_added": 0}):
        raise ValueError("The known fixture's record count did not match.")
    service = replies[0]["result"]["serverInfo"]
    if service.get("name") != layout.name or (layout.profile is not None and
            service.get("version") != json.loads(layout.profile.read_bytes())["version"]):
        raise ValueError("Registered service identity differs from this checkout. Check the service and profile versions.")
    return {"service": service["name"], "service_version": service["version"], "tools": tools,
            "fixture_records": counts["records"], "official_rea_version": official["version"], "official_import": payload}


def apply(changes):
    applied = []
    try:
        for path, before, after in changes:
            if before != after:
                _replace_checked(path, before, after)
                applied.append((path, after, before))
    except (ValueError, OSError):
        for path, after, before in reversed(applied):
            _replace_checked(path, after, before)
        raise


def empty_skill_tree(folder):
    if not folder.exists():
        return True
    if folder.is_symlink() or not folder.is_dir():
        return False
    return all(p.name in ("references", ".claude-plugin") and p.is_dir()
               and not p.is_symlink() and not any(p.iterdir()) for p in folder.iterdir())


def check_absent_installation(host, folder, config, layout=DEFAULT):
    """A missing receipt authorizes no writes. Report any remaining recognizable entries."""
    remnants = []
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        remnants.append(folder)
    elif folder.is_dir():
        for name in skill_files(host, command(layout), layout):
            candidate = folder / name
            if candidate.exists() or candidate.is_symlink():
                remnants.append(candidate)
    configs = [config] if config else []
    if host == "opencode":
        configs.extend(folder.parent.parent / name for name in ("config.json", "opencode.json", "opencode.jsonc"))
    for path in dict.fromkeys(configs):
        try:
            if has_registration(host, existing(path), name=layout.name):
                remnants.append(path)
        except (ValueError, OSError) as exc:
            raise ValueError(f"Missing installation receipt {folder / RECEIPT}. Inspect the configuration at {path}. "
                             "All entries have been preserved.") from exc
    if remnants:
        paths_found = ", ".join(map(str, remnants))
        raise ValueError(f"Missing installation receipt {folder / RECEIPT}. Inspect the remaining entries at "
                         f"{paths_found}. All entries have been preserved.")
    return {"status": "no-owned-installation", "host": host, "skill": str(folder),
            "mcp_config": str(config or folder / ".mcp.json")}


def manage(action, host, home=None, *, opencode_version=1, layout=DEFAULT):
    folder, config = paths(host, home, opencode_version=opencode_version, layout=layout)
    identity = os.path.normcase(str(folder.resolve()))
    lock = Path(tempfile.gettempdir()) / "reverse-fusion-review-locks" / sha256(identity.encode()).hexdigest()
    with locked(lock, timeout=30):
        reject_link(folder)
        reject_link(folder / 'references')
        if host == 'claude':
            reject_link(folder / '.claude-plugin')
        receipt_file = folder / RECEIPT
        raw = existing(receipt_file)
        record = json.loads(raw) if raw is not None else None
        if raw is not None and (not isinstance(record, dict) or record.get("schema") != 1
                                or record.get("checkout") != str(ROOT) or record.get("host") != host):
            raise ValueError(f"This host entry belongs to another checkout. Inspect {receipt_file}.")
        if record and host == "opencode" and record.get("opencode_version", 1) != opencode_version:
            raise ValueError(f"Use --opencode-version {record.get('opencode_version', 1)} for this installation.")
        if record and config and str(config) != record["config_file"]:
            raise ValueError(f"Host now selects a different configuration. Original: {record['config_file']}.")
        if record is None and action == "remove":
            return check_absent_installation(host, folder, config, layout)
        if record is None and (action == "check" or not empty_skill_tree(folder)):
            raise ValueError(f"Missing installation receipt or existing unowned skill directory: {folder}")
        argv = record["command"] if record else command(layout)
        if action != "remove" and argv != command(layout):
            raise ValueError("The installed Python or checkout path differs. Remove the old entry and run setup again.")
        remove = action == "remove"
        owned = receipt_files(record, host, layout) if record else {}
        files = {} if remove else skill_files(host, argv, layout)
        desired = {name: sha256(content).hexdigest() for name, content in files.items()}
        if action == "check" and owned != desired:
            raise ValueError("Installed skill files differ from this checkout. Run setup to sync them.")

        previous = {}
        for name in dict.fromkeys((*owned, *files)):
            path = folder / name
            value = previous[name] = existing(path)
            if name not in owned:
                if value is not None:
                    raise ValueError(f"An unowned skill file already exists: {path}")
            elif value is None:
                if name in files and not (action == 'attach' and record.get('pending')):
                    raise ValueError(f"Installed file is missing: {path}")
            elif sha256(value).hexdigest() != owned[name]:
                raise ValueError(f"Installed file changed; inspect {path} before continuing.")
        prior_config = existing(config) if config else None
        patch = record["config_patch"] if record else None
        next_config = None
        if host == "opencode" and action != "remove":
            directory = folder.parent.parent
            for other in (directory / "config.json", directory / "opencode.json", directory / "opencode.jsonc"):
                if other != config and other.is_file():
                    # A native host would merge the two files; an existing entry
                    # in a different layer belongs to its owner, even if identical.
                    update(host, existing(other), argv, opencode_version=opencode_version, name=layout.name)
        if config:
            next_config, patch = update(host, prior_config, argv, patch, remove=action == "remove",
                                        opencode_version=opencode_version, name=layout.name)
        if action == "check":
            if record.get("pending") or next_config != prior_config:
                raise ValueError("The configured server is missing.")
            if host == "claude":
                server = json.loads(previous[CLAUDE_SERVER])["mcpServers"]["review"]
                argv = [server["command"], *server["args"]]
            return {"status": "verified", "host": host, "skill": str(folder), **check_transport(argv, layout)}
        changes = [(folder / name, before, files.get(name)) for name, before in previous.items()]
        if config:
            changes.append((config, prior_config, next_config))
        receipt = {"schema": 1, "host": host, "checkout": str(ROOT), "command": argv,
                   "config_file": str(config) if config else None, "config_patch": patch,
                   "files": desired}
        if host == "opencode" and opencode_version == 2:
            receipt["opencode_version"] = opencode_version
        if not remove:
            proof = check_transport(argv, layout)
            if raw is None:
                # A stopped first install is resumable without saving unrelated config.
                pending = encoded(dict(receipt, pending=True))
                changes.insert(0, (receipt_file, None, pending))
                raw = pending
        changes.append((receipt_file, raw, None if remove else encoded(receipt)))
        apply(changes)
        if remove:
            for directory in (folder / "references", folder / ".claude-plugin", folder):
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
        result = {"status": "removed" if remove else "attached", "host": host, "skill": str(folder),
                  "mcp_config": str(config or folder / ".mcp.json")}
        if not remove:
            result["fixture_records"] = proof["fixture_records"]
        return result


def main(*, repository_field=False, repository_fusion=False):
    layout = FUSION if repository_fusion else CHECKOUT if repository_field else DEFAULT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "attach", "check", "remove"))
    parser.add_argument("host", choices=HOSTS)
    parser.add_argument("--home", help="Isolated user home; ignores user-specific configuration overrides.")
    parser.add_argument("--opencode-version", type=int, choices=(1, 2),
                        help="OpenCode configuration major version. Defaults to 1; select 2 explicitly for Desktop 2.x.")
    args = parser.parse_args()
    if args.opencode_version is not None and args.host != "opencode":
        parser.error("--opencode-version applies only to the opencode host.")
    try:
        started = time.monotonic()
        if args.action == "setup":
            prepared = subprocess.run([sys.executable, "-B", "-I", str(layout.service), "prepare"], cwd=ROOT)
            if prepared.returncode:
                return prepared.returncode
        action = "attach" if args.action == "setup" else args.action
        selected_opencode_version = args.opencode_version or opencode_version(args.host)
        result = manage(action, args.host, args.home, opencode_version=selected_opencode_version, layout=layout)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
