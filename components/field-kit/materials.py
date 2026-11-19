"""Read facts from bounded local application artifacts. Embedded paths are data."""
from collections import defaultdict
from contextlib import closing
import csv
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import sqlite3
import stat
import struct
import tempfile
from urllib.parse import urljoin
import wave
import zipfile

import apk_manifest
from coff_data import observe_coff_data


LIMIT = 16 * 1024 * 1024
TEXT_PREVIEW_CHARS = 4096
MAIL_HEADER_BYTES = 32 * 1024
MAIL_HEADER_COUNT = 128
MAIL_LINE_BYTES = 998
TEXT_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
MAIL_SEPARATOR = re.compile(rb"\r?\n\r?\n")
MAIL_FIELD_NAME = re.compile(r"[\x21-\x39\x3b-\x7e]+")


def ordinary(path):
    if not isinstance(path, str) or not path or "\0" in path or path.startswith(("//", "\\\\", "\\??\\")) or ":" in path[2:]:
        raise ValueError("Select an ordinary local file.")
    file = Path(os.path.abspath(path))
    for parent in (*reversed(file.parents), file):
        meta = parent.lstat()
        if stat.S_ISLNK(meta.st_mode) or getattr(meta, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError("The selected path contains a link or a reparse point.")
    if not stat.S_ISREG(meta.st_mode) or meta.st_size > LIMIT:
        raise ValueError("Expected an ordinary file at most 16 MiB.")
    with file.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("The selected file grew beyond its limit.")
    return file, raw, {"name":file.name,"bytes":len(raw),"sha256":sha256(raw).hexdigest()}


def zip_members(raw):
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members)>512 or sum(m.file_size for m in members)>32*1024*1024:
            raise ValueError("Archive size or member count exceeds the limit.")
        for m in members:
            name = m.filename
            if m.is_dir():
                continue
            if (name in result or name.startswith(("/", "\\")) or ".." in PurePosixPath(name).parts or "\\" in name
                    or len(name)>400 or ":" in name or m.flag_bits & 1 or m.file_size > 8*1024*1024):
                raise ValueError("Archive contains an ambiguous, encrypted, or oversized member.")
            with archive.open(m) as file:
                data = file.read(8*1024*1024+1)
            if len(data) != m.file_size:
                raise ValueError("Archive member size mismatch.")
            result[name] = {"bytes":len(data),"sha256":sha256(data).hexdigest()}
    return result


def fields_for(entries, requested):
    if not isinstance(entries,list) or len(entries)>10000:
        raise ValueError("Expected a bounded observation list.")
    found = defaultdict(dict)
    for item in entries:
        if not isinstance(item,dict) or not isinstance(item.get("field"),str) or "value" not in item:
            raise ValueError("Invalid observation entry.")
        name, value = item["field"], item["value"]
        if name in requested:
            token = json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False)
            found[name][token] = value
    return found


def names_of(value):
    if not isinstance(value,list) or not 1<=len(value)<=128 or not all(isinstance(n,str) and n for n in value) or len(set(value))!=len(value):
        raise ValueError("Requested fields must be unique, named strings.")
    return value


def comparison(doc):
    names = names_of(doc["fields_requested"])
    left, right = doc["left"],doc["right"]
    subjects = [s.get("subject") for s in (left,right)]
    if not all(isinstance(s,str) and s for s in subjects):
        raise ValueError("Both documents need a subject identifier.")
    base = {"kind":"observation-comparison","subjects":subjects,"runtime":"unobserved","deltas":{},"missing":[],"conflicts":[]}
    if subjects[0] != subjects[1]:
        return dict(base,verdict="different_subject")
    a,b = [fields_for(s["observations"],names) for s in (left,right)]
    for name in names:
        if max(len(a[name]),len(b[name]))>1:
            base["conflicts"].append(name)
        if not a[name] or not b[name]:
            base["missing"].append(name)
        if len(a[name])==len(b[name])==1 and a[name].keys()!=b[name].keys():
            base["deltas"][name]=[next(iter(a[name].values())),next(iter(b[name].values()))]
    verdict = ("conflict" if base["conflicts"] else "insufficient" if base["missing"] else
               "changed" if base["deltas"] else "same")
    return dict(base,verdict=verdict)


