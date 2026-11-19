"""Shared maintenance EVIDENCE REVIEW runtime; never a production bootstrap.

Only prepare may acquire archives. Warm checks read small manifests/receipts
and stat fixed anchors; they deliberately say nothing about non-anchor files.
First prepare and explicit prepare --verify authenticate the complete package.
Receipts are local preparation records, not official REA qualification.
"""
import base64
from contextlib import contextmanager
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import tempfile
import threading
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "four-host-evidence-review-v1"
STATE = ROOT / "state" / "evidence-review"
TIMEOUT = 30
OUTPUT_LIMIT = 64 * 1024  # Each pipe, including worst-case JSON escaping and MCP duplication.
RECEIPT_LIMIT = 16 * 1024
FIXTURE = Path("evidence/next/s2/native-bundle.json")
PACKAGE_ANCHORS = (
    "package.json", "scripts/rea.mjs",
    "scripts/lib/cli-process-environment.mjs", "scripts/lib/runtime-admission.mjs",
    "dist/cli-runtime/cliBuiltinArguments.js", "dist/cli-runtime/cli.js",
    "dist/cli-runtime/cliOutput.js", "dist/cli-runtime/cliResultOutput.js",
)
WARM_CHECK = {
    "kind": "fixed-anchor-metadata-only",
    "whole_package_verified_now": False,
    "limits": "Non-anchor changes and metadata-preserving edits are not checked on warm reads.",
    "deep_recheck": "next-review.py prepare --verify",
}


class RuntimeError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def reject(code, message):
    raise RuntimeError(code, message)


