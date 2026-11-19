"""Observe the file identity of a local XML plist snapshot using pinned REA."""

import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from xml.etree import ElementTree


_VERSION = "6.9.0"
_PROVIDER = "rea-artifact-graph"
_MAX_INPUT = 64 * 1024
_MAX_BUNDLE = 64 * 1024
_XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
_PLIST_DOCTYPE = ('<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                  '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">')
_PLIST_VALUES = {"array", "dict", "string", "data", "date", "integer", "real", "true", "false"}
_FILENAME = re.compile(r"\w[\w. -]{0,89}\.plist", re.IGNORECASE)
_DEVICE = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])", re.IGNORECASE)
_EVIDENCE_ID = re.compile(r"ev_[0-9a-f]{64}")


class IdentityError(ValueError):
    """An adapter failure with a stable code and CLI output when available."""

    def __init__(self, code, message, *, receipt=None):
        super().__init__(message)
        self.code = code
        self.receipt = receipt
        self.partial_export = None


def _admit(raw, filename):
    if (not isinstance(filename, str) or not _FILENAME.fullmatch(filename)
            or _DEVICE.fullmatch(filename.split(".", 1)[0].rstrip())):
        raise IdentityError("invalid_filename", "Expected a simple local .plist basename.")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_INPUT:
        raise IdentityError("invalid_bytes", "Expected nonempty bytes up to 64 KiB.")

    try:
        text = raw.decode("utf-8")
        if not text.startswith(_XML_HEADER):
            raise ValueError("UTF-8 XML declaration required")
        body = text[len(_XML_HEADER):].lstrip(" \r\n\t")
        if body.startswith(_PLIST_DOCTYPE):
            body = body[len(_PLIST_DOCTYPE):]
        if "<!" in body or "<?" in body:
            raise ValueError("Unexpected XML declaration or markup")
        root = ElementTree.fromstring(body)
        if (root.tag != "plist" or root.attrib != {"version": "1.0"}
                or len(root) != 1 or root[0].tag not in _PLIST_VALUES):
            raise ValueError("Expected the XML plist envelope")
    except (ValueError, ElementTree.ParseError) as exc:
        raise IdentityError("unsupported_format", "Expected standalone UTF-8 XML plist 1.0.") from exc