def exhibits(doc):
    target = doc["requested_build"]
    if not isinstance(target,str) or not target or not isinstance(doc["exhibits"],list):
        raise ValueError("Expected a named build and its reports.")
    names = names_of(doc["requested_fields"])
    entries = [{"field":key,"value":value} for ex in doc["exhibits"] if ex["build"]==target
               for key,value in ex["observed"].items()]
    found=fields_for(entries,names)
    return {"kind":"scoped-observations","subject":target,"runtime":"unobserved",
            "fields":{k:next(iter(found[k].values())) for k in names if len(found[k])==1},
            "missing":[k for k in names if not found[k]],"conflicts":[k for k in names if len(found[k])>1]}


class WebResources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.base = None
        self.resources = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "base" and self.base is None and attrs.get("href"):
            self.base = attrs["href"]
        if tag == "title":
            self.in_title = True
        key = {"script":"src","link":"href","img":"src"}.get(tag)
        if key and attrs.get(key):
            self.resources.append((tag,attrs[key]))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)


def parse_pcap(raw):
    variants = {b"\xd4\xc3\xb2\xa1":("<",1000000),b"\xa1\xb2\xc3\xd4":(">",1000000),
                b"\x4d\x3c\xb2\xa1":("<",10**9),b"\xa1\xb2\x3c\x4d":(">",10**9)}
    endian,scale=variants[raw[:4]]
    if len(raw)<24 or struct.unpack_from(endian+"HH",raw,4)!=(2,4):
        raise ValueError("Invalid classic PCAP header.")
    link=struct.unpack_from(endian+"I",raw,20)[0]
    offset=24
    captured=[]
    while offset < len(raw):
        if offset+16>len(raw) or len(captured)>=1024:
            raise ValueError("Truncated or oversized PCAP.")
        sec,frac,n,wire=struct.unpack_from(endian+"IIII",raw,offset)
        offset+=16
        if frac>=scale or n>wire or n>len(raw)-offset:
            raise ValueError("Invalid PCAP record bounds.")
        captured.append({"index":len(captured)+1,"seconds":sec,"fraction":frac,"fraction_per_second":scale,
                         "captured_bytes":n,"wire_bytes":wire,"truncated":n<wire})
        offset+=n
    return {"kind":"pcap","link_type":link,"frames":captured}


def background_worker(doc):
    if "background" not in doc:
        return {"state": "absent"}
    background = doc["background"]
    if not isinstance(background, dict):
        return {"state": "invalid", "field": "background"}
    if "service_worker" not in background:
        return {"state": "absent"}
    value = background["service_worker"]
    if not isinstance(value, str) or not value.strip():
        return {"state": "invalid", "field": "background.service_worker"}
    return {"state": "declared", "path": value}


def extension_metadata(doc):
    if not isinstance(doc,dict) or type(doc.get("manifest_version")) is not int or doc["manifest_version"] not in (2,3) or not isinstance(doc.get("name"),str):
        return None
    facts = {"kind":"extension-manifest",**{k:doc[k] for k in ("name","version","manifest_version","permissions",
            "host_permissions","optional_host_permissions","optional_permissions","action","browser_action","content_scripts") if k in doc}}
    if doc["manifest_version"] == 3:
        # Each list represents declarations in one MV3 field, not a runtime grant.
        declarations = {}
        for group, source in (("required_sites", "host_permissions"), ("optional_sites", "optional_host_permissions"),
                              ("required_apis", "permissions"), ("optional_apis", "optional_permissions")):
            values = doc.get(source, [])
            if isinstance(values, list) and all(isinstance(value, str) for value in values):
                declarations[group] = values
            else:
                declarations[group] = None
                declarations.setdefault("invalid_fields", []).append(source)
        facts["permission_declarations"] = declarations
        facts["service_worker_declaration"] = background_worker(doc)
    return facts


