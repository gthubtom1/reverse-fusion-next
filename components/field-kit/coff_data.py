"""Read archival headers from a conservative subset of read-only COFF objects."""

from hashlib import sha256
import re
from struct import Struct


_FILE_HEADER = Struct("<HHIIIHH")
_SECTION_HEADER = Struct("<8sIIIIIIHHI")
_STRING_SIZE = Struct("<I")
_SYMBOL_RECORD_SIZE = 18
_ARCHITECTURES = {0x8664: "x86_64", 0x014C: "x86"}
_SECTION_NAME = re.compile(rb"[A-Za-z_.$][A-Za-z0-9_.$-]{0,7}")
_SECTION_ALIGNMENT_MASK = 0x00F00000
_READ_ONLY_INITIALIZED_DATA = 0x40000040
_EMPTY_SECTION_FLAGS = 0xE00000E0  # Read/write/execute and code/initialized/uninitialized.
_OBJECT_FLAGS = 0x0105  # 32-bit machine, line numbers stripped, relocations stripped.


def _read_layout(raw: bytes) -> dict | None:
    if len(raw) < _FILE_HEADER.size:
        return None
    machine, section_count, timestamp, symbol_offset, symbol_count, optional_size, flags = (
        _FILE_HEADER.unpack_from(raw)
    )
    if machine not in _ARCHITECTURES or not section_count:
        return None
    if optional_size or flags & ~_OBJECT_FLAGS:
        return None
    section_end = _FILE_HEADER.size + section_count * _SECTION_HEADER.size
    if section_end > len(raw):
        return None

    if symbol_offset:
        string_offset = symbol_offset + symbol_count * _SYMBOL_RECORD_SIZE
        if not section_end <= symbol_offset <= string_offset <= len(raw) - _STRING_SIZE.size:
            return None
        (string_size,) = _STRING_SIZE.unpack_from(raw, string_offset)
        if string_size < _STRING_SIZE.size or string_size != len(raw) - string_offset:
            return None
    elif symbol_count:
        return None
    data_limit = symbol_offset or len(raw)

    sections = []
    spans = []
    for offset in range(_FILE_HEADER.size, section_end, _SECTION_HEADER.size):
        (name_field, physical_size, virtual_address, raw_size, raw_pointer,
         reloc_pointer, line_pointer, reloc_count, line_count, section_flags) = (
            _SECTION_HEADER.unpack_from(raw, offset)
        )
        # Only inline section names are in scope. Symbol and string contents are opaque.
        name = name_field.rstrip(b"\0")
        if not _SECTION_NAME.fullmatch(name) or any((
            physical_size, virtual_address, reloc_pointer, line_pointer, reloc_count, line_count,
        )):
            return None
        if (section_flags & _SECTION_ALIGNMENT_MASK) == _SECTION_ALIGNMENT_MASK:
            return None  # COFF reserves the all-ones alignment value.
        section_type = section_flags & ~_SECTION_ALIGNMENT_MASK
        if raw_size:
            if section_type != _READ_ONLY_INITIALIZED_DATA:
                return None
            if name.lower().startswith((b".text", b".code", b".drectve")):
                return None
            raw_end = raw_pointer + raw_size
            if not section_end <= raw_pointer < raw_end <= data_limit:
                return None
            spans.append((raw_pointer, raw_end))
            storage = "read-only-initialized-data"
        else:
            if raw_pointer or section_type & ~_EMPTY_SECTION_FLAGS:
                return None
            storage = "empty-placeholder"
        sections.append({
            "name": name.decode("ascii"),
            "raw_size": raw_size,
            "raw_pointer": raw_pointer,
            "characteristics": hex(section_flags),
            "storage": storage,
        })

    # Walk the physical order independently of section header order. Any gaps
    # inside the container must be zero padding, and bare trailing bytes are invalid.
    if not spans:
        return None
    cursor = section_end
    for start, end in sorted(spans):
        if start < cursor or raw.count(b"\0", cursor, start) != start - cursor:
            return None
        cursor = end
    if cursor != data_limit:
        if not symbol_offset or raw.count(b"\0", cursor, data_limit) != data_limit - cursor:
            return None

    return {
        "machine": hex(machine),
        "architecture": _ARCHITECTURES[machine],
        "section_count": section_count,
        "timestamp_raw": timestamp,
        "optional_header_size": optional_size,
        "characteristics": hex(flags),
        "symbol_table_offset": symbol_offset,
        "symbol_count": symbol_count,
        "sections": sections,
    }


def observe_coff_data(raw: bytes) -> dict | None:
    """Return JSON-ready facts for a supported data-only layout, or None.

    The digest describes the input bytes. Data meaning and symbol records are
    outside the observation, which uses section declarations and container bounds.
    """
    if not isinstance(raw, bytes):
        return None
    layout = _read_layout(raw)
    if layout is None:
        return None
    return {
        "kind": "coff-data-header",
        "format": "COFF",
        "size_bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
        **layout,
        "unknowns": ["data_layout_and_meaning", "symbol_names_and_meaning"],
    }
