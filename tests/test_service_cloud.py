"""云端文件管理（管理页）的服务层测试：浏览 / 新建 / 上传目录。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_lanzou_account import MockLanzouAccount
from online.errors import AuthError, SourceError
from online.service import OnlineService, PresetRef


class CloudManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.db = base / "db"
        self.account_db = base / "account"
        self.server = MockLanzouAccount("18651999816", "secret")
        self.server.start()
        self.svc = OnlineService(
            self.db, app_version="2.6.0",
            account_base=self.server.base,
            account_db=str(self.account_db))
        self.svc.login("18651999816", "secret")

    def tearDown(self):
        self.server.stop()
        self.temp.cleanup()

    def test_browse_create_and_find(self):
        root = self.svc.cloud_browse("/")
        self.assertEqual(root["path"], "/")
        made = self.svc.cloud_mkdir("/", "黑盒测试")
        self.assertEqual(made["path"], "/黑盒测试")
        listing = self.svc.cloud_browse("/黑盒测试")
        self.assertEqual(listing["path"], "/黑盒测试")
        self.assertEqual(listing["folders"], [])
        # 浏览不存在的目录不能顺手建目录
        with self.assertRaises(SourceError):
            self.svc.cloud_browse("/不存在")
        # 再查一次，目录仍然只有刚建的那个
        self.assertEqual(len(self.svc.cloud_browse("/")["folders"]), 1)

    def test_upload_file_and_folder_tree(self):
        local = Path(self.temp.name) / "local"
        local.mkdir()
        (local / "hello.txt").write_text("hello", encoding="utf-8")
        nested = local / "sub"
        nested.mkdir()
        (nested / "nested.zip").write_bytes(b"PK\x05\x06" + b"\0" * 18)
        (local / "empty").mkdir()

        result = self.svc.cloud_upload("/上传测试", [str(local)])
        self.assertEqual(result["failed"], [])
        self.assertEqual(len(result["uploaded"]), 2)
        top = self.svc.cloud_browse("/上传测试")
        self.assertEqual([f["name"] for f in top["folders"]], ["local"])
        inside = self.svc.cloud_browse("/上传测试/local")
        self.assertIn("hello.txt", [f["name"] for f in inside["files"]])
        self.assertEqual([f["name"] for f in inside["folders"]], ["empty", "sub"])
        sub = self.svc.cloud_browse("/上传测试/local/sub")
        self.assertIn("nested.zip", [f["name"] for f in sub["files"]])

    def test_probe_and_quota(self):
        probe = self.svc.probe_cloud()
        self.assertTrue(probe["logged_in"])
        self.assertTrue(probe["online"])
        self.assertIn("quota", probe)

    def test_publish_rejects_player_role(self):
        ref = PresetRef("x", str(Path(self.temp.name)), str(Path(self.temp.name)))
        with self.assertRaises(AuthError):
            self.svc.publish(ref, None, [], version="v1", role="player")

    def test_invalid_folder_name(self):
        with self.assertRaises(SourceError):
            self.svc.cloud_mkdir("/", "a/b")
        with self.assertRaises(SourceError):
            self.svc.cloud_mkdir("/", "..")


if __name__ == "__main__":
    unittest.main()