def decode_text(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Expected UTF-8 text.") from exc
    if TEXT_CONTROL.search(text):
        raise ValueError("Text contains unsupported control characters.")
    return text


def plain_text(raw):
    text = decode_text(raw)
    if re.match(r"%PDF-\d\.\d(?:[\r\n]|$)", text):
        raise ValueError("Expected plain text, found a PDF signature.")
    # Count CRLF as one ending and count an unterminated last line once.
    line_count = text.count("\n") + text.count("\r") - text.count("\r\n")
    if text and not text.endswith(("\r", "\n")):
        line_count += 1
    truncated = len(text) > TEXT_PREVIEW_CHARS
    return {"kind": "plain-text", "encoding": "utf-8", "character_count": len(text),
            "line_count": line_count, "preview": text[:TEXT_PREVIEW_CHARS],
            "preview_truncated": truncated, "unknown": ["claim_accuracy"]}


def email_headers(raw):
    # Stop at the first empty line. Even valid MIME bodies are opaque here.
    window = raw[:MAIL_HEADER_BYTES + 4]
    separator = MAIL_SEPARATOR.search(window)
    end = separator.start() if separator else len(raw)
    if end > MAIL_HEADER_BYTES:
        raise ValueError("Mail header block exceeds 32 KiB.")
    block = window[:end].replace(b"\r\n", b"\n").removesuffix(b"\n")
    if b"\r" in block or any(len(line) > MAIL_LINE_BYTES for line in block.split(b"\n")):
        raise ValueError("Invalid mail header line ending or length.")
    text = decode_text(block)
    if not text:
        raise ValueError("Expected at least one mail header.")

    headers = []
    fragments = []
    for line_number, line in enumerate(text.split("\n"), 1):
        if line.startswith((" ", "\t")):
            if not headers:
                raise ValueError("Mail header begins with an orphaned continuation.")
            fragments[-1].append(line)
            headers[-1]["line_end"] = line_number
            continue
        name, colon, value = line.partition(":")
        if not colon or not MAIL_FIELD_NAME.fullmatch(name):
            raise ValueError(f"Invalid mail header at line {line_number}.")
        if len(headers) == MAIL_HEADER_COUNT:
            raise ValueError("Mail header count exceeds 128 fields.")
        headers.append({"name": name, "line_start": line_number, "line_end": line_number})
        fragments.append([value])
    for header, pieces in zip(headers, fragments):
        header["value"] = "".join(pieces).strip(" \t")
    return {"kind": "email-headers", "scope": "headers-only", "headers": headers,
            "unknown": ["header_authenticity", "authentication_verification", "sender_identity",
                        "delivery_path", "recipient_disposition", "body_and_attachments"]}


def observe(path, parse_json):
    file,raw,identity=ordinary(path)
    suffix=file.suffix.lower()
    # Explicit text types validate their bytes before binary signature dispatch.
    if suffix in (".txt", ".md"):
        facts = plain_text(raw)
    elif suffix == ".eml":
        facts = email_headers(raw)
    elif suffix == ".obj":
        facts = observe_coff_data(raw)
        if facts is None:
            raise ValueError("Unsupported object layout for read-only COFF data inventory.")
    elif suffix == ".apk":
        with tempfile.TemporaryDirectory(prefix="rf-manifest-") as tmp:
            copy=Path(tmp)/"selected.apk"
            copy.write_bytes(raw)
            facts={"kind":"apk-compiled-manifest",**apk_manifest.inspect_apk(copy)}
    elif raw.startswith(b"PK\x03\x04") or raw.startswith(b"PK\x05\x06") or suffix==".zip":
        facts={"kind":"zip-resources","members":zip_members(raw)}
        if "manifest.json" in facts["members"]:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                try:
                    doc=parse_json(archive.read("manifest.json").decode("utf-8-sig"))
                    extension=extension_metadata(doc)
                except (ValueError,UnicodeError):
                    extension=None
                if extension:
                    facts["extension"]=extension
                    worker = extension.get("service_worker_declaration", {})
                    if worker.get("state") == "declared":
                        path = worker["path"]
                        # Match local, literal member paths. Leave URI resolution to the browser.
                        if any(c in path for c in "\\%?#:") or ".." in path.split("/") or path.startswith("//"):
                            worker["member_status"] = "unresolved"
                        else:
                            member = PurePosixPath(path.removeprefix("/")).as_posix()
                            meta = facts["members"].get(member)
                            worker["member_status"] = "present" if meta else "missing"
                            if meta:
                                worker["member"] = member
                                worker["sha256"] = meta["sha256"]
                    action=extension.get("action",extension.get("browser_action",{}))
                    popup=action.get("default_popup") if isinstance(action,dict) else None
                    if isinstance(popup,str) and popup in facts["members"] and popup.lower().endswith((".htm",".html")):
                        parser=WebResources()
                        parser.feed(archive.read(popup).decode("utf-8-sig")); parser.close()
                        facts["popup"]={"member":popup,"sha256":facts["members"][popup]["sha256"],"title":"".join(parser.title)}
    elif raw.startswith(b"SQLite format 3\x00"):
        wal = file.with_name(file.name + "-wal")
        try:
            has_wal_frames = wal.lstat().st_size > 32
        except FileNotFoundError:
            has_wal_frames = False
        if has_wal_frames:
            raise ValueError("SQLite may have committed data outside the main file. Select a consistent SQLite backup, not a live file with a WAL sidecar.")
        with tempfile.TemporaryDirectory(prefix="rf-sqlite-") as tmp:
            snapshot = Path(tmp) / "snapshot.db"
            snapshot.write_bytes(raw)
            with closing(sqlite3.connect(snapshot.as_uri() + "?immutable=1", uri=True)) as db:
                db.execute("PRAGMA trusted_schema=OFF")
                db.execute("PRAGMA query_only=ON")
                rows = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_schema "
                                  "WHERE substr(name, 1, 7) <> 'sqlite_' COLLATE NOCASE "
                                  "ORDER BY type,name LIMIT 257").fetchall()
            if len(rows)>256:
                raise ValueError("Too many SQLite schema entries.")
            facts={"kind":"sqlite-schema","schema":[dict(zip(("type","name","table","sql"),r)) for r in rows]}
    elif raw[:4] in (b"\xd4\xc3\xb2\xa1",b"\xa1\xb2\xc3\xd4",b"\x4d\x3c\xb2\xa1",b"\xa1\xb2\x3c\x4d"):
        facts=parse_pcap(raw)
    elif raw.startswith(b"RIFF") and raw[8:12]==b"WAVE":
        try:
            with wave.open(io.BytesIO(raw)) as recording:
                facts={"kind":"pcm-wav","channels":recording.getnchannels(),"sample_bytes":recording.getsampwidth(),
                       "rate_hz":recording.getframerate(),"frames":recording.getnframes()}
                payload=recording.readframes(facts["frames"])
            if len(payload)!=facts["frames"]*facts["channels"]*facts["sample_bytes"]:
                raise ValueError("Truncated PCM stream.")
        except (wave.Error,EOFError) as exc:
            raise ValueError("Invalid PCM WAV.") from exc
    elif raw.startswith(b"MZ") and len(raw)>=64:
        offset=struct.unpack_from("<I",raw,60)[0]
        if offset+24>len(raw) or raw[offset:offset+4]!=b"PE\0\0":
            raise ValueError("Invalid PE header.")
        machine,sections=struct.unpack_from("<HH",raw,offset+4)
        optional=offset+24
        opt_size=struct.unpack_from("<H",raw,offset+20)[0]
        if opt_size<70 or optional+opt_size>len(raw):
            raise ValueError("Invalid PE optional header.")
        magic=struct.unpack_from("<H",raw,optional)[0]
        if magic not in (0x10b,0x20b):
            raise ValueError("Unsupported PE optional header.")
        dirs=96 if magic==0x10b else 112
        ndir=struct.unpack_from("<I",raw,optional+dirs-4)[0] if opt_size>=dirs else 0
        cli=struct.unpack_from("<II",raw,optional+dirs+14*8) if ndir>14 and opt_size>=dirs+15*8 else (0,0)
        facts={"kind":"pe-header","machine":hex(machine),"sections":sections,
               "managed_clr_header":all(cli),"subsystem":struct.unpack_from("<H",raw,optional+68)[0],
               "architecture":{0x8664:"x86_64",0x14c:"x86",0xaa64:"arm64"}.get(machine,"unknown")}
    elif raw.startswith(b"\x7fELF"):
        if len(raw)<52 or raw[4] not in (1,2) or raw[5] not in (1,2) or (raw[4]==2 and len(raw)<64):
            raise ValueError("Invalid ELF identification.")
        fmt="<" if raw[5]==1 else ">"
        machine=struct.unpack_from(fmt+"H",raw,18)[0]
        facts={"kind":"elf-header","bits":32 if raw[4]==1 else 64,"byte_order":"little" if raw[5]==1 else "big",
               "machine":machine,"architecture":{3:"x86",62:"x86_64",40:"arm",183:"arm64"}.get(machine,"unknown")}
    elif suffix in (".html",".htm"):
        parser=WebResources()
        parser.feed(raw.decode("utf-8-sig")); parser.close()
        facts={"kind":"html","title":"".join(parser.title),"base":parser.base,
               "resources":[{"tag":tag,"reference":ref,"resolved":urljoin(parser.base or "",ref)} for tag,ref in parser.resources]}
    elif suffix==".plist":
        try:
            meta=plistlib.loads(raw)
            if not isinstance(meta,dict):
                raise ValueError("Expected a property-list dictionary.")
            facts={"kind":"bundle-plist",**{k:meta[k] for k in ("CFBundleIdentifier","CFBundleVersion",
                "CFBundleShortVersionString","CFBundleExecutable") if isinstance(meta.get(k),str)}}
        except (plistlib.InvalidFileException,OverflowError) as exc:
            raise ValueError("Invalid property list.") from exc
    elif suffix in (".json",".jsonl"):
        if suffix==".jsonl":
            raise ValueError("Select one JSON document; newline records may be read separately by the host.")
        doc=parse_json(raw.decode("utf-8-sig"))
        if isinstance(doc,dict) and {"left","right","fields_requested"}<=doc.keys():
            facts=comparison(doc)
        elif isinstance(doc,dict) and {"requested_build","requested_fields","exhibits"}<=doc.keys():
            facts=exhibits(doc)
        elif (extension := extension_metadata(doc)) is not None:
            facts=extension
        else:
            facts={"kind":"json","top_level":type(doc).__name__,"keys":sorted(doc)[:100] if isinstance(doc,dict) else [],
                   "entries":len(doc) if isinstance(doc,(dict,list)) else 1}
    elif suffix==".csv":
        rows=csv.reader(io.StringIO(raw.decode("utf-8-sig")))
        header=next(rows,[])
        count=sum(1 for _ in rows)
        facts={"kind":"csv","columns":header,"data_rows":count}
    else:
        raise ValueError("Unsupported material format. File contents may still be reviewed by the host.")
    return {"file":identity,"facts":facts,"basis":"owned-static-reader","runtime":"unobserved"}


def compare_files(first, second, parse_json):
    a,b=[observe(p,parse_json) for p in (first,second)]
    result={"first":a["file"],"second":b["file"],"bytes_equal":a["file"]["sha256"]==b["file"]["sha256"],
            "basis":"owned-static-reader","runtime":"unobserved"}
    left,right=a["facts"],b["facts"]
    if left["kind"]!=right["kind"]:
        return dict(result,comparable=False,kinds=[left["kind"],right["kind"]])
    if left["kind"]=="zip-resources":
        old,new=left["members"],right["members"]
        return dict(result,kind=left["kind"],added=sorted(new.keys()-old.keys()),removed=sorted(old.keys()-new.keys()),
                    changed=sorted(k for k in old.keys()&new.keys() if old[k]!=new[k]),
                    unchanged=sorted(k for k in old.keys()&new.keys() if old[k]==new[k]),members=[old,new])
    return dict(result,kind=left["kind"],field_differences={k:[left.get(k),right.get(k)] for k in sorted(left.keys()|right.keys())
                if json.dumps(left.get(k),sort_keys=True)!=json.dumps(right.get(k),sort_keys=True) or (k in left)!=(k in right)})
