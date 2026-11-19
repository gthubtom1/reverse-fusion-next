"""Read literal release metadata from a local APK's compiled AndroidManifest.xml."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from struct import Struct, unpack_from
import sys
from zipfile import BadZipFile, ZipFile
import zlib


_CHUNK = Struct("<HHI")
_ATTRIBUTE = Struct("<IIIHBBI")
_NO_INDEX = 0xFFFFFFFF
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_ANDROID = "http://schemas.android.com/apk/res/android"
_PERMISSION_TAGS = {"uses-permission", "uses-permission-sdk-23", "uses-permission-sdk-m"}


class ApkManifestError(ValueError):
    """A readable failure with a stable code for callers."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _invalid(message):
    return ApkManifestError("invalid_manifest", message)


def _chunk(data, offset):
    if len(data) - offset < _CHUNK.size:
        raise _invalid("truncated Android XML chunk header")
    kind, header, size = _CHUNK.unpack_from(data, offset)
    if not _CHUNK.size <= header <= size <= len(data) - offset or (header | size) % 4:
        raise _invalid("invalid Android XML chunk size")
    return kind, header, size


class _StringPool:
    def __init__(self, data, header):
        if header < 28:
            raise _invalid("truncated Android XML string pool")
        count, styles, flags, start, style_start = unpack_from("<5I", data, 8)
        end = style_start or len(data)
        if not header + 4 * (count + styles) <= start <= end <= len(data):
            raise _invalid("invalid Android XML string pool offsets")
        if bool(styles) != bool(style_start):
            raise _invalid("invalid Android XML style pool offset")
        self.data = data
        self.offsets = header
        self.count = count
        self.start = start
        self.end = end
        self.utf8 = bool(flags & 0x100)
        self.decoded = {}

    def _length(self, cursor):
        width = 1 if self.utf8 else 2
        if cursor + width > self.end:
            raise _invalid("truncated Android XML string length")
        length = int.from_bytes(self.data[cursor:cursor + width], "little")
        cursor += width
        bits = 8 * width - 1
        if length >> bits:
            if cursor + width > self.end:
                raise _invalid("truncated Android XML string length")
            low = int.from_bytes(self.data[cursor:cursor + width], "little")
            length = ((length & ((1 << bits) - 1)) << (bits + 1)) | low
            cursor += width
        return length, cursor

    def get(self, index):
        if index == _NO_INDEX:
            return None
        if index >= self.count:
            raise _invalid("invalid Android XML string index")
        if index in self.decoded:
            return self.decoded[index]

        offset, = unpack_from("<I", self.data, self.offsets + 4 * index)
        units, cursor = self._length(self.start + offset)
        width = 1 if self.utf8 else 2
        length = units * width
        if self.utf8:
            length, cursor = self._length(cursor)
        end = cursor + length
        if end + width > self.end or any(self.data[end:end + width]):
            raise _invalid("unterminated Android XML string")
        raw = bytes(self.data[cursor:end])
        if self.utf8:
            # Android's UTF-8 pool can encode supplementary characters as surrogate pairs.
            utf16 = raw.decode("utf-8", "surrogatepass").encode("utf-16-le", "surrogatepass")
            if len(utf16) // 2 != units:
                raise _invalid("inconsistent Android XML string length")
            raw = utf16
        value = raw.decode("utf-16-le")
        self.decoded[index] = value
        return value


def _attributes(node, header, pool):
    start, width, count = unpack_from("<HHH", node, header + 8)
    if start < 20 or width < _ATTRIBUTE.size or header + start + width * count > len(node):
        raise _invalid("invalid Android XML attribute list")
    attributes = {}
    for index in range(count):
        ns, name, _, size, reserved, kind, value = _ATTRIBUTE.unpack_from(node, header + start + width * index)
        key = (pool.get(ns), pool.get(name))
        if not key[1] or key in attributes or size != 8 or reserved:
            raise _invalid("invalid or duplicate Android XML attribute")
        attributes[key] = (kind, value)
    return attributes


def _literal(attributes, key, pool, types, *, required=False):
    entry = attributes.get(key)
    if entry is None:
        if required:
            raise _invalid(f"missing {key[1]} attribute")
        return None
    kind, value = entry
    if kind not in types:
        raise ApkManifestError("unsupported_manifest", f"{key[1]} requires a literal manifest value")
    if kind == 0x03:
        value = pool.get(value)
        if value is None or (required and not value):
            raise _invalid(f"empty {key[1]} attribute")
    return value


