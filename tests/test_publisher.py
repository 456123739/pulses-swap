"""发布端：认证 / 建目录 / 打包上传 / 覆盖 / 删云端 / manifest 最后替换。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_lanzou_account import MockLanzouAccount
from online import diff, hashing
from online.errors import AuthError, SourceError
from online.manifest import normalize
from online.provider_lanzou import MANIFEST_NAME
from online.provider_lanzou_account import LanzouAccount
from online.publisher import Publisher


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_zip(path: Path, name: str, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, payload)


class PublisherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "dev" / "测试预设"
        self.staging = base / "staging"
        self.root.mkdir(parents=True)
        make_zip(self.root / "alpha.zip", "alpha.json", b'{"a":1}')
        write(self.root / "beta" / "pack.json", b'{"b":2}')
        write(self.root / "readme.txt", b"hello")

        self.server = MockLanzouAccount("123456", "secret")
        self.server.start()
        self.account = LanzouAccount(base=self.server.base)
        self.account.login("123456", "secret")
        self.folder = self.account.ensure_path("/PulsesSwap/测试预设")

    def tearDown(self):
        self.server.stop()
        self.temp.cleanup()

    # ---------- 工具 ----------
    def entries(self):
        return hashing.scan_local(str(self.root))

    def cloud_manifest(self):
        files = self.server.files_in(self.folder)
        raw = files.get(MANIFEST_NAME)
        return normalize(json.loads(raw.decode("utf-8"))) if raw else None

    def publish(self, *, version="1.0.0", selection=None, notes="",
                generation=0, cancel=None):
        entries = self.entries()
        cloud = self.cloud_manifest() or normalize({"files": []})
        plan = diff.compare(entries, cloud, role="developer")
        if selection is None:
            selection = diff.selection_of(plan, include_deletes=True)
        publisher = Publisher(self.account, str(self.staging), str(self.root),
                              cancel=cancel)
        result = publisher.publish(
            folder_id=self.folder, plan=plan, entries=entries,
            selection=selection, version=version, notes=notes,
            name="测试预设",
            previous_generation=cloud.get("generation") or generation)
        return result, plan

    def _rewrite_cloud_manifest(self, data: dict) -> None:
        """把改过的 manifest 塞回云端（模拟"上次发布留下的记录"）。"""
        for info in self.account.list_files(self.folder):
            if info["name"] == MANIFEST_NAME:
                self.account.delete_file(info["id"])
        path = Path(self.temp.name) / MANIFEST_NAME
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.account.upload(str(path), self.folder)

    # ---------- 用例 ----------
    def test_login(self):
        self.assertTrue(self.account.logged_in)
        self.assertEqual(self.account.uid, "123456")

    def test_login_wrong_password(self):
        account = LanzouAccount(base=self.server.base)
        with self.assertRaises(AuthError):
            account.login("123456", "bad")

    def test_ensure_path_is_idempotent(self):
        again = self.account.ensure_path("/PulsesSwap/测试预设")
        self.assertEqual(again, self.folder)
        self.assertIsNotNone(self.server.folder_id("PulsesSwap"))
        self.assertIsNotNone(self.server.folder_id("测试预设",
                                                   self.server.folder_id("PulsesSwap")))

    def test_first_publish(self):
        result, plan = self.publish(version="2026.10.18", notes="首发")
        self.assertTrue(result.ok, result.failed)
        self.assertEqual(sorted(result.uploaded),
                         ["alpha.zip", "beta.zip", "readme.txt"])
        self.assertEqual(result.generation, 1)
        self.assertTrue(result.share_url)

        files = self.server.files_in(self.folder)
        self.assertEqual(set(files),
                         {"alpha.zip", "beta.zip", "readme.txt", MANIFEST_NAME})

        manifest = self.cloud_manifest()
        self.assertEqual(manifest["version"], "2026.10.18")
        self.assertEqual(manifest["generation"], 1)
        self.assertEqual(manifest["notes"], "首发")
        by_path = {e["path"]: e for e in manifest["files"]}
        self.assertEqual(by_path["beta.zip"]["type"], "folder")
        self.assertEqual(by_path["beta.zip"]["target"], "beta")
        self.assertGreater(by_path["beta.zip"]["packed_size"], 0)

        # 打出来的包能被解回去，且树摘要对得上
        data = files["beta.zip"]
        archive = Path(self.temp.name) / "beta.zip"
        archive.write_bytes(data)
        target = Path(self.temp.name) / "unpacked"
        from online import packing
        packing.unpack_to(str(archive), str(target))
        self.assertEqual(hashing.tree_digest(str(target))[0],
                         by_path["beta.zip"]["sha256"])

    def test_incremental_publish(self):
        first, _ = self.publish(version="1.0.0")
        self.assertTrue(first.ok)
        write(self.root / "readme.txt", b"hello v2")
        result, plan = self.publish(version="1.1.0")
        self.assertTrue(result.ok, result.failed)
        self.assertEqual(result.uploaded, ["readme.txt"])
        self.assertEqual(result.generation, 2)
        self.assertEqual(self.cloud_manifest()["version"], "1.1.0")

    def test_unchanged_publish_uploads_only_manifest(self):
        self.publish(version="1.0.0")
        result, plan = self.publish(version="1.0.1")
        self.assertTrue(result.ok)
        self.assertEqual(result.uploaded, [])
        self.assertEqual(result.generation, 2)

    def test_delete_cloud_extra(self):
        self.publish(version="1.0.0")
        # 让云端 manifest 里多一条本地没有的记录，并在云端真的放上这个文件
        manifest = self.cloud_manifest()
        manifest["files"].append({"path": "stale.zip", "type": "zip",
                                  "size": 3, "sha256": "c" * 64,
                                  "packed_size": 3})
        self._rewrite_cloud_manifest(manifest)
        self.server.state.create_file("stale.zip", self.folder, b"old")

        result, plan = self.publish(version="1.0.1")
        self.assertIn("stale.zip", result.deleted)
        self.assertNotIn("stale.zip", self.server.files_in(self.folder))

    def test_keep_cloud_extra(self):
        self.publish(version="1.0.0")
        manifest = self.cloud_manifest()
        manifest["files"].append({"path": "stale.zip", "type": "zip",
                                  "size": 3, "sha256": "c" * 64,
                                  "packed_size": 3})
        self._rewrite_cloud_manifest(manifest)
        entries = self.entries()
        cloud = self.cloud_manifest()
        plan = diff.compare(entries, cloud, role="developer",
                            allow_delete_cloud=False)
        self.assertNotIn(diff.DELETE_CLOUD, [i.action for i in plan.items])

    def test_upload_failure_keeps_manifest(self):
        self.publish(version="1.0.0")
        before = self.cloud_manifest()
        self.server.state.fail_uploads.add("readme.txt")
        write(self.root / "readme.txt", b"broken upload")
        result, plan = self.publish(version="2.0.0")
        self.assertFalse(result.ok)
        self.assertEqual(result.failed[0][0], "readme.txt")
        after = self.cloud_manifest()
        self.assertEqual(after["version"], before["version"])
        self.assertEqual(after["generation"], before["generation"])

    def test_rename_guard(self):
        self.server.state.rename_uploads.add("readme.txt")
        result, plan = self.publish(version="1.0.0")
        self.assertFalse(result.ok)
        self.assertTrue(any("改名" in message
                            for _path, message in result.failed))
        files = self.server.files_in(self.folder)
        self.assertNotIn("readme(1).txt", files)

    def test_cancel(self):
        from online.errors import CancelledError
        with self.assertRaises(CancelledError):
            self.publish(cancel=lambda: True)

    def test_packed_size_reused_for_unchanged_folder(self):
        self.publish(version="1.0.0")
        first = {e["path"]: e for e in self.cloud_manifest()["files"]}
        result, plan = self.publish(version="1.0.1")
        self.assertTrue(result.ok)
        second = {e["path"]: e for e in self.cloud_manifest()["files"]}
        self.assertEqual(first["beta.zip"]["packed_size"],
                         second["beta.zip"]["packed_size"])

    def test_delete_requires_login(self):
        account = LanzouAccount(base=self.server.base)
        with self.assertRaises(AuthError):
            account.delete_file(1)


if __name__ == "__main__":
    unittest.main()
