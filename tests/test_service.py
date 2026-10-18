"""OnlineService 门面：绑定 / 检查 / 同步 / 离线 / 记账。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_lanzou import MockLanzou
from online import diff, hashing, packing, paths
from online.errors import ManifestError, SourceError
from online.manifest import normalize
from online.provider_lanzou import MANIFEST_NAME
from online.service import OnlineService, PresetRef


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_zip(path: Path, name: str, payload: bytes) -> None:
    import zipfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, payload)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.db = base / "db"
        self.dev_root = base / "dev" / "测试预设"
        self.player_root = base / "player" / "测试预设"
        self.dev_root.mkdir(parents=True)
        self.player_root.mkdir(parents=True)

        make_zip(self.dev_root / "alpha.zip", "alpha.json", b'{"a":1}')
        write(self.dev_root / "beta" / "pack.json", b'{"b":2}')
        write(self.dev_root / "beta" / "textures" / "x.png", b"PNG" * 50)
        write(self.dev_root / "readme.txt", b"hello")

        entries = hashing.scan_local(str(self.dev_root))
        uploads: dict[str, bytes] = {}
        for entry in entries:
            if entry["type"] == "folder":
                archive = base / "upload" / entry["path"]
                packing.pack_folder(str(self.dev_root / entry["target"]),
                                    str(archive))
                uploads[entry["path"]] = archive.read_bytes()
                entry["packed_size"] = archive.stat().st_size
            else:
                uploads[entry["path"]] = (self.dev_root / entry["path"]).read_bytes()

        self.cloud_manifest = normalize({
            "name": "测试预设", "version": "2026.10.18", "generation": 4,
            "files": entries})
        uploads[MANIFEST_NAME] = json.dumps(
            self.cloud_manifest, ensure_ascii=False).encode("utf-8")

        self.cloud = MockLanzou(uploads, password="28pm")
        self.cloud.start()
        self.service = OnlineService(self.db, app_version="2.4.16")
        self.ref = PresetRef("测试预设", str(self.player_root),
                             str(self.player_root))

    def tearDown(self):
        self.cloud.stop()
        self.temp.cleanup()

    # ------------------------------------------------------------------
    def test_bind_and_source(self):
        self.assertFalse(self.service.is_bound("测试预设"))
        self.service.bind("测试预设", self.cloud.url, "28pm")
        self.assertTrue(self.service.is_bound("测试预设"))
        stored = self.service.source_of("测试预设")
        self.assertEqual(stored["lanzou"]["password"], "28pm")
        self.assertTrue(Path(self.db, paths.ONLINE_DIRNAME,
                             "sources.json").exists())

    def test_check_without_source(self):
        with self.assertRaises(SourceError):
            self.service.check(self.ref)

    def test_test_source(self):
        info = self.service.test_source(self.cloud.url, "28pm")
        self.assertTrue(info["manifest_ok"])
        self.assertEqual(info["count"], 4)

    def test_test_source_wrong_password(self):
        with self.assertRaises(SourceError):
            self.service.test_source(self.cloud.url, "nope")

    def test_check_plan(self):
        self.service.bind("测试预设", self.cloud.url, "28pm")
        plan = self.service.check(self.ref)
        self.assertEqual(plan.count_of(diff.DOWNLOAD), 3)
        self.assertEqual(plan.cloud_version, "2026.10.18")
        self.assertEqual(plan.cloud_generation, 4)
        self.assertFalse(plan.offline)

    def test_sync_end_to_end(self):
        self.service.bind("测试预设", self.cloud.url, "28pm")
        plan = self.service.check(self.ref)
        result = self.service.sync(self.ref, plan, diff.selection_of(plan))
        self.assertTrue(result.ok, result.failed)
        self.assertEqual(len(result.installed), 3)

        installed = {e["path"]: e for e in
                     hashing.scan_local(str(self.player_root))}
        self.assertEqual(set(installed), {"alpha.zip", "beta.zip", "readme.txt"})
        for entry in self.cloud_manifest["files"]:
            self.assertEqual(installed[entry["path"]]["sha256"],
                             entry["sha256"])

        index = json.loads((self.player_root / "index.json").read_text("utf-8"))
        self.assertEqual(index["name"], "测试预设")
        self.assertEqual(index["version"], "2026.10.18")
        self.assertEqual(set(index["gunpacks"]),
                         {"alpha.zip", "beta", "readme.txt"})
        self.assertEqual(index["gunpacks"]["beta"]["type"], "folder")
        self.assertEqual(
            (self.player_root / "version.txt").read_text("utf-8"), "2026.10.18")

        again = self.service.check(self.ref)
        self.assertTrue(again.is_clean, again.summary())

    def test_sync_records_source(self):
        self.service.bind("测试预设", self.cloud.url, "28pm")
        plan = self.service.check(self.ref)
        self.service.sync(self.ref, plan, diff.selection_of(plan))
        stored = self.service.source_of("测试预设")
        self.assertEqual(stored["last_version"], "2026.10.18")
        self.assertEqual(stored["last_generation"], 4)
        self.assertIn("last_sync", stored)

    def test_inspect_share(self):
        info = self.service.inspect_share(self.cloud.url, "28pm")
        self.assertEqual(info["name"], "测试预设")
        self.assertEqual(info["version"], "2026.10.18")
        self.assertEqual(info["files"], 3)
        self.assertGreater(info["total_bytes"], 0)
        self.assertEqual(len(info["manifest"]["files"]), 3)

    def test_inspect_share_wrong_password(self):
        with self.assertRaises(SourceError):
            self.service.inspect_share(self.cloud.url, "bad")

    def test_cache_tools(self):
        self.service.bind("测试预设", self.cloud.url, "28pm")
        self.service.check(self.ref)
        self.assertGreater(self.service.cache_size(), 0)
        freed = self.service.clear_caches()
        self.assertGreaterEqual(freed, 0)
        # sources.json 不能被清掉
        self.assertTrue(self.service.is_bound("测试预设"))

    def test_diagnose_without_source(self):
        result = self.service.diagnose(self.ref, role="player", deep=False)
        names = {item["name"]: item for item in result["checks"]}
        self.assertIn("已绑定分享链接", names)
        self.assertFalse(names["已绑定分享链接"]["ok"])
        self.assertFalse(result["ok"])

    def test_diagnose_with_source(self):
        self.service.bind("测试预设", self.cloud.url, "28pm")
        result = self.service.diagnose(self.ref, role="player", deep=True)
        names = {item["name"]: item for item in result["checks"]}
        self.assertTrue(names["已绑定分享链接"]["ok"])
        self.assertTrue(names["分享链接可访问"]["ok"],
                        names["分享链接可访问"])
        self.assertTrue(names["云端 manifest 可读"]["ok"],
                        names["云端 manifest 可读"])
        self.assertTrue(result["ok"], result["checks"])

    def test_diagnose_developer_without_account(self):
        self.service.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        result = self.service.diagnose(self.ref, role="developer", deep=False)
        names = {item["name"]: item for item in result["checks"]}
        self.assertTrue(names["已填云端路径"]["ok"])
        self.assertFalse(names["账号已认证"]["ok"])

    def test_cancel_returns_partial_result(self):
        """取消同步：不抛异常，返回 cancelled=True 的结果。"""
        from online.errors import CancelledError

        self.service.bind("测试预设", self.cloud.url, "28pm")
        plan = self.service.check(self.ref)

        class _CancelShare:
            def list_files(self):
                return [{"name": entry["path"],
                         "size_bytes": entry.get("packed_size") or 1,
                         "file_id": "1", "raw_id": "1"}
                        for entry in plan.cloud_entries()]

            def download(self, *args, **kwargs):
                raise CancelledError("取消")

        self.service._make_share = lambda name: _CancelShare()
        result = self.service.sync(self.ref, plan, diff.selection_of(plan))
        self.assertTrue(result.cancelled)
        self.assertEqual(result.installed, [])
        self.assertFalse(result.failed)

    def test_multi_source_fallback(self):
        """主链接失效时自动用备用链接，并记住能用的那个。"""
        dead = MockLanzou({"x.txt": b"x"}, password="")
        dead.start()
        dead_url = dead.url
        dead.stop()                      # 起完就关掉，制造"主链接失效"
        self.service.bind("测试预设", dead_url, "",
                          fallback_url=self.cloud.url,
                          fallback_password="28pm")
        plan = self.service.check(self.ref)
        self.assertEqual(plan.count_of(diff.DOWNLOAD), 3)
        record = self.service.source_of("测试预设")
        self.assertEqual(record["lanzou"]["active_url"], self.cloud.url)

    def test_offline_fallback(self):
        self.service.bind("测试预设", self.cloud.url, "28pm")
        first = self.service.check(self.ref)
        self.assertFalse(first.offline)
        self.cloud.stop()
        plan = self.service.check(self.ref)
        self.assertTrue(plan.offline)
        self.assertIn("连接", plan.source_error)
        self.assertEqual(plan.count_of(diff.DOWNLOAD), 3)

    def test_missing_manifest(self):
        empty = MockLanzou({"whatever.txt": b"x"}, password="")
        empty.start()
        try:
            self.service.bind("空源", empty.url, "")
            ref = PresetRef("空源", str(self.player_root), str(self.player_root))
            with self.assertRaises(SourceError) as ctx:
                self.service.check(ref)
            self.assertIn("发布", str(ctx.exception))
        finally:
            empty.stop()

    def test_broken_manifest(self):
        broken = MockLanzou({MANIFEST_NAME: b"{not json"}, password="")
        broken.start()
        try:
            self.service.bind("坏源", broken.url, "")
            ref = PresetRef("坏源", str(self.player_root), str(self.player_root))
            with self.assertRaises(ManifestError):
                self.service.check(ref)
        finally:
            broken.stop()

    def test_delete_local_extra(self):
        write(self.player_root / "extra.zip", b"junk")
        self.assertTrue(self.service.delete_local_extra(
            self.ref, {"path": "extra.zip", "type": "zip"}))
        self.assertFalse((self.player_root / "extra.zip").exists())

    def test_update_index_keeps_applied(self):
        write(self.player_root / "index.json",
              b'{"name":"x","applied":true,"incremental_count":2}')
        write(self.player_root / "a.zip", b"aaa")
        self.service.update_index(self.ref)
        data = json.loads((self.player_root / "index.json").read_text("utf-8"))
        self.assertTrue(data["applied"])
        self.assertEqual(data["incremental_count"], 2)
        self.assertIn("a.zip", data["gunpacks"])

    def test_recover_all_cleans_orphans(self):
        staging = Path(self.db, paths.ONLINE_DIRNAME, "staging", "孤儿")
        staging.mkdir(parents=True)
        write(staging / "junk.bin", b"x")
        notes = self.service.recover_all()
        self.assertFalse(staging.exists())
        self.assertIsInstance(notes, list)


if __name__ == "__main__":
    unittest.main()
