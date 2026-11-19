"""Public review-host attachment and ownership, using only disposable homes."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_hosts", ROOT / "scripts/review-host.py")
hosts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosts)
import review_host_config as config


class HostAttachment(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="two words 宿主 ")
        self.addCleanup(scratch.cleanup)
        self.home = Path(scratch.name)
        probe = patch.object(hosts, "check_transport", return_value={"fixture_records": 2})
        self.probe = probe.start()
        self.addCleanup(probe.stop)

    def run_host(self, action, host):
        return hosts.manage(action, host, self.home)

    def test_all_four_attach_twice_check_and_remove_keep_unrelated_bytes(self):
        initial = {
            "codex": b'# example\r\nmodel = "other"\r\n[mcp_servers.other]\r\ncommand = "other"',
            "pi": b'{ "mcpServers" : {"other":{"command":"other"}}, "label":"original" }\n',
            "opencode": b'{// keep this comment\r\n"mcp":{"other":{"enabled":false},},\r\n"theme":"other",}\r\n',
        }
        for host in hosts.HOSTS:
            with self.subTest(host=host):
                folder, conf = hosts.paths(host, self.home)
                if conf:
                    conf.parent.mkdir(parents=True, exist_ok=True)
                    conf.write_bytes(initial[host])
                self.run_host("attach", host)
                original = (folder / hosts.RECEIPT).read_bytes()
                first = conf.read_bytes() if conf else None
                self.run_host("attach", host)
                self.assertEqual(original, (folder / hosts.RECEIPT).read_bytes())
                self.assertNotIn(b"label", original)
                if conf:
                    self.assertEqual(first, conf.read_bytes())
                self.assertEqual("verified", self.run_host("check", host)["status"])
                self.run_host("remove", host)
                self.assertFalse(folder.exists())
                if conf:
                    self.assertEqual(initial[host], conf.read_bytes())
                self.assertEqual("no-owned-installation", self.run_host("remove", host)["status"])

    def field_layout(self, *guides):
        sources = self.home / 'sources'
        sources.mkdir(exist_ok=True)
        for name in ('SKILL.md', 'domain-methods.md', 'raw-materials.md', 'independent-build.md', *guides):
            if not (sources / name).exists():
                (sources / name).write_text(name, encoding='utf-8')
        layout = hosts.CHECKOUT._replace(skill=sources / 'SKILL.md', methods=sources, profile=sources / 'profile.json')
        layout.profile.write_bytes(hosts.encoded({'profile': layout.name, 'version': '1.1.19', 'field_guides': guides}))
        return layout

    def test_changed_guide_bytes_fail_check_until_synced(self):
        layout = self.field_layout()
        folder = Path(hosts.manage('attach', 'pi', self.home, layout=layout)['skill'])
        installed = folder / 'references/domain-methods.md'
        (layout.methods / installed.name).write_bytes(b'new instructions')
        receipt = (folder / hosts.RECEIPT).read_bytes()
        with self.assertRaisesRegex(ValueError, 'setup'):
            hosts.manage('check', 'pi', self.home, layout=layout)
        self.assertEqual(installed.read_bytes(), b'domain-methods.md')
        self.assertEqual((folder / hosts.RECEIPT).read_bytes(), receipt)
        hosts.manage('attach', 'pi', self.home, layout=layout)
        self.assertEqual(installed.read_bytes(), b'new instructions')
        self.assertEqual(hosts.manage('check', 'pi', self.home, layout=layout)['status'], 'verified')

    def test_added_and_retired_guides_follow_the_receipt_across_upgrades(self):
        old, new = 'field-guide-old.md', 'field-guide-new.md'
        layout = self.field_layout(old)
        folder = Path(hosts.manage('attach', 'pi', self.home, layout=layout)['skill'])
        refs = folder / 'references'
        (refs / 'notes.md').write_bytes(b'personal')
        for before, after in ((old, new), (new, old)):
            self.field_layout(after)
            with self.assertRaisesRegex(ValueError, 'setup'):
                hosts.manage('check', 'pi', self.home, layout=layout)
            hosts.manage('attach', 'pi', self.home, layout=layout)
            self.assertFalse((refs / before).exists())
            self.assertEqual((refs / after).read_bytes(), after.encode())
            self.assertEqual(hosts.manage('check', 'pi', self.home, layout=layout)['status'], 'verified')
        self.field_layout(new)
        (refs / new).write_bytes(b'personal file under a new guide name')
        hosts.manage('remove', 'pi', self.home, layout=layout)
        self.assertEqual({p.name for p in refs.iterdir()}, {'notes.md', new})
        self.assertEqual((refs / new).read_bytes(), b'personal file under a new guide name')

    def test_upgrade_conflicts_preserve_foreign_and_locally_edited_guides(self):
        old, new = 'field-guide-old.md', 'field-guide-new.md'
        layout = self.field_layout(old)
        folder, conf = hosts.paths('pi', self.home, layout=layout)
        hosts.manage('attach', 'pi', self.home, layout=layout)
        refs = folder / 'references'
        receipt = (folder / hosts.RECEIPT).read_bytes()
        config_bytes = conf.read_bytes()
        self.field_layout(new)
        (refs / new).write_bytes((layout.methods / new).read_bytes())
        with self.assertRaises(ValueError):
            hosts.manage('attach', 'pi', self.home, layout=layout)
        self.assertEqual((refs / new).read_bytes(), new.encode())
        self.assertEqual((refs / old).read_bytes(), old.encode())
        (refs / new).unlink()
        (refs / old).write_bytes(b'my edits')
        for action in ('attach', 'remove'):
            with self.assertRaises(ValueError):
                hosts.manage(action, 'pi', self.home, layout=layout)
            self.assertEqual((refs / old).read_bytes(), b'my edits')
            self.assertFalse((refs / new).exists())
            self.assertEqual((folder / hosts.RECEIPT).read_bytes(), receipt)
            self.assertEqual(conf.read_bytes(), config_bytes)

    def test_upgrade_write_failure_restores_old_receipt_and_guide(self):
        old, new = 'field-guide-old.md', 'field-guide-new.md'
        layout = self.field_layout(old)
        folder = Path(hosts.manage('attach', 'pi', self.home, layout=layout)['skill'])
        receipt = folder / hosts.RECEIPT
        original = receipt.read_bytes()
        self.field_layout(new)
        replace = hosts._replace_checked

        def fail_at_receipt(path, before, after):
            if path == receipt:
                raise OSError('test receipt write failure')
            replace(path, before, after)

        with patch.object(hosts, '_replace_checked', side_effect=fail_at_receipt), self.assertRaises(OSError):
            hosts.manage('attach', 'pi', self.home, layout=layout)
        self.assertEqual(receipt.read_bytes(), original)
        self.assertEqual((folder / 'references' / old).read_bytes(), old.encode())
        self.assertFalse((folder / 'references' / new).exists())
        hosts.manage('attach', 'pi', self.home, layout=layout)
        self.assertEqual(hosts.manage('check', 'pi', self.home, layout=layout)['status'], 'verified')

    def test_remove_rejects_unrecognized_receipt_member(self):
        layout = self.field_layout()
        folder = Path(hosts.manage('attach', 'pi', self.home, layout=layout)['skill'])
        receipt = folder / hosts.RECEIPT
        record = json.loads(receipt.read_bytes())
        note = folder / 'notes.md'
        note.write_bytes(b'personal')
        record['files'][note.name] = hosts.sha256(note.read_bytes()).hexdigest()
        receipt.write_bytes(hosts.encoded(record))
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            hosts.manage('remove', 'pi', self.home, layout=layout)
        self.assertEqual(note.read_bytes(), b'personal')
        self.assertTrue((folder / 'SKILL.md').exists())

    def test_first_time_remove_returns_files_to_absence(self):
        for host in hosts.HOSTS:
            folder, conf = hosts.paths(host, self.home)
            self.run_host("attach", host)
            self.run_host("remove", host)
            self.assertFalse(folder.exists())
            if conf:
                self.assertFalse(conf.exists())

    def test_native_claude_plugin_keeps_account_and_personal_guidance(self):
        guidance = self.home / ".claude/CLAUDE.md"
        guidance.parent.mkdir()
        guidance.write_bytes(b"keep my instructions")
        account = self.home / ".claude.json"
        account.write_bytes(b'{"unrelated":"keep its bytes"}')
        folder, _ = hosts.paths("claude", self.home)
        self.run_host("attach", "claude")
        self.assertTrue((folder / ".claude-plugin/plugin.json").exists())
        entry = json.loads((folder / ".mcp.json").read_bytes())["mcpServers"]["review"]
        self.assertEqual(hosts.command(), [entry["command"], *entry["args"]])
        self.run_host("remove", "claude")
        self.assertEqual(guidance.read_bytes(), b"keep my instructions")
        self.assertEqual(account.read_bytes(), b'{"unrelated":"keep its bytes"}')

    def test_new_config_members_added_after_install_survive(self):
        for host, key in (("opencode", "mcp"), ("pi", "mcpServers")):
            folder, conf = hosts.paths(host, self.home)
            self.run_host("attach", host)
            content = json.loads(conf.read_bytes())
            content[key]["foreign"] = {"command": "other"}
            content["unrelated"] = 7
            conf.write_text(json.dumps(content), encoding="utf-8")
            (folder / "my-notes.md").write_text("keep", encoding="utf-8")
            self.run_host("remove", host)
            self.assertEqual(json.loads(conf.read_bytes()), {key: {"foreign": {"command": "other"}}, "unrelated": 7})
            self.assertEqual((folder / "my-notes.md").read_text(), "keep")

    def test_first_install_preserves_foreign_keys_skill_and_jsonc_layer(self):
        for host, contents in (("codex", b'[mcp_servers.reverse-fusion-review]\ncommand="other"'),
                               ("pi", b'{"mcpServers":{"reverse-fusion-review":{}}}'),
                               ("opencode", b'{"mcp":{"reverse-fusion-review":{}}}')):
            folder, conf = hosts.paths(host, self.home)
            if host == "opencode":
                conf = conf.with_suffix(".json")
            conf.parent.mkdir(parents=True, exist_ok=True)
            conf.write_bytes(contents)
            with self.assertRaises(ValueError):
                self.run_host("attach", host)
            self.assertEqual(contents, conf.read_bytes())
            self.assertFalse(folder.exists())
        folder, _ = hosts.paths("claude", self.home)
        folder.mkdir(parents=True)
        (folder / "my-file").touch()
        with self.assertRaises(ValueError):
            self.run_host("attach", "claude")
        self.assertTrue((folder / "my-file").exists())

    def test_edited_owned_file_blocks_removal_without_altering_config(self):
        folder, conf = hosts.paths("pi", self.home)
        self.run_host("attach", "pi")
        config_bytes = conf.read_bytes()
        (folder / "SKILL.md").write_bytes(b"local edits")
        with self.assertRaises(ValueError):
            self.run_host("remove", "pi")
        self.assertEqual(config_bytes, conf.read_bytes())
        self.assertEqual((folder / "SKILL.md").read_bytes(), b"local edits")

    def test_probe_failure_and_partial_file_write_leave_retryable_install(self):
        folder, conf = hosts.paths("codex", self.home)
        self.probe.side_effect = ValueError("unprepared")
        with self.assertRaises(ValueError):
            self.run_host("attach", "codex")
        self.assertFalse(folder.exists())
        self.probe.side_effect = None
        real = hosts._replace_checked

        def fail_at_config(path, before, after):
            if path == conf:
                raise OSError("simulated write failure")
            return real(path, before, after)
        with patch.object(hosts, "_replace_checked", side_effect=fail_at_config), self.assertRaises(OSError):
            self.run_host("attach", "codex")
        self.assertFalse(conf.exists())
        self.run_host("attach", "codex")
        self.assertEqual("verified", self.run_host("check", "codex")["status"])

    def test_resumes_interrupted_first_install_and_finishes_interrupted_removal(self):
        folder, conf = hosts.paths("pi", self.home)
        self.run_host("attach", "pi")
        receipt = folder / hosts.RECEIPT
        original = json.loads(receipt.read_bytes())
        receipt.write_bytes(hosts.encoded(dict(original, pending=True)))
        (folder / "SKILL.md").unlink()
        conf.unlink()
        self.run_host("attach", "pi")
        self.assertFalse(json.loads(receipt.read_bytes()).get("pending"))
        (folder / "SKILL.md").unlink()
        self.run_host("remove", "pi")
        self.assertFalse(folder.exists())
        self.assertFalse(conf.exists())

    def test_host_environment_overrides_and_explicit_isolation(self):
        overrides = {k: str(self.home / k) for k in
                     ("CODEX_HOME", "PI_CODING_AGENT_DIR", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME",
                      "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG")}
        with patch.dict(os.environ, overrides):
            self.assertEqual(hosts.paths("codex")[1], Path(overrides["CODEX_HOME"]) / "config.toml")
            self.assertEqual(hosts.paths("pi")[1], Path(overrides["PI_CODING_AGENT_DIR"]) / "mcp.json")
            self.assertEqual(hosts.paths("claude")[0].parent.parent, Path(overrides["CLAUDE_CONFIG_DIR"]))
            self.assertEqual(hosts.paths("opencode")[0].parent.parent, Path(overrides["OPENCODE_CONFIG_DIR"]))
            self.assertEqual(hosts.paths("opencode")[1], Path(overrides["OPENCODE_CONFIG"]))
            self.assertEqual(hosts.paths("pi", self.home)[1], self.home / ".pi/agent/mcp.json")

    def test_jsonc_comments_strings_bom_and_edit_after_empty_group(self):
        original = b'\xef\xbb\xbf{// \xe4\xbf\x9d\xe7\x95\x99\n "mcp":{}, "text":"// /* {,} */", }\n'
        payload, receipt = config.update("opencode", original, hosts.command())
        restored, _ = config.update("opencode", payload, hosts.command(), receipt, remove=True)
        self.assertEqual(restored, original)
        added = payload.replace(b'"enabled": true}', b'"enabled": true}, "new":{"enabled":false}')
        restored, _ = config.update("opencode", added, hosts.command(), receipt, remove=True)
        self.assertEqual({"new": {"enabled": False}}, config._json_object(restored.decode("utf-8-sig"), True)[1]["mcp"])

    def test_opencode_v2_uses_native_nested_servers_and_preserves_v1_shape(self):
        original = b'{\n  "mcp": {\n    "foreign": {"enabled": false}\n  },\n  "theme": "keep"\n}\n'
        payload, receipt = config.update("opencode", original, hosts.command(), opencode_version=2)
        data = json.loads(payload)
        self.assertEqual(data["mcp"]["foreign"], {"enabled": False})
        self.assertEqual(data["mcp"]["servers"][config.NAME]["type"], "local")
        self.assertEqual(data["theme"], "keep")
        restored, _ = config.update("opencode", payload, hosts.command(), receipt,
                                    remove=True, opencode_version=2)
        self.assertEqual(restored, original)

        v1_payload, _ = config.update("opencode", original, hosts.command())
        v1_data = json.loads(v1_payload)
        self.assertIn(config.NAME, v1_data["mcp"])
        self.assertNotIn("servers", v1_data["mcp"])

    def test_opencode_v2_creates_and_removes_its_owned_parent(self):
        payload, receipt = config.update("opencode", None, hosts.command(), opencode_version=2)
        self.assertEqual(json.loads(payload), {
            "mcp": {"servers": {config.NAME: {
                "type": "local", "command": hosts.command()
            }}}
        })
        restored, _ = config.update("opencode", payload, hosts.command(), receipt,
                                    remove=True, opencode_version=2)
        self.assertIsNone(restored)

    def test_missing_entry_is_detected_and_repeat_attach_repairs_it(self):
        _, conf = hosts.paths("pi", self.home)
        self.run_host("attach", "pi")
        conf.write_bytes(b'{"my-setting":1}\n')
        with self.assertRaises(ValueError):
            self.run_host("check", "pi")
        self.run_host("attach", "pi")
        self.assertEqual("verified", self.run_host("check", "pi")["status"])

    def test_refuses_invalid_or_ambiguous_configuration(self):
        for src in ('{"mcp":{}, "mcp":{}}', '{"mcp":null}', '{"mcp":{,}}', '[]'):
            with self.subTest(src=src), self.assertRaises(ValueError):
                config.update("opencode", src.encode(), hosts.command())


if __name__ == "__main__":
    unittest.main()