def ordinary(path, *, file=True):
    metadata = Path(path).lstat()
    if (stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        reject("runtime_changed", "Runtime links/reparse points are unsupported; run prepare.")
    if not (stat.S_ISREG(metadata.st_mode) if file else stat.S_ISDIR(metadata.st_mode)):
        reject("runtime_changed", "Runtime file is not ordinary; run prepare.")
    return metadata


def fingerprint(path, *, parents=True):
    """Cheap change detection of locally authenticated ordinary files."""
    path = Path(path)
    if parents:
        for parent in reversed(path.parents):
            ordinary(parent, file=False)
    metadata = ordinary(path)
    return [metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns, metadata.st_ino]


def hash_stream(stream, algorithm="sha256"):
    result = hashlib.new(algorithm)
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def digest(path, algorithm="sha256", *, parents=True):
    fingerprint(path, parents=parents)
    with Path(path).open("rb") as stream:
        return hash_stream(stream, algorithm)


def metadata(path):
    fingerprint(path)
    with Path(path).open("rb") as stream:
        data = stream.read(RECEIPT_LIMIT + 1)
    if len(data) > RECEIPT_LIMIT:
        reject("runtime_changed", "Profile metadata exceeds its bound.")
    return json.loads(data), hashlib.sha256(data).hexdigest()


def load(path):
    return metadata(path)[0]


def pins():
    node = ROOT / "vendor/node/manifest.json"
    rea = ROOT / "vendor/rea/manifest.json"
    node_pin, node_sha = metadata(node)
    rea_pin, rea_sha = metadata(rea)
    if (not isinstance(node_pin, dict) or not isinstance(rea_pin, dict)
            or rea_pin.get("package") != "rea-agents" or rea_pin.get("version") != "6.9.0"
            or rea_pin.get("entry") != "package/scripts/rea.mjs"):
        reject("pin_error", "This profile requires the locked official REA 6.9.0 entry.")
    relative = Path(node_pin["entry"])
    if (relative.drive or relative.root or ".." in relative.parts
            or ":" in node_pin["entry"] or "\\" in node_pin["entry"]
            or relative.name != "node.exe"):
        reject("pin_error", "Invalid locked Node entry.")
    return node_pin, rea_pin, [node_sha, rea_sha]


def expected_paths(node_pin, identities, locations):
    """Paths come from code + manifests; receipt selectors are two closed enums."""
    if (not isinstance(locations, dict) or set(locations) != {"node", "package"}
            or any(value not in ("checkout", "prepared") for value in locations.values())):
        reject("runtime_changed", "Invalid runtime location selection; run prepare.")
    generation = hashlib.sha256("".join(identities).encode("ascii")).hexdigest()
    prepared = STATE / "prepared" / generation
    node = (ROOT / "vendor/node" / node_pin["entry"]
            if locations["node"] == "checkout" else prepared / "node.exe")
    package = ROOT / "vendor/rea/package" if locations["package"] == "checkout" else prepared / "package"
    return {"node": str(node), "package": str(package), "entry": str(package / "scripts/rea.mjs")}


def anchors(paths):
    package = Path(paths["package"])
    return {"node": Path(paths["node"]),
            **{name: package / name for name in PACKAGE_ANCHORS}}


def checked():
    """Never repair, download, write receipts or import bootstrap during reads."""
    try:
        receipt = load(STATE / "runtime.json")
        node_pin, rea, identities = pins()
        if (receipt["schema"] != 2 or receipt["profile"] != PROFILE
                or receipt["root"] != str(ROOT) or receipt["pins"] != identities
                or receipt["rea_version"] != rea["version"]
                or receipt["smoke"]["status"] != "ok"):
            reject("runtime_changed", "Profile identity changed; run prepare.")
        paths = expected_paths(node_pin, identities, receipt["locations"])
        if any(receipt[name] != value for name, value in paths.items()):
            reject("runtime_changed", "Receipt paths differ from the exact expected runtime paths.")
        fixed = anchors(paths)
        if not isinstance(receipt["anchors"], dict) or set(receipt["anchors"]) != set(fixed):
            reject("runtime_changed", "Invalid fixed anchor identities; run prepare.")
        parents = set()
        for name, selected in fixed.items():
            for parent in selected.parents:
                if parent not in parents:
                    ordinary(parent, file=False)
                    parents.add(parent)
            if fingerprint(selected, parents=False) != receipt["anchors"][name]:
                reject("runtime_changed", "Prepared runtime changed; run prepare.")
        receipt["warm_check"] = WARM_CHECK
        return receipt
    except RuntimeError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        reject("not_prepared", "Shared EVIDENCE REVIEW runtime is absent or stale; run next-review.py prepare.")


def bootstrap_primitives():
    # Load just the safe bootstrap helpers, not rea_enhanced package initialization.
    # Their relative storage import is supplied by the normal checkout package.
    import sys
    root = str(ROOT)
    sys.path.insert(0, root)
    try:
        from rea_enhanced import bootstrap
        return bootstrap
    finally:
        sys.path.remove(root)


def acquire(helpers, pin, candidates, destination, *, node=False):
    algorithm, expected = ("sha256", pin["sha256"]) if node else (
        pin["integrity"].split("-", 1)[0],
        base64.b64decode(pin["integrity"].split("-", 1)[1], validate=True).hex())
    for path in candidates:
        if path.is_file() and digest(path, algorithm) == expected:
            return path
    return helpers.acquire(pin["url"] if node else pin["source"], destination,
                           algorithm=algorithm, expected=expected)


@contextmanager
def preparation_lock():
    """Repository-profile OS lock; the file stays, ownership dies with the process."""
    STATE.mkdir(parents=True, exist_ok=True)
    lock_path = STATE / "prepare.lock"
    if lock_path.exists():
        fingerprint(lock_path)
    with lock_path.open("a+b") as lock:
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            reject("prepare_busy", "Another preparation holds the repository profile lock; retry after it exits.")
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def package_members(archive):
    """Validate names lexically once, before writing into a fresh staging tree."""
    entries = archive.getmembers()
    seen = set()
    devices = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
               *(f"{prefix}{number}" for prefix in ("COM", "LPT") for number in "123456789¹²³")}
    for entry in entries:
        name = entry.name.rstrip("/") if entry.isdir() else entry.name
        parts = name.split("/")
        if (parts[0] != "package" or "\\" in name or ":" in name
                or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in parts)
                or any(part.split(".", 1)[0].rstrip().upper() in devices
                       or any(ord(char) < 32 or char in '<>"|?*' for char in part)
                       for part in parts)
                or (entry.isfile() and len(parts) < 2)
                or not (entry.isfile() or entry.isdir())
                or name.casefold() in seen):
            reject("archive_error", "Unsafe or ambiguous official package member.")
        seen.add(name.casefold())
    return entries


