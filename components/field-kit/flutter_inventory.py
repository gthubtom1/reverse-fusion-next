"""Read package class inventory from the selected library using a bounded local reader."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile

from materials import ordinary

HOME = Path(__file__).resolve().parent / "flutter-inventory"
READER_SHA256 = "000dd83154d6d7b5a8274fa08bfcf69693bdec7676d7720f423792eee6fcb10d"


def observe(path, query=""):
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError("Expected a short class or package name")
    _, raw, identity = ordinary(path)
    if len(raw) < 64 or raw[:6] != b"\x7fELF\x02\x01" or raw[18:20] != b"\xb7\x00":
        raise ValueError("This inventory reads 64-bit little-endian ARM64 ELF libraries")
    reader = HOME / "inventory.exe"
    if sha256(reader.read_bytes()).hexdigest() != READER_SHA256:
        raise ValueError("Installed Flutter inventory reader differs from the release")
    result = {"basis":"owned-flutter-package-inventory", "file":identity, "runtime":"unobserved",
              "reader_sha256":READER_SHA256, "architecture":"arm64", "bits":64}
    with tempfile.TemporaryDirectory(prefix="rf-class-list-") as directory:
        source = Path(directory) / "app.so"
        source.write_bytes(raw)
        try:
            proc = subprocess.run([str(reader), str(source)], cwd=directory,
                                  env={"SystemRoot":os.environ["SystemRoot"],"GOMEMLIMIT":"112MiB"},
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  timeout=12, creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            return {**result, "status":"time_limit", "classes":[], "complete":False}
    if proc.returncode:
        return {**result,"status":"unresolved_snapshot","classes":[],"complete":False}
    rows = json.loads(proc.stdout)
    rows = [r for r in rows if query.casefold() in (r["class_name"]+" "+r["library_uri"]).casefold()]
    return {**result,"status":"observed","classes":rows[:64],"matching_rows":len(rows),
            "truncated":len(rows)>64, "scope":"package classes with resolved class-to-library references"}
