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
from online.errors import ManifestError, NetworkError, SourceError
from online.manifest import dumps, normalize
from online.provider_lanzou import MANIFEST_NAME, LanzouShare
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
        uploads[MANIFEST_NAME] = dumps(
            self.cloud_manifest, fmt="cfg").encode("utf-8")

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


class ShareRecordTest(unittest.TestCase):
    def test_rename_migrates_cloud_binding(self):
        temp = tempfile.TemporaryDirectory()
        try:
            service = OnlineService(Path(temp.name) / "db")
            service._remember_share("旧名字", "https://x.lanzoul.com/b1", "pw")
            service.rename_preset("旧名字", "新名字")
            moved = service.source_of("新名字")
            self.assertEqual(moved["lanzou"]["url"], "https://x.lanzoul.com/b1")
            self.assertEqual(moved["share_password"], "pw")
            self.assertEqual(service.source_of("旧名字"), {})
        finally:
            temp.cleanup()

    def test_rename_overwrites_stale_target_cache(self):
        temp = tempfile.TemporaryDirectory()
        try:
            db = Path(temp.name) / "db"
            service = OnlineService(db)
            for name, payload in (("旧预设", b"OLD"), ("新预设", b"STALE")):
                path = paths.cloud_manifest_path(db, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            service._remember_share("旧预设", "https://x.lanzoul.com/b2", "pw")
            service.rename_preset("旧预设", "新预设")
            self.assertEqual(paths.cloud_manifest_path(db, "新预设").read_bytes(),
                             b"OLD")
            self.assertFalse(paths.cloud_manifest_path(db, "旧预设").exists())
        finally:
            temp.cleanup()

    def test_rebind_drops_old_cloud_cache(self):
        temp = tempfile.TemporaryDirectory()
        try:
            db = Path(temp.name) / "db"
            service = OnlineService(db)
            service.bind("预设", "https://a.lanzoul.com/b1", "pw")
            cache = paths.cloud_manifest_path(db, "预设")
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b"old-source-manifest")
            service.bind("预设", "https://b.lanzoul.com/b2", "pw")
            self.assertFalse(cache.exists())
        finally:
            temp.cleanup()

    def test_clear_source_removes_binding(self):
        temp = tempfile.TemporaryDirectory()
        try:
            service = OnlineService(Path(temp.name) / "db")
            service._remember_share("预设", "https://x.lanzoul.com/b3", "pw")
            service.clear_source("预设")
            source = service.source_of("预设")
            self.assertNotIn("lanzou", source)
            self.assertNotIn("share_url", source)
            self.assertEqual(service.cloud_path_of("预设"), "")
        finally:
            temp.cleanup()

    def test_forget_preset_removes_binding_cache_and_staging(self):
        temp = tempfile.TemporaryDirectory()
        try:
            db = Path(temp.name) / "db"
            service = OnlineService(db)
            service._remember_share("要删的预设", "https://x.lanzoul.com/b1", "pw")
            staging = paths.staging_dir(db, "要删的预设")
            staging.mkdir(parents=True, exist_ok=True)
            (staging / "part.bin").write_bytes(b"x")
            service.forget_preset("要删的预设")
            self.assertEqual(service.source_of("要删的预设"), {})
            self.assertFalse(staging.exists())
            self.assertFalse(paths.cloud_manifest_path(db, "要删的预设").exists())
        finally:
            temp.cleanup()

    def test_remember_share_fills_source_page_fields(self):
        temp = tempfile.TemporaryDirectory()
        try:
            service = OnlineService(Path(temp.name) / "db")
            service._remember_share("测试预设", "https://x.lanzoul.com/b123",
                                    "abcd")
            source = service.source_of("测试预设")
            self.assertEqual(source["share_url"], "https://x.lanzoul.com/b123")
            self.assertEqual(source["lanzou"]["url"],
                             "https://x.lanzoul.com/b123")
            self.assertEqual(source["lanzou"]["password"], "abcd")
        finally:
            temp.cleanup()


class CloudProbeTest(unittest.TestCase):
    """云端读取不能把界面吊死：超时要收手，列目录失败不绕远路。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "db"
        self.service = OnlineService(self.db, app_version="2.5.4")

    def tearDown(self):
        self.temp.cleanup()

    def test_fetch_manifest_gives_up_on_timeout(self):
        import http.server
        import threading as _threading
        import time as _time

        class Slow(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _hang(self):
                _time.sleep(6)
                body = b"{}"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = _hang
            do_POST = _hang

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
        server.daemon_threads = True
        _threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            share = LanzouShare(f"http://127.0.0.1:{server.server_address[1]}/b123")
            started = _time.monotonic()
            with self.assertRaises(NetworkError):
                self.service._fetch_manifest_bounded(share, timeout=1.0)
            self.assertLess(_time.monotonic() - started, 3.5)
        finally:
            server.shutdown()
            server.server_close()

    def test_list_files_failure_does_not_touch_share_page(self):
        class BrokenAccount:
            def list_files(self, folder):
                raise SourceError("账号接口不通")

            def folder_share(self, folder):
                raise AssertionError("列目录失败时不该再去抓分享页")

        with self.assertRaises(SourceError):
            self.service._cloud_manifest_for_publish(
                "测试预设", BrokenAccount(), 1)

    def test_cached_manifest_used_when_list_fails(self):
        from online import manifest as manifest_mod

        cached = manifest_mod.empty_manifest("测试预设")
        cached["generation"] = 7
        self.service._save_cloud_manifest("测试预设", cached)

        class BrokenAccount:
            def list_files(self, folder):
                raise SourceError("账号接口不通")

            def folder_share(self, folder):
                raise AssertionError("不该走分享页")

        data = self.service._cloud_manifest_for_publish(
            "测试预设", BrokenAccount(), 1)
        self.assertEqual(data.get("generation"), 7)


if __name__ == "__main__":
    unittest.main()