def long_local_path(path):
    """Use the Windows extended form only for already selected absolute disk paths."""
    path = Path(path)
    if os.name == "nt" and path.is_absolute() and len(path.drive) == 2 and path.drive.endswith(":"):
        return Path("\\\\?\\" + str(path))
    return path


def extract_package(archive_path, staging):
    """Fresh, private destination + validated relative names; no per-member resolve."""
    staging = long_local_path(staging)
    with tarfile.open(archive_path) as archive:
        for entry in package_members(archive):
            target = staging.joinpath(*entry.name.rstrip("/").split("/"))
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(entry) as incoming, target.open("xb") as output:
                    shutil.copyfileobj(incoming, output)


def verify_package(package, archive_path):
    """Deep hash + exact file-set check, including extras and reparse points."""
    package = long_local_path(package)
    fingerprint(package / "scripts/rea.mjs")
    with tarfile.open(archive_path) as archive:
        entries = package_members(archive)
        expected = {e.name[len("package/"):] for e in entries if e.isfile()}
        actual = set()
        def walk_error(error):
            raise error
        for directory, dirs, files in os.walk(package, followlinks=False, onerror=walk_error):
            for name in dirs:
                ordinary(Path(directory) / name, file=False)
            for name in files:
                path = Path(directory) / name
                ordinary(path)
                actual.add(path.relative_to(package).as_posix())
        if actual != expected:
            reject("verification_failed", "Official package has missing or extra files.")
        for entry in entries:
            if entry.isfile():
                path = package.joinpath(*entry.name.split("/")[1:])
                with archive.extractfile(entry) as incoming:
                    expected_sha = hash_stream(incoming)
                if digest(path, parents=False) != expected_sha:
                    reject("verification_failed", "Official package file differs: " + entry.name[:200])
    return len(expected)


def smoke_import(receipt):
    spec = importlib.util.spec_from_file_location("review_smoke", ROOT / "scripts/next-review.py")
    reviewer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reviewer)
    selected = reviewer.read_json(str(ROOT / FIXTURE), with_bytes=True)
    result = invoke(receipt, "evidence-import", [selected], reviewer.parse_json)
    payload = result["official"]["payload"]
    if ("error" in result or not isinstance(payload, dict)
            or payload.get("imported") != len(selected[0]["records"])):
        reject("smoke_failed", "Official REA did not import the benign s2 fixture.")
    return {"status": "ok", "file": selected[1], "official_payload": payload}


def save_receipt(receipt):
    data = json.dumps(receipt, separators=(",", ":")).encode("utf-8")
    if len(data) > RECEIPT_LIMIT:
        reject("prepare_failed", "Profile receipt exceeds its small fixed bound.")
    with tempfile.NamedTemporaryFile(dir=STATE, prefix="receipt-", delete=False) as output:
        temporary = Path(output.name)
        output.write(data)
    try:
        os.replace(temporary, STATE / "runtime.json")
    finally:
        temporary.unlink(missing_ok=True)


def ready(receipt, *, deep):
    return {"profile": PROFILE, "status": "ready", "cached": not deep,
            "verified_now": deep, "warm_check": WARM_CHECK,
            "receipt": str(STATE / "runtime.json"), "smoke": receipt["smoke"]}


