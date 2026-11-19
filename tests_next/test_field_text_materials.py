"""Exercise plain-text and email observation through the Field stdio tool."""
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "components/field-kit/service.py"


class FieldTextMaterials(unittest.TestCase):
    def observe(self, samples):
        with tempfile.TemporaryDirectory(prefix="field-text-") as directory:
            requests = [dict(jsonrpc="2.0", id=0, method="initialize", params={
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "field-text-regression", "version": "1"},
            })]
            for index, (name, raw) in enumerate(samples.items(), 1):
                path = Path(directory) / name
                path.write_bytes(raw)
                requests.append(dict(jsonrpc="2.0", id=index, method="tools/call", params={
                    "name": "field_observe", "arguments": {"path": str(path)},
                }))
            run = subprocess.run(
                [sys.executable, "-B", str(SERVICE), "mcp"], cwd=ROOT,
                input="".join(json.dumps(request) + "\n" for request in requests),
                text=True, encoding="utf-8", capture_output=True, timeout=20, check=True,
            )
            self.assertEqual(run.stderr, "")
            replies = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual([reply["id"] for reply in replies], list(range(len(requests))))
            self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "reverse-fusion-field")
            for name, raw in samples.items():
                self.assertEqual((Path(directory) / name).read_bytes(), raw)
            self.assertEqual({path.name for path in Path(directory).iterdir()}, set(samples))
        return {name: reply["result"] for name, reply in zip(samples, replies[1:])}

    def assert_observation(self, response, name, raw, kind):
        result = response["structuredContent"]
        self.assertFalse(response["isError"], result)
        self.assertEqual(result["file"], {"name": name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()})
        self.assertEqual(result["basis"], "owned-static-reader")
        self.assertEqual(result["runtime"], "unobserved")
        self.assertEqual(result["facts"]["kind"], kind)
        return result["facts"]

    def assert_invalid_material(self, response):
        self.assertTrue(response["isError"], response["structuredContent"])
        self.assertEqual(response["structuredContent"]["error"]["code"], "invalid_material")

    def test_markdown_preserves_source_and_rejects_binary(self):
        sample = "入库说明.MD"
        raw = "# 九月到货\n实收 0 件\n".encode()
        replies = self.observe({sample: raw, "冒名.md": b"\xff\x00\x81"})
        self.assert_observation(replies[sample], sample, raw, "plain-text")
        self.assert_invalid_material(replies["冒名.md"])

    def test_plain_text_for_policy_recorder_and_notice(self):
        samples = {
            "policy.txt": "\u6307\u5b9a\u5165\u53e3 in.shop.invalid\n".encode(),
            "recorder.txt": b"Left I, right Q\r\nOne complex sample per frame",
            "notice.TXT": b"\xef\xbb\xbf" + "\u5317\u4ed3\u4ea4\u63a5\r\n\u5348\u73ed\r\n".encode(),
            "empty.txt": b"",
        }
        replies = self.observe(samples)
        for (name, raw), line_count in zip(samples.items(), (1, 2, 2, 0)):
            with self.subTest(name=name):
                facts = self.assert_observation(replies[name], name, raw, "plain-text")
                text = raw.decode("utf-8-sig")
                self.assertEqual(facts["preview"], text)
                self.assertEqual(facts["line_count"], line_count)
                self.assertEqual(facts["character_count"], len(text))
                self.assertEqual(facts["encoding"], "utf-8")
                self.assertFalse(facts["preview_truncated"])
                self.assertIn("claim_accuracy", facts["unknown"])

    def test_text_preview_is_bounded_but_validation_covers_the_whole_file(self):
        text = "\u5e93\U0001f4e6" * 3000 + "\nTAIL"
        raw = text.encode()
        replies = self.observe({"large.txt": raw, "bad-tail.txt": raw + b"\x00"})
        facts = self.assert_observation(replies["large.txt"], "large.txt", raw, "plain-text")
        self.assertEqual(facts["preview"], text[:4096])
        self.assertTrue(facts["preview_truncated"])
        self.assertEqual(facts["character_count"], len(text))
        self.assertEqual(facts["line_count"], 2)
        self.assert_invalid_material(replies["bad-tail.txt"])

    def test_mail_preserves_order_folding_duplicates_and_header_only_scope(self):
        raw = (
            b"From: buyer@shop.invalid\r\n"
            b"Authentication-Results: in.shop.invalid; dkim=pass header.d=mailer.invalid;\r\n"
            b"\tspf=pass smtp.mailfrom=shop.invalid\r\n"
            b"authentication-results: other.invalid; spf=fail\r\n"
            b"Subject: =?UTF-8?B?5L2g5aW9?=\r\n"
            b"Content-Type: multipart/mixed; boundary=abc\r\n\r\n"
            b"--abc\r\nContent-Disposition: attachment; filename=body-marker.txt\r\n"
            b"\r\n\xff\x00body-marker\r\n--abc--\r\n"
        )
        short = b"\xef\xbb\xbfFrom: buyer@shop.invalid\nSubject: Header-only\n"
        replies = self.observe({"handoff.EML": raw, "header-only.eml": short})
        facts = self.assert_observation(replies["handoff.EML"], "handoff.EML", raw, "email-headers")
        self.assertEqual(facts["scope"], "headers-only")
        self.assertEqual(facts["headers"], [
            {"name": "From", "value": "buyer@shop.invalid", "line_start": 1, "line_end": 1},
            {"name": "Authentication-Results", "value": "in.shop.invalid; dkim=pass header.d=mailer.invalid;"
             "\tspf=pass smtp.mailfrom=shop.invalid", "line_start": 2, "line_end": 3},
            {"name": "authentication-results", "value": "other.invalid; spf=fail", "line_start": 4, "line_end": 4},
            {"name": "Subject", "value": "=?UTF-8?B?5L2g5aW9?=", "line_start": 5, "line_end": 5},
            {"name": "Content-Type", "value": "multipart/mixed; boundary=abc", "line_start": 6, "line_end": 6},
        ])
        self.assertTrue({"header_authenticity", "authentication_verification", "sender_identity", "delivery_path",
                         "recipient_disposition", "body_and_attachments"} <= set(facts["unknown"]))
        self.assertNotIn("body-marker", json.dumps(replies["handoff.EML"]))
        header_only = self.assert_observation(replies["header-only.eml"], "header-only.eml", short, "email-headers")
        self.assertEqual([header["name"] for header in header_only["headers"]], ["From", "Subject"])

    def test_binary_mislabeled_text_and_invalid_mail_return_invalid_material(self):
        samples = {
            "invalid-utf8.txt": b"\xff\xfe\x00\x00",
            "control.txt": b"notice\x1b[0m",
            "pdf.txt": b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF\n",
            "empty.eml": b"",
            "headerless.eml": b"\nFrom: body text\n",
            "orphaned-fold.eml": b" From: buyer@shop.invalid\n\nunused",
            "broken-name.eml": b"From : buyer@shop.invalid\n\nunused",
            "broken-line.eml": b"From: buyer@shop.invalid\ninvalid header\n\nunused",
            "bare-cr.eml": b"From: buyer@shop.invalid\rSubject: invalid\n\nunused",
            "binary-header.eml": b"Subject: \x00\xff\n\nunused",
            "long-line.eml": b"Subject: " + b"x" * 999 + b"\n\nunused",
            "large-header.eml": b"Subject: x\n" + (b" " + b"x" * 800 + b"\n") * 50 + b"\nunused",
            "many-headers.eml": b"X-Label: x\n" * 129 + b"\nunused",
            "unsupported.log": b"ordinary text, unsupported extension",
        }
        for name, response in self.observe(samples).items():
            with self.subTest(name=name):
                self.assert_invalid_material(response)

    def test_existing_wav_zip_and_json_dispatch_and_binary_mismatches(self):
        wav = io.BytesIO()
        with wave.open(wav, "wb") as recording:
            recording.setparams((2, 2, 8000, 0, "NONE", "not compressed"))
            recording.writeframes(b"\0" * 640)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("static.txt", b"fixture")
        wav_raw, zip_raw, json_raw = wav.getvalue(), archive.getvalue(), b'{"entry":1}'
        replies = self.observe({
            "receiver.wav": wav_raw, "resources.bundle": zip_raw, "packet.json": json_raw,
            "archive.txt": zip_raw, "receiver.eml": wav_raw,
        })
        wav_facts = self.assert_observation(replies["receiver.wav"], "receiver.wav", wav_raw, "pcm-wav")
        self.assertEqual(wav_facts, {"kind": "pcm-wav", "channels": 2, "sample_bytes": 2, "rate_hz": 8000, "frames": 160})
        zip_facts = self.assert_observation(replies["resources.bundle"], "resources.bundle", zip_raw, "zip-resources")
        self.assertIn("static.txt", zip_facts["members"])
        json_facts = self.assert_observation(replies["packet.json"], "packet.json", json_raw, "json")
        self.assertEqual(json_facts["keys"], ["entry"])
        for name in ("archive.txt", "receiver.eml"):
            self.assert_invalid_material(replies[name])


if __name__ == "__main__":
    unittest.main()
