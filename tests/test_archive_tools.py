"""archive/ 存档工具：清单完整性、脱敏规则、清单筛选。

这些用例不联网——只验证「清单自洽」和「脱敏不会漏、也不会把 JSON 标点当成密码」。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "archive" / "tools"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sanitize_session = load("sanitize_session")
fetch_archive = load("fetch_archive")
publish_asset = load("publish_asset")


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "archive" / "manifest.json").read_text(encoding="utf-8"))

    def test_schema_and_assets(self):
        self.assertEqual(self.manifest["schema"], 2)
        self.assertTrue(self.manifest["items"])
        tags = {rel["tag"] for rel in self.manifest["releases"]}
        for item in self.manifest["items"]:
            self.assertIn(item["release_tag"], tags, item["id"])
            self.assertGreater(item["size"], 0, item["id"])
            self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$", item["id"])
            self.assertTrue(item["name"].endswith((".zst", ".zip")), item["name"])
            self.assertIn(item["unpack"], {"zstd", "tar.zst", "zip", "none"}, item["id"])

    def test_ids_are_unique(self):
        ids = [item["id"] for item in self.manifest["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        names = [item["name"] for item in self.manifest["items"]]
        self.assertEqual(len(names), len(set(names)))

    def test_purged_entries_explain_themselves(self):
        for entry in self.manifest["purged"]:
            self.assertGreater(entry["size"], 0)
            self.assertTrue(entry["reason"])
            self.assertTrue(entry["restore"])


class SanitizeTest(unittest.TestCase):
    def setUp(self):
        self.rules = sanitize_session.compile_rules()

    def clean(self, text):
        return sanitize_session.sanitize_text(text, self.rules)[0]

    def test_token(self):
        out = self.clean('{"token":"gho_' + "A" * 30 + '"}')
        self.assertNotIn("A" * 30, out)
        self.assertIn("REDACTED", out)

    def test_url_credential(self):
        out = self.clean('url = "https://x-access-token:abcdef123456@github.com/o/r"')
        self.assertNotIn("abcdef123456", out)
        self.assertIn("x-access-token:REDACTED@", out)

    def test_json_password_field(self):
        out = self.clean('{"password": "hunter2", "user": "me"}')
        self.assertNotIn("hunter2", out)
        self.assertIn('"password": "REDACTED"', out)
        self.assertIn('"user": "me"', out)

    def test_lanzou_account_and_cn_password(self):
        out = self.clean("账号18651999816；密码abc123456；")
        self.assertNotIn("18651999816", out)
        self.assertNotIn("abc123456", out)
        self.assertIn("账号REDACTED", out)
        self.assertIn("密码REDACTED", out)

    def test_cn_password_does_not_eat_chinese_prose(self):
        # 「密码」后面跟中文不是密码，不能被吃掉
        out = self.clean("密码输入框的边框颜色改成灰色")
        self.assertEqual(out, "密码输入框的边框颜色改成灰色")

    def test_collect_secrets_skips_json_punctuation(self):
        # 回归：早期版本把 `","`、`\\` 当密码全文替换，一行能毁 64 万处
        text = '密码","user":"x"\n' * 50 + '密码Zx9Qw8Er\n'
        secrets = sanitize_session.collect_secrets(text, self.rules)
        self.assertEqual(secrets, ["Zx9Qw8Er"])

    def test_sanitize_is_idempotent(self):
        text = "账号18651999816；密码abc123456；token=gho_" + "B" * 30
        once = self.clean(text)
        twice = self.clean(once)
        self.assertEqual(once, twice)


class FileSanitizeTest(unittest.TestCase):
    def test_sanitize_file_replaces_password_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "in.jsonl"
            dst = Path(tmp) / "out.jsonl"
            src.write_text(
                '{"type":"user/message","text":"账号18651999816；密码Zx9Qw8Er"}\n'
                '{"type":"tool/result","text":"login Zx9Qw8Er ok"}\n',
                encoding="utf-8")
            counts = sanitize_session.sanitize_file(src, dst)
            body = dst.read_text(encoding="utf-8")
            self.assertNotIn("Zx9Qw8Er", body)
            self.assertNotIn("18651999816", body)
            self.assertGreater(counts["propagated"], 0)
            self.assertEqual(len(body.splitlines()), 2)


class SelectItemTest(unittest.TestCase):
    def setUp(self):
        self.manifest = {"items": [
            {"id": "a", "name": "a.zst"},
            {"id": "b", "name": "b.tar.zst"},
        ]}

    def test_all_by_default(self):
        self.assertEqual(len(fetch_archive.select_items(self.manifest, [])), 2)

    def test_by_id_and_name(self):
        picked = fetch_archive.select_items(self.manifest, ["a", "b.tar.zst"])
        self.assertEqual([item["id"] for item in picked], ["a", "b"])

    def test_unknown_id_exits(self):
        with self.assertRaises(SystemExit):
            fetch_archive.select_items(self.manifest, ["nope"])


class PublishAssetTest(unittest.TestCase):
    def test_sha256_of_matches_hashlib(self):
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"pulses")
            self.assertEqual(
                publish_asset.sha256_of(path),
                hashlib.sha256(b"pulses").hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
