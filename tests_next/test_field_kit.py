"""Regression checks for the owned field decoder's business-value contract."""
import importlib.util
from hashlib import sha256
import json
from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("field_service", ROOT / "components/field-kit/service.py")
field_service = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(field_service)


class FieldDecoder(unittest.TestCase):
    def test_inventory_with_unconfirmed_values_keeps_subtotal_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            manual = Path(directory) / "manual.json"
            listing = Path(directory) / "listing.json"
            manual.write_text(json.dumps({"format8": {"49": "数量"}}), encoding="utf-8")
            for values, known, missing in (
                ([0, None, 7], 7, 1), ([False, 0], 0, 1),
                ([None, None], None, 2), ([2, "待清点"], 2, 1),
            ):
                with self.subTest(values=values):
                    listing.write_text(json.dumps({"format": 8, "rows": [[49, v] for v in values]}), encoding="utf-8")
                    result = field_service.decode_records(str(listing), str(manual))
                    summary = result["quantity_summary"]
                    self.assertIsNone(summary["sum"])
                    self.assertIsNone(result["sum"])
                    self.assertIsNone(result["quantity_sum"])
                    self.assertEqual(summary["known_subtotal"], known)
                    self.assertEqual(summary["unknown_rows"], missing)
                    self.assertEqual(summary["known_rows"], len(values) - missing)

    def test_sqlite_schema_keeps_user_objects_with_sqlite_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stock.db'
            with closing(sqlite3.connect(path)) as db:
                db.executescript('''
                    CREATE TABLE inventory(id INTEGER PRIMARY KEY AUTOINCREMENT);
                    CREATE TABLE sqliteLedger(id INTEGER UNIQUE);
                    CREATE VIEW SQLiteTotals AS SELECT id FROM sqliteLedger;
                ''')
                names = {row[0] for row in db.execute('SELECT name FROM sqlite_schema')}
            self.assertIn('sqlite_sequence', names)
            facts = field_service.observe(str(path))['facts']
            self.assertEqual({row['name'] for row in facts['schema']},
                             {'inventory', 'sqliteLedger', 'SQLiteTotals'})

    def test_mv3_worker_declaration_member_and_execution_are_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "addon.zip"
            rows = [({}, {"state":"absent"}), ({"background":None}, {"state":"invalid","field":"background"}),
                    ({"background":{"scripts":["helper.js"]}}, {"state":"absent"}),
                    ({"background":{"service_worker":[]}}, {"state":"invalid","field":"background.service_worker"}),
                    ({"background":{"service_worker":"./jobs/main.js"}}, {"state":"declared","path":"./jobs/main.js",
                     "member_status":"present","member":"jobs/main.js","sha256":sha256(b"test").hexdigest()}),
                    ({"background":{"service_worker":"missing.js"}}, {"state":"declared","path":"missing.js","member_status":"missing"}),
                    ({"background":{"service_worker":"jobs%2Fmain.js"}}, {"state":"declared","path":"jobs%2Fmain.js","member_status":"unresolved"})]
            for fields, expected in rows:
                with self.subTest(fields=fields):
                    with zipfile.ZipFile(path,"w") as archive:
                        archive.writestr("manifest.json", json.dumps({"manifest_version":3,"name":"Example",**fields}))
                        archive.writestr("helper.js","")
                        archive.writestr("jobs/main.js",b"test")
                    result = field_service.materials.observe(str(path), json.loads)
                    self.assertEqual(result["facts"]["extension"]["service_worker_declaration"],expected)
                    self.assertEqual(result["runtime"],"unobserved")

    def test_v3_keeps_declared_sites_and_api_permissions_separate(self):
        manifest = {"name": "Example", "manifest_version": 3, "permissions": ["storage"],
                    "optional_permissions": ["bookmarks"], "host_permissions": ["https://a.invalid/*"]}
        facts = field_service.materials.extension_metadata(manifest)
        self.assertEqual(facts["permission_declarations"], {
            "required_sites": ["https://a.invalid/*"], "optional_sites": [],
            "required_apis": ["storage"], "optional_apis": ["bookmarks"]})
        self.assertEqual(facts["permissions"], manifest["permissions"])

    def test_invalid_permission_field_is_distinct_from_absent(self):
        facts = field_service.materials.extension_metadata(
            {"name": "Example", "manifest_version": 3, "host_permissions": "broken"})
        groups = facts["permission_declarations"]
        self.assertIsNone(groups["required_sites"])
        self.assertEqual(groups["optional_sites"], [])
        self.assertEqual(groups["invalid_fields"], ["host_permissions"])

    def test_v2_preserves_its_original_mixed_declarations(self):
        manifest = {"name": "Legacy", "manifest_version": 2,
                    "permissions": ["storage", "https://a.invalid/*"]}
        facts = field_service.materials.extension_metadata(manifest)
        self.assertEqual(facts["permissions"], manifest["permissions"])
        self.assertNotIn("permission_declarations", facts)

    def test_quantity_summary_separates_business_rows_from_all_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "listing.json").write_text(
                json.dumps({"format": 2, "rows": [[17, 6], [33, 3], [17, 4]]}),
                encoding="utf-8",
            )
            (folder / "manual.json").write_text(
                json.dumps({"format2": {"17": "数量", "33": "标签"}}),
                encoding="utf-8",
            )
            result = field_service.decode_records(
                str(folder / "listing.json"),
                str(folder / "manual.json"),
            )
            self.assertEqual(result["row_count"], 3)
            self.assertEqual(result["quantity_record_count"], 2)
            self.assertEqual(result["quantity_sum"], 10)
            self.assertEqual(result["count_rows"], 2)
            self.assertEqual(result["sum"], 10)
            self.assertEqual(
                result["quantity_summary"],
                {
                    "field": "数量",
                    "count_rows": 2,
                    "sum": 10,
                    "row_count_scope": "all decoded fields",
                },
            )


if __name__ == "__main__":
    unittest.main()