def prepare(verify=False):
    """First prepare verifies everything; --verify rechecks the selected runtime."""
    try:
        try:
            existing = checked()
        except RuntimeError:
            if verify:
                raise  # Explicit verification never silently selects a replacement.
            existing = None
        if existing and not verify:
            return ready(existing, deep=False)
        if platform.system() != "Windows" or platform.machine().lower() not in ("amd64", "x86_64"):
            reject("platform", "Preparation requires the locked Windows x64 assets.")
        with preparation_lock():
            # Recheck after acquiring ownership in case a peer just finished.
            if not verify:
                try:
                    return ready(checked(), deep=False)
                except RuntimeError:
                    pass
            node_pin, rea_pin, identities = pins()
            helpers = bootstrap_primitives()
            node_archive = acquire(helpers, node_pin, [
                ROOT / "state/downloads/node.zip", ROOT / "vendor/node/node-windows-x64.zip",
                STATE / "downloads/node.zip"], STATE / "downloads/node.zip", node=True)
            rea_archive = acquire(helpers, rea_pin, [
                ROOT / "state/downloads/rea.tgz", ROOT / "vendor/rea/rea-agents-6.9.0.tgz",
                STATE / "downloads/rea.tgz"], STATE / "downloads/rea.tgz")
            with zipfile.ZipFile(node_archive) as archive:
                with archive.open(node_pin["entry"]) as incoming:
                    expected_node = hash_stream(incoming)
            if verify:
                receipt = checked()
                if digest(receipt["node"]) != expected_node:
                    reject("verification_failed", "Selected Node differs from its pinned archive.")
                count = verify_package(Path(receipt["package"]), rea_archive)
            else:
                locations = {"node": "checkout", "package": "checkout"}
                paths = expected_paths(node_pin, identities, locations)
                try:
                    valid_node = digest(paths["node"]) == expected_node
                except (OSError, RuntimeError):
                    valid_node = False
                try:
                    count = verify_package(Path(paths["package"]), rea_archive)
                    valid_package = True
                except (OSError, RuntimeError):
                    valid_package = False
                locations = {"node": "checkout" if valid_node else "prepared",
                             "package": "checkout" if valid_package else "prepared"}
                paths = expected_paths(node_pin, identities, locations)
                # Only the pinned node.exe is needed; npm and the Node tree stay archived.
                prepared_smoke = None
                if not valid_node or not valid_package:
                    prepared = Path(expected_paths(node_pin, identities, {
                        "node": "prepared", "package": "prepared"})["node"]).parent
                    prepared.mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory(prefix="preparing-", dir=long_local_path(STATE)) as temporary:
                        staging = Path(temporary)
                        staged = dict(paths)
                        publish = []
                        if not valid_node:
                            if not Path(paths["node"]).exists():
                                with zipfile.ZipFile(node_archive) as archive:
                                    with archive.open(node_pin["entry"]) as incoming, \
                                            (staging / "node.exe").open("xb") as output:
                                        shutil.copyfileobj(incoming, output)
                                staged["node"] = str(staging / "node.exe")
                                publish.append((staging / "node.exe", Path(paths["node"])))
                            if digest(staged["node"]) != expected_node:
                                reject("verification_failed", "Prepared Node differs from its archive.")
                        if not valid_package:
                            if not Path(paths["package"]).exists():
                                extract_package(rea_archive, staging)
                                staged["package"] = str(staging / "package")
                                staged["entry"] = str(staging / "package/scripts/rea.mjs")
                                publish.append((staging / "package", Path(paths["package"])))
                            count = verify_package(Path(staged["package"]), rea_archive)
                        # Publish new components only after complete authentication
                        # and a real benign import; a crash leaves reusable components.
                        prepared_smoke = smoke_import({**staged, "rea_version": rea_pin["version"]})
                        for source, destination in publish:
                            os.replace(source, destination)
                receipt = {"schema": 2, "profile": PROFILE, "root": str(ROOT),
                           "pins": identities, "rea_version": rea_pin["version"],
                           "locations": locations, **paths}
            receipt["anchors"] = {name: fingerprint(path) for name, path in anchors(receipt).items()}
            receipt["deep_verification"] = {"kind": "locked-archive-full-package-and-extra-file-check",
                                            "scope": "Last successful preparation only; not current warm proof.",
                                            "package_files": count}
            receipt["smoke"] = smoke_import(receipt) if verify else (prepared_smoke or smoke_import(receipt))
            receipt.pop("warm_check", None)
            save_receipt(receipt)
            return ready(receipt, deep=True)
    except RuntimeError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError,
            http.client.HTTPException, tarfile.TarError, zipfile.BadZipFile) as exc:
        reject("prepare_failed", f"Profile preparation failed: {exc}")