def _official_json(data):
    result = json.loads(data.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected an official JSON object")
    return result


def _invoke(runtime, prefix, cwd, command, *args):
    argv = [*prefix, command, *args, "--format", "json"]
    code, stdout, stderr = runtime.run(argv, cwd)
    receipt = {"command": command, "argv": argv, "exit_code": code, "stdout": stdout, "stderr": stderr}
    if code != 0:
        raise IdentityError("official_error", f"Official REA {command} failed.", receipt=receipt)
    try:
        payload = _official_json(stdout)
    except (ValueError, RecursionError) as exc:
        raise IdentityError("invalid_official_output", f"Invalid REA {command} JSON.",
                            receipt=receipt) from exc
    if "error" in payload:
        raise IdentityError("official_error", f"Official REA {command} rejected the request.",
                            receipt=receipt)
    return payload, receipt


def _read_identity(summary, bundle_path, subject_path, sha256, size):
    """Accept the two-record, root-file-only evidence emitted by this fixed operation."""
    with bundle_path.open("rb") as stream:
        data = stream.read(_MAX_BUNDLE + 1)
    if not 0 < len(data) <= _MAX_BUNDLE:
        raise ValueError("Unexpected export size")
    if summary["evidence_bundle"] != {"path": str(bundle_path), "bytes": len(data)}:
        raise ValueError("The export receipt does not match the staged bundle")
    records = _official_json(data)["records"]
    if not isinstance(records, list) or len(records) != 2:
        raise ValueError("Expected exactly the inspection and inventory records")
    by_operation = {record["operation"]: record for record in records}
    inspection = by_operation["inspect_artifact"]
    inventory = by_operation["inventory_artifact"]
    for record in records:
        subject = record["subject"]
        if (record["provider"]["id"] != _PROVIDER
                or not _EVIDENCE_ID.fullmatch(record["evidence_id"])
                or subject["local_path"] != str(subject_path)
                or subject["digest"]["sha256"] != sha256
                or subject["format"] != "plist"):
            raise ValueError("Official evidence subject does not match the input snapshot")

    if (inspection["evidence_links"] != [inventory["evidence_id"]]
            or inspection["evidence_id"] == inventory["evidence_id"]
            or summary["summary"]["normalized_result"]["parent_evidence_id"] != inspection["evidence_id"]):
        raise ValueError("Inspection, summary and inventory identities differ")
    facts = inventory["normalized_result"]
    if (facts["coverage"] != {"scope": "root", "status": "complete"}
            or len(facts["nodes"]) != 1 or len(facts["occurrences"]) != 1 or facts["edges"] != []):
        raise ValueError("Expected a complete inventory of one root file")
    node, occurrence = facts["nodes"][0], facts["occurrences"][0]
    if (node["artifact_id"] != facts["manifest"]["root_artifact_id"]
            or node["artifact_id"] != occurrence["artifact_id"]
            or occurrence["entry_kind"] != "file" or occurrence["logical_path"] != "."
            or node["sha256"] != sha256 or node["format"] != "plist"
            or type(node["size"]) is not int or node["size"] != size):
        raise ValueError("Official file digest, format or size differs from the snapshot")
    return node, data, inspection["evidence_id"], inventory["evidence_id"]


def observe_bytes(raw, filename, runtime):
    """Return file identity and unmodified REA export/CLI bytes; retain nothing on disk.

    Pass the existing scripts/review_runtime.py module as runtime. Its checked()
    and run() errors propagate. Adapter failures raise IdentityError with a code.
    The original filename is a label; REA sees a fixed private snapshot basename.
    """
    _admit(raw, filename)
    checked = runtime.checked()
    if checked["rea_version"] != _VERSION:
        raise IdentityError("runtime_version", "Expected the checked official REA 6.9.0 runtime.")
    prefix = [checked["node"], checked["entry"]]
    sha256 = hashlib.sha256(raw).hexdigest()
    with TemporaryDirectory(prefix="rea-identity-") as temporary:
        cwd = Path(temporary).resolve()
        subject_path, bundle_path = cwd / "subject.plist", cwd / "official-bundle.json"
        subject_path.write_bytes(raw)
        summary, inspection = _invoke(runtime, prefix, cwd, "inspect-artifact", str(subject_path),
                                      "--detail", "summary", "--evidence_output", str(bundle_path))
        try:
            node, data, inspection_id, inventory_id = _read_identity(
                summary, bundle_path, subject_path, sha256, len(raw))
        except (OSError, ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
            raise IdentityError("evidence_mismatch", "Official REA root file evidence did not verify.",
                                receipt=inspection) from exc
        try:
            imported, import_receipt = _invoke(runtime, prefix, cwd, "evidence-import", str(bundle_path))
            counts = {"imported": 2, "unknowns_added": 0, "total": 2}
            if imported != counts or any(type(imported[key]) is not int for key in counts):
                raise IdentityError("import_mismatch", "Unexpected official REA import counts.",
                                    receipt=import_receipt)
        except (ValueError, OSError) as exc:
            error = exc if isinstance(exc, IdentityError) else IdentityError(
                getattr(exc, "code", "import_error"), str(exc))
            error.partial_export = {
                "bundle_bytes": data, "bundle_sha256": hashlib.sha256(data).hexdigest(),
                "inspection": inspection, "inspection_evidence_id": inspection_id,
                "inventory_evidence_id": inventory_id, "reimport_verified": False,
            }
            if error is exc:
                raise
            raise error from exc

    return {
        "kind": "owned-rea-file-identity-observation",
        "filename": filename,
        "sha256": node["sha256"],
        "format": node["format"],
        "size": node["size"],
        "official": {
            "package": "rea-agents",
            "version": _VERSION,
            "provider": _PROVIDER,
            "inspection_evidence_id": inspection_id,
            "inventory_evidence_id": inventory_id,
            "bundle_bytes": data,
            "bundle_sha256": hashlib.sha256(data).hexdigest(),
            "inspection": inspection,
            "import": {**import_receipt, "payload": imported},
        },
    }
