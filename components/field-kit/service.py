"""Read static facts and report a fixed official REA observation on user-selected files."""
import base64
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import sys
import zipfile


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE if (HERE / "next-review.py").is_file() else HERE.parents[1] / "scripts"
sys.path.insert(0,str(HERE))
import materials
import official_identity
import flutter_inventory

spec = importlib.util.spec_from_file_location("field_base_review",SCRIPTS/"next-review.py")
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def guarded(fn):
    def run(**args):
        try:
            return fn(**args)
        except review.ReviewError:
            raise
        except (ValueError,OSError,KeyError,TypeError,IndexError,AttributeError,EOFError,struct.error,RecursionError,zipfile.BadZipFile,
                sqlite3.DatabaseError,review.runtime.RuntimeError) as exc:
            review.fail(getattr(exc,"code","invalid_material"),str(exc)[:640])
    return run


def identify(path):
    file,raw,identity=materials.ordinary(path)
    try:
        result=official_identity.observe_bytes(raw,file.name,review.runtime)
    except official_identity.IdentityError as exc:
        failure = {"file": identity, "error": {"code": exc.code, "message": str(exc)}}
        if exc.receipt is not None:
            failure["official_receipt"] = wire_receipt(exc.receipt)
        if exc.partial_export is not None:
            export = dict(exc.partial_export)
            export["bundle_base64"] = base64.b64encode(export.pop("bundle_bytes")).decode("ascii")
            export["inspection"] = wire_receipt(export["inspection"])
            failure["partial_export"] = export
        return failure
    native=result["official"]
    native["bundle_base64"]=base64.b64encode(native.pop("bundle_bytes")).decode("ascii")
    for key in ("inspection","import"):
        native[key] = wire_receipt(native[key])
    return result


def wire_receipt(receipt):
    result = dict(receipt)
    for stream in ("stdout", "stderr"):
        data = receipt[stream]
        result[stream] = data.decode("utf-8-sig", errors="replace")
        result[stream + "_base64"] = base64.b64encode(data).decode("ascii")
    return result


def about(**kwargs):
    result=review.info(**kwargs)
    result["field_inputs"]=["compiled Android manifest","offline ZIP inventory","browser manifest","HTML",
                            "SQLite schema","classic PCAP frame metadata","CSV","scoped observations",
                            "decoded field/value records","fixed official artifact identity"]
    return result


def decode_records(listing, manual):
    listing_file, listing_raw, listing_identity = materials.ordinary(listing)
    manual_file, manual_raw, manual_identity = materials.ordinary(manual)
    listing = review.parse_json(listing_raw.decode("utf-8-sig"))
    manual = review.parse_json(manual_raw.decode("utf-8-sig"))
    if not isinstance(listing, dict) or not isinstance(manual, dict):
        raise ValueError("The listing and manual must be JSON objects.")
    format_id = listing.get("format")
    rows = listing.get("rows")
    if type(format_id) is not int or not isinstance(rows, list) or not rows:
        raise ValueError("The listing needs an integer format and a non-empty rows array.")
    mapping = manual.get("format" + str(format_id))
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("The manual has no mapping for the selected format.")
    mapped = []
    field_counts = {}
    field_sums = {}
    numeric_counts = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("Each record must be a two-item field/value row.")
        field_id, value = row
        label = mapping.get(str(field_id))
        if not isinstance(label, str) or not label:
            raise ValueError("A record refers to a field missing from the selected manual format.")
        mapped.append({"field_id": field_id, "field": label, "value": value})
        field_counts[label] = field_counts.get(label, 0) + 1
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            field_sums[label] = field_sums.get(label, 0) + value
            numeric_counts[label] = numeric_counts.get(label, 0) + 1
    result = {
        "kind": "decoded-field-value-records",
        "format": format_id,
        "row_count": len(mapped),
        "mapped_rows": mapped,
        "field_counts": field_counts,
        "field_sums": field_sums,
        "files": {
            "listing": listing_identity,
            "manual": manual_identity,
        },
        "basis": "owned-static-reader",
        "runtime": "unobserved",
    }
    quantity_labels = {"数量", "quantity", "count", "units"}
    for label in field_counts:
        if label.lower() in quantity_labels:
            quantity_count = field_counts[label]
            result["quantity_field"] = label
            result["quantity_record_count"] = quantity_count
            result["count_rows"] = quantity_count
            known_count = numeric_counts.get(label, 0)
            complete = known_count == quantity_count
            total = field_sums.get(label) if complete else None
            result["quantity_sum"] = result["sum"] = total
            result["quantity_summary"] = {
                "field": label,
                "count_rows": quantity_count,
                "sum": total,
                "row_count_scope": "all decoded fields",
            }
            if not complete:
                result["quantity_summary"].update(
                    known_rows=known_count,
                    unknown_rows=quantity_count - known_count,
                    known_subtotal=field_sums.get(label),
                )
            break
    return result


review.NAME="reverse-fusion-field"
review.VERSION="1.1.19"
review.FUNCTIONS["review_info"]=about
path_schema={"path":{"type":"string"}}
for name,desc,properties,fn in [
    ("field_observe","Read static facts from an actual local application artifact or a structured observation packet.",
     path_schema,lambda path:materials.observe(path,review.parse_json)),
    ("field_compare_files","Compare two local resource archives or supported metadata files. Returns both input hashes.",
     {"first":{"type":"string"},"second":{"type":"string"}},lambda first,second:materials.compare_files(first,second,review.parse_json)),
    ("field_decode_records","Decode field/value rows with the matching manual. field_sums counts numeric values only. For the selected quantity field, quantity_summary.sum is null when any quantity is nonnumeric. In that case known_subtotal and unknown_rows describe the partial result.",
     {"listing":{"type":"string"},"manual":{"type":"string"}},decode_records),
    ("field_rea_identify","Observe identity of a small local UTF-8 XML property list with official REA 6.9.0. Returns the original export in base64 and its real import receipt.",path_schema,identify),
]:
    review.SPECS[name]=(desc,properties,list(properties))
    review.FUNCTIONS[name]=guarded(fn)

review.SPECS["field_observe"] = (
    "Read static facts from a local artifact. For Dart package classes in an ARM64 Flutter release library, "
    "select detail=flutter-package-classes. Narrow long results by a class or package substring in query.",
    {**path_schema, "detail":{"type":"string","enum":["flutter-package-classes"]}, "query":{"type":"string"}},
    ["path"])


def observe(path, detail=None, query=""):
    if detail == "flutter-package-classes":
        return flutter_inventory.observe(path, query)
    if detail is not None or query:
        raise ValueError("Select flutter-package-classes to search the package class inventory")
    return materials.observe(path, review.parse_json)


review.FUNCTIONS["field_observe"] = guarded(observe)


if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1] in review.FUNCTIONS:
        name=sys.argv[1]
        try:
            params=json.loads(sys.argv[2]) if len(sys.argv)>2 else {}
            response=review.FUNCTIONS[name](**params)
            print(review.encode(response))
            if "error" in response:
                raise SystemExit(2)
        except (ValueError,OSError,TypeError) as error:
            print(json.dumps({"error":str(error)},ensure_ascii=True))
            raise SystemExit(2)
    else:
        raise SystemExit(review.main())