def _release_metadata(manifest):
    data = memoryview(manifest)
    if manifest[:4] != b"\x03\x00\x08\x00":
        raise _invalid("expected a compiled binary AndroidManifest.xml")
    _, _, size = _chunk(data, 0)
    if size != len(data):
        raise _invalid("binary AndroidManifest.xml size differs from its header")

    kind, header, size = _chunk(data, 8)
    if kind != 0x0001:
        raise _invalid("missing Android XML string pool")
    pool = _StringPool(data[8:8 + size], header)
    offset = 8 + size
    if offset < len(data):
        kind, header, size = _chunk(data, offset)
        if kind == 0x0180:  # Optional resource ID map.
            offset += size

    root = None
    elements = []
    namespaces = []
    permissions = {}
    while offset < len(data):
        kind, header, size = _chunk(data, offset)
        node = data[offset:offset + size]
        offset += size
        if header < 16 or len(node) - header < 8:
            raise _invalid("truncated Android XML node")
        if kind == 0x0104:  # Character data.
            if not elements or len(node) - header < 12:
                raise _invalid("misplaced or truncated Android XML character data")
            continue
        ns, name = unpack_from("<II", node, header)
        key = (pool.get(ns), pool.get(name))
        if kind == 0x0100:
            namespaces.append(key)
        elif kind == 0x0101:
            if not namespaces or namespaces.pop() != key:
                raise _invalid("unmatched Android XML namespace")
        elif kind == 0x0102:
            if not key[1] or len(node) - header < 20:
                raise _invalid("invalid Android XML start element")
            attributes = _attributes(node, header, pool)
            if not elements:
                if root is not None or key != (None, "manifest"):
                    raise _invalid("expected one unqualified manifest root element")
                root = attributes
            elif len(elements) == 1 and key[0] is None and key[1] in _PERMISSION_TAGS:
                value = _literal(attributes, (_ANDROID, "name"), pool, (0x03,), required=True)
                permissions[value] = None
            elements.append(key)
        elif kind == 0x0103:
            if not elements or elements.pop() != key:
                raise _invalid("unmatched Android XML end element")
        else:
            raise ApkManifestError("unsupported_manifest", f"unsupported Android XML node 0x{kind:04x}")

    if root is None or elements or namespaces:
        raise _invalid("incomplete Android XML document")
    return {
        "package_name": _literal(root, (None, "package"), pool, (0x03,), required=True),
        "version_code": _literal(root, (_ANDROID, "versionCode"), pool, (0x10, 0x11)),
        "version_code_major": _literal(root, (_ANDROID, "versionCodeMajor"), pool, (0x10, 0x11)),
        "version_name": _literal(root, (_ANDROID, "versionName"), pool, (0x03,)),
        "permissions": list(permissions),
    }


def inspect_apk(path):
    """Return release fields and the SHA-256 and size of the exact APK file.

    Omitted version attributes are None. Permissions are unique, in manifest order.
    Raises ApkManifestError for unreadable or unsupported input.
    """
    try:
        with Path(path).open("rb") as stream:
            before = os.fstat(stream.fileno())
            with ZipFile(stream) as archive:
                entries = [entry for entry in archive.infolist() if entry.filename == "AndroidManifest.xml"]
                if len(entries) != 1:
                    raise ApkManifestError("invalid_apk", "expected exactly one root AndroidManifest.xml")
                entry = entries[0]
                if entry.file_size > _MAX_MANIFEST_BYTES:
                    raise ApkManifestError("unsupported_manifest", "compiled manifest exceeds 4 MiB")
                with archive.open(entry) as member:
                    manifest = member.read(_MAX_MANIFEST_BYTES + 1)
                if len(manifest) != entry.file_size:
                    raise ApkManifestError("invalid_apk", "manifest size differs from the ZIP directory")
            result = _release_metadata(manifest)
            stream.seek(0)
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            after = os.fstat(stream.fileno())
    except (BadZipFile, EOFError, NotImplementedError, RuntimeError, zlib.error) as exc:
        raise ApkManifestError("invalid_apk", f"unreadable APK archive: {exc}") from exc
    except UnicodeError as exc:
        raise _invalid("invalid Android XML string encoding") from exc
    except OSError as exc:
        raise ApkManifestError("input_error", str(exc)) from exc
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ApkManifestError("input_changed", "APK changed during inspection")
    result["input"] = {"sha256": digest, "size_bytes": after.st_size}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect_apk(args.apk)))
    except ApkManifestError as exc:
        print(json.dumps({"error": exc.code, "message": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
