"""Owned EVIDENCE REVIEW profile. Python 3.11 standard library only.

Observed format: evidence/next/s2/native-bundle.json (official owned benign
export): seven array sections, no top-level format/version tag. Embedded paths
are data, never additional inputs. Official CLI access is a fixed file adapter.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import importlib.util


# Absolute sibling loading also works with Python -I and from arbitrary host cwd.
_runtime_spec = importlib.util.spec_from_file_location(
    "reverse_review_runtime", Path(__file__).resolve().with_name("review_runtime.py"))
runtime = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(runtime)


NAME = "reverse-fusion-review"
VERSION = "1.0.0"
PINNED_REA = "6.9.0"  # vendor/rea/manifest.json, observed 2026-11-19.
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SECTIONS = ("artifacts", "captures", "environments", "providers", "records",
            "scenarios", "unknowns")
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_NODES = 200_000
MAX_DEPTH = 64
MAX_RECORDS = 10_000
MAX_ITEMS = 50
SCOPE = {
    "kind": "owned-offline-review",
    "basis": "caller-selected local file bytes and declared JSON fields only",
    "upstream_execution_verified": False,
    "behavioral_equivalence_established": False,
    "embedded_paths_followed": False,
    "provenance_authenticated": False,
}


class ReviewError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fail(code, message):
    raise ReviewError(code, message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("invalid_json", "Duplicate JSON object keys.")
        result[key] = value
    return result


def _constant(_value):
    fail("invalid_json", "Non-finite JSON numbers are unsupported.")


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        fail("invalid_json", "Non-finite JSON numbers are unsupported.")
    return number


def parse_json(data):
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant,
                           parse_float=_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ReviewError):
            raise
        fail("invalid_json", "Expected bounded UTF-8 JSON.")
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            fail("input_limit", "JSON structure exceeds review limits.")
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
    return value


def read_json(path, *, with_bytes=False):
    """Read exactly one explicitly selected, bounded, ordinary local file."""
    if not isinstance(path, str) or not path or len(path) > 4096 or "\0" in path:
        fail("invalid_path", "Expected a local ordinary file path.")
    if (path.startswith(("\\\\", "//", "\\??\\")) or "://" in path
            or ":" in path[2:] or (":" in path and not re.match(r"^[A-Za-z]:[\\/]", path))):
        fail("invalid_path", "Network, device, URI and alternate-stream paths are unsupported.")
    try:
        selected = Path(os.path.abspath(path))
        for part in (*reversed(selected.parents), selected):
            metadata = part.lstat()
            if (stat.S_ISLNK(metadata.st_mode)
                    or getattr(metadata, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                fail("invalid_path", "Symlinks and reparse points are unsupported.")
        if not stat.S_ISREG(metadata.st_mode):
            fail("invalid_path", "Expected a local ordinary file.")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(selected, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                fail("invalid_path", "Expected a local ordinary file.")
            if opened.st_size > MAX_FILE_BYTES:
                fail("input_limit", "File exceeds review byte limit.")
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            fail("input_limit", "File exceeds review byte limit.")
        parsed = parse_json(data.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ReviewError):
            raise
        fail("file_error", "Selected file could not be read as ordinary UTF-8 JSON.")
    result = parsed, {"path": str(selected), "bytes": len(data), "sha256": sha(data)}
    return (*result, data) if with_bytes else result


def short_text(value):
    return isinstance(value, str) and 0 < len(value) <= 256


def bundle(path):
    value, identity = read_json(path)
    if not isinstance(value, dict) or set(value) != set(SECTIONS):
        fail("unsupported_format", "Expected the seven-section unversioned REA export shape.")
    if any(not isinstance(value[key], list) for key in SECTIONS):
        fail("unsupported_format", "REA export sections must be arrays.")
    if any(not isinstance(item, dict) for key in SECTIONS for item in value[key]):
        fail("unsupported_format", "REA export section entries must be objects.")
    if len(value["records"]) > MAX_RECORDS:
        fail("input_limit", "Record count exceeds review limit.")
    for provider in value["providers"]:
        if any(not short_text(provider.get(k)) for k in ("id", "version")):
            fail("unsupported_format", "Unsupported REA provider declaration.")
    ids = set()
    for record in value["records"]:
        if (any(not short_text(record.get(k)) for k in
                ("evidence_id", "operation", "predicate_type"))
                or not isinstance(record.get("subject"), dict)
                or not isinstance(record.get("provider"), dict)
                or not isinstance(record.get("parameters"), dict)
                or not isinstance(record.get("limitations"), list)
                or any(not isinstance(v, str) for v in record["limitations"])
                or not isinstance(record.get("evidence_links"), list)
                or any(not short_text(v) for v in record["evidence_links"])):
            fail("unsupported_format", "Unsupported REA evidence record shape.")
        if record["evidence_id"] in ids:
            fail("unsupported_format", "Duplicate evidence_id prevents unambiguous review.")
        ids.add(record["evidence_id"])
    return value, identity


def limited(values):
    values = sorted(values)
    return {"count": len(values), "items": values[:MAX_ITEMS],
            "omitted": max(0, len(values) - MAX_ITEMS)}


def counts(values):
    counted = Counter(values)
    keys = sorted(counted)
    return {"items": {k: counted[k] for k in keys[:MAX_ITEMS]},
            "distinct": len(keys), "omitted": max(0, len(keys) - MAX_ITEMS)}


def summary(path):
    value, identity = bundle(path)
    providers = sorted({(p["id"], p["version"]) for p in value["providers"]})
    unresolved_records = []
    for record in value["records"]:
        coverage = record.get("relationship_coverage")
        # Only interpret the explicit discovery status observed in the export.
        discovery = coverage.get("discovery", {}) if isinstance(coverage, dict) else {}
        if isinstance(discovery, dict) and any(
            isinstance(item, dict) and item.get("status") == "unknown"
            for item in discovery.values()
        ):
            unresolved_records.append(record["evidence_id"])
    return {
        "scope": SCOPE, "file": identity,
        "format": "rea-evidence-bundle-unversioned",
        "declared_bundle_version": None, "declared_rea_version": None,
        "section_counts": {k: len(value[k]) for k in SECTIONS},
        "declared_providers": {
            "count": len(providers),
            "items": [{"id": key, "version": version} for key, version in providers[:MAX_ITEMS]],
            "omitted": max(0, len(providers) - MAX_ITEMS),
        },
        "record_kinds": counts(r["predicate_type"] for r in value["records"]),
        "operations": counts(r["operation"] for r in value["records"]),
        "declared_unknown_entries": len(value["unknowns"]),
        "records_with_unknown_discovery": limited(unresolved_records),
        "records_with_limitations": sum(bool(r["limitations"]) for r in value["records"]),
        "interpretation": "Counts describe declarations, not resolution, validity or execution proof.",
    }


def compare(first, second):
    left, left_file = bundle(first)
    right, right_file = bundle(second)
    old = {r["evidence_id"]: r for r in left["records"]}
    new = {r["evidence_id"]: r for r in right["records"]}
    # Python treats True == 1; compare canonical JSON to retain JSON types.
    old_content = {k: encode(v) for k, v in old.items()}
    new_content = {k: encode(v) for k, v in new.items()}
    return {
        "scope": SCOPE, "first": left_file, "second": right_file,
        "bytes_equal": left_file["sha256"] == right_file["sha256"],
        "json_equal": encode(left) == encode(right),
        "records": {
            "added": limited(new.keys() - old.keys()),
            "removed": limited(old.keys() - new.keys()),
            "changed": limited(k for k in old.keys() & new.keys()
                               if old_content[k] != new_content[k]),
            "unchanged": sum(old_content[k] == new_content[k] for k in old.keys() & new.keys()),
        },
        "sections_equal": {k: encode(left[k]) == encode(right[k]) for k in SECTIONS},
        "interpretation": "Record matching uses declared evidence_id; equality is content equality only.",
    }


def info(lock_path=None, package_path=None):
    result = {
        "scope": SCOPE, "name": NAME, "version": VERSION,
        "python_required": ">=3.11", "transport": "newline-delimited JSON-RPC 2.0 on stdio",
        "protocol_versions": list(PROTOCOLS),
        "supported_format": "rea-evidence-bundle-unversioned",
        "repository_rea_pin_snapshot": PINNED_REA,
        "pin_snapshot_source": "vendor/rea/manifest.json observed 2026-11-19; not a live lock read",
        "lock": None, "package": None,
        "package_presence": "not inspected; supply package_path to inspect one metadata file",
        "limits": {"file_bytes": MAX_FILE_BYTES, "request_line_bytes": MAX_LINE_BYTES,
                   "output_line_bytes": MAX_OUTPUT_BYTES, "json_nodes": MAX_NODES,
                   "json_depth": MAX_DEPTH, "records": MAX_RECORDS, "listed_items": MAX_ITEMS},
    }
    for label, path, field in (("lock", lock_path, "package"),
                               ("package", package_path, "name")):
        if path is None:
            continue
        value, identity = read_json(path)
        if (not isinstance(value, dict) or value.get(field) != "rea-agents"
                or not short_text(value.get("version"))):
            fail("unsupported_format", "Expected rea-agents lock or package metadata.")
        result[label] = {"file": identity, "declared_name": "rea-agents",
                         "declared_version": value["version"]}
    if package_path is not None:
        result["package_presence"] = "selected metadata file exists; package completeness and authenticity unverified"
    if result["package"] and result["lock"]:
        result["package_version_matches_lock"] = (
            result["package"]["declared_version"] == result["lock"]["declared_version"])
    return result


def prepare(verify=False):
    try:
        return runtime.prepare(verify=verify)
    except runtime.RuntimeError as exc:
        fail(exc.code, str(exc))


def official(command, paths):
    # Bound bytes and JSON structure, but leave official record validation to REA.
    selected = [read_json(path, with_bytes=True) for path in paths]
    for value, _identity, _data in selected:
        if (isinstance(value, dict) and isinstance(value.get("records"), list)
                and len(value["records"]) > MAX_RECORDS):
            fail("input_limit", "Record count exceeds review limit.")
    try:
        return runtime.execute(command, selected, parse_json)
    except runtime.RuntimeError as exc:
        fail(exc.code, str(exc))


def rea_import(path):
    return official("evidence-import", [path])


def rea_compare(first, second):
    return official("compare", [first, second])


SPECS = {
    "review_info": ("Offline reviewer identity, limits and optional explicit REA metadata.",
                    {"lock_path": {"type": "string"}, "package_path": {"type": "string"}}, []),
    "review_summary": ("Summarize one explicitly selected local REA export.",
                       {"path": {"type": "string"}}, ["path"]),
    "review_compare": ("Compare two local export files; content comparison only.",
                       {"first": {"type": "string"}, "second": {"type": "string"}},
                       ["first", "second"]),
    "review_rea_import": ("Validate selected local evidence with pinned official REA; no session retained.",
                          {"path": {"type": "string"}}, ["path"]),
    "review_rea_compare": ("Compare selected local evidence with pinned official REA.",
                           {"first": {"type": "string"}, "second": {"type": "string"}},
                           ["first", "second"]),
}
FUNCTIONS = {"review_info": info, "review_summary": summary, "review_compare": compare,
             "review_rea_import": rea_import, "review_rea_compare": rea_compare}


class RpcError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message


def rpc_error(code, message):
    raise RpcError(code, message)


class Server:
    def __init__(self):
        self.initialized = False

    def dispatch(self, method, params):
        if method == "initialize":
            if (not short_text(params.get("protocolVersion"))
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(params.get("clientInfo"), dict)
                    or not short_text(params["clientInfo"].get("name"))
                    or not short_text(params["clientInfo"].get("version"))):
                rpc_error(-32602, "Invalid initialize parameters.")
            version = params["protocolVersion"]
            self.initialized = True
            return {"protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": NAME, "version": VERSION},
                    "instructions": "Offline content review only; paths must be explicit local ordinary files."}
        if method == "ping":
            return {}
        if method not in ("tools/list", "tools/call"):
            rpc_error(-32601, "Method not found.")
        if not self.initialized:
            rpc_error(-32002, "Initialize the reviewer first.")
        if method == "tools/list":
            if params.get("cursor") is not None:
                rpc_error(-32602, "Pagination cursors are unsupported.")
            return {"tools": [
                {"name": name, "description": description,
                 "inputSchema": {"type": "object", "properties": properties,
                                 "required": required, "additionalProperties": False},
                 "annotations": {"readOnlyHint": True, "destructiveHint": False,
                                 "openWorldHint": False}}
                for name, (description, properties, required) in SPECS.items()]}
        name = params.get("name")
        if not isinstance(name, str) or name not in SPECS:
            rpc_error(-32602, "Unknown review tool.")
        args = params.get("arguments", {})
        _, properties, required = SPECS[name]
        if (not isinstance(args, dict) or set(args) - set(properties)
                or any(k not in args for k in required)
                or any(not isinstance(v, str) for v in args.values())):
            rpc_error(-32602, "Invalid review tool arguments.")
        try:
            result = FUNCTIONS[name](**args)
            is_error = "error" in result
        except ReviewError as exc:
            result, is_error = error_payload(exc), True
        return {"content": [{"type": "text", "text": encode(result)}],
                "structuredContent": result, "isError": is_error}

    def handle(self, request):
        if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
                or not isinstance(request.get("method"), str)
                or ("id" in request and request["id"] is not None
                    and type(request["id"]) not in (str, int))
                or "result" in request or "error" in request):
            return rpc_failure(None, -32600, "Invalid Request.")
        request_id = request.get("id")
        notification = "id" not in request
        try:
            params = request.get("params", {})
            if not isinstance(params, dict):
                rpc_error(-32602, "Expected object parameters.")
            if notification:
                # Notifications, including initialized/cancelled, never invoke tools.
                return None
            result = self.dispatch(request["method"], params)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except RpcError as exc:
            return None if notification else rpc_failure(request_id, exc.code, exc.message)


def error_payload(exc):
    return {"scope": SCOPE, "error": {"code": exc.code, "message": str(exc)}}


def rpc_failure(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def emit(value, output):
    line = encode(value).encode("ascii")
    if len(line) + 1 > MAX_OUTPUT_BYTES:
        if isinstance(value, dict) and value.get("jsonrpc") == "2.0":
            failure = rpc_failure(value.get("id"), -32603, "Response exceeds output limit.")
        else:
            failure = error_payload(ReviewError("output_limit", "Response exceeds output limit."))
        line = encode(failure).encode("ascii")
    output.write(line + b"\n")
    output.flush()


def serve(input_stream=None, output_stream=None, *, server=None):
    source = input_stream if input_stream is not None else sys.stdin.buffer
    output = output_stream if output_stream is not None else sys.stdout.buffer
    if server is None:
        server = Server()
    while True:
        line = source.readline(MAX_LINE_BYTES + 1)
        if not line:
            break
        if len(line) > MAX_LINE_BYTES:
            while not line.endswith(b"\n"):
                line = source.readline(MAX_LINE_BYTES + 1)
                if not line:
                    break
            emit(rpc_failure(None, -32600, "Request line exceeds input limit."), output)
            continue
        try:
            request = parse_json(line.decode("utf-8"))
        except (ReviewError, UnicodeError):
            emit(rpc_failure(None, -32700, "Parse error."), output)
            continue
        response = server.handle(request)
        if response is not None:
            emit(response, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("mcp", help="Serve newline JSON-RPC on stdio.")
    preparation = commands.add_parser("prepare", help="Prepare shared EVIDENCE REVIEW runtime (CLI only).")
    preparation.add_argument("--verify", action="store_true",
                             help="Deep recheck the exact selected Node and complete REA package.")
    about = commands.add_parser("info", help="Offline reviewer identity and optional metadata.")
    about.add_argument("--lock-path", help="Explicit rea-agents lock JSON file.")
    about.add_argument("--package-path", help="Explicit rea-agents package.json file.")
    one = commands.add_parser("summary")
    one.add_argument("path")
    two = commands.add_parser("compare")
    two.add_argument("first")
    two.add_argument("second")
    official_one = commands.add_parser("rea-import")
    official_one.add_argument("path")
    official_two = commands.add_parser("rea-compare")
    official_two.add_argument("first")
    official_two.add_argument("second")
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    if command == "mcp":
        serve()
        return 0
    try:
        result = {"info": info, "summary": summary, "compare": compare,
                  "prepare": prepare, "rea-import": rea_import,
                  "rea-compare": rea_compare}[command](**args)
        code = 2 if "error" in result else 0
    except ReviewError as exc:
        result, code = error_payload(exc), 2
    emit(result, sys.stdout.buffer)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