def run(command, cwd):
    """Drain both pipes with hard memory bounds; kill and reap on limit/timeout."""
    # Do not inherit NODE_OPTIONS, REA/provider settings, proxy or user config.
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}}
    env.update({"HOME": str(cwd), "USERPROFILE": str(cwd), "CI": "1",
                "DO_NOT_TRACK": "1", "NO_COLOR": "1"})
    buffers = [bytearray(), bytearray()]
    exceeded = threading.Event()
    try:
        with subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
            def drain(pipe, target):
                with pipe:
                    while chunk := pipe.read(8192):
                        remaining = OUTPUT_LIMIT - len(target)
                        target.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            exceeded.set()
                            process.kill()
            threads = [threading.Thread(target=drain, args=(pipe, target), daemon=True)
                       for pipe, target in zip((process.stdout, process.stderr), buffers)]
            for thread in threads:
                thread.start()
            timed_out = False
            try:
                process.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait()
            finally:
                for thread in threads:
                    thread.join()
            if exceeded.is_set():
                reject("output_limit", "Official CLI exceeded the bounded output budget.")
            if timed_out:
                reject("timeout", "Official CLI exceeded the review timeout.")
            return process.returncode, bytes(buffers[0]), bytes(buffers[1])
    except OSError:
        reject("execution_error", "Prepared official CLI failed to start.")


def invoke(receipt, command, selected, parser):
    if command not in ("evidence-import", "compare") or len(selected) != (
            1 if command == "evidence-import" else 2):
        reject("invalid_command", "Only fixed evidence-import and compare operations are supported.")
    with tempfile.TemporaryDirectory(prefix="read-", dir=STATE) as temporary:
        cwd = Path(temporary).resolve()
        paths = []
        for number, (_value, _identity, data) in enumerate(selected):
            path = cwd / f"selected-{number}.json"
            path.write_bytes(data)
            paths.append(str(path))
        argv = [receipt["node"], receipt["entry"], command, *paths, "--format", "json"]
        code, stdout, stderr = run(argv, cwd)
        decode_error = False
        try:
            payload = parser(stdout.decode("utf-8-sig"))
        except (ValueError, UnicodeError):
            payload = None
            decode_error = True
        result = {
            "profile": PROFILE,
            "review": {"kind": "owned-read-only-official-cli-adapter",
                       "runtime_check": WARM_CHECK,
                       "inputs": [identity for _, identity, _ in selected],
                       "input_mode": "byte-identical private snapshots; embedded paths stay data",
                       "behavioral_equivalence_established": False,
                       "provenance_authenticated": False},
            "official": {"implementation": "rea-agents", "version": receipt["rea_version"],
                         "command": command, "argv": argv, "exit_code": code,
                         "payload": payload, "stderr": stderr.decode("utf-8", errors="replace"),
                         "stdout_base64": base64.b64encode(stdout).decode("ascii"),
                         "stderr_base64": base64.b64encode(stderr).decode("ascii")},
        }
        if decode_error:
            result["error"] = {"code": "invalid_official_output", "message": "Official CLI returned invalid or over-complex JSON."}
        elif code != 0 or not isinstance(payload, dict) or "error" in payload:
            result["error"] = {"code": "official_error", "message": "Official REA rejected the selected evidence."}
        return result


def execute(command, selected, parser):
    return invoke(checked(), command, selected, parser)
