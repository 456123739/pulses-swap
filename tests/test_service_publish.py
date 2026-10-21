"""发布 → 分享 → 玩家同步 的完整闭环（两个本地模拟服务对接）。"""
from __future__ import annotations

import hashlib
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
from online.manifest import loads
from online.provider_lanzou import MANIFEST_NAME
from online.service import OnlineService, PresetRef


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_zip(path: Path, name: str, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, payload)


class PublishLoopTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.dev_db = base / "dev_db"
        self.dev_root = base / "dev" / "测试预设"
        self.dev_root.mkdir(parents=True)
        make_zip(self.dev_root / "alpha.zip", "alpha.json", b'{"a":1}')
        write(self.dev_root / "beta" / "pack.json", b'{"b":2}')
        write(self.dev_root / "beta" / "textures" / "x.png", b"PNG" * 80)
        write(self.dev_root / "readme.txt", b"hello")

        self.account_server = MockLanzouAccount("123456", "secret")
        self.account_server.start()

        self.dev = OnlineService(self.dev_db, app_version="2.4.16",
                                 account_base=self.account_server.base)
        self.dev_ref = PresetRef("测试预设", str(self.dev_root),
                                 str(self.dev_root))

    def tearDown(self):
        self.account_server.stop()
        self.temp.cleanup()

    def _login(self):
        return self.dev.login("123456", "secret")

    def test_login_and_restore(self):
        info = self._login()
        self.assertEqual(info["uid"], "123456")
        self.assertTrue(self.dev.has_account())
        # 记住的是登录名，不是会话 ID；界面上显示打码后的登录名
        self.assertEqual(self.dev.accounts.username, "123456")
        self.assertEqual(self.dev.account_info()["label"], "12***56")

        # 新实例用记住的凭据静默登录
        again = OnlineService(self.dev_db, app_version="2.4.16",
                              account_base=self.account_server.base)
        self.assertTrue(again.has_account())
        self.assertTrue(again.restore_account())
        self.assertEqual(again.account_info()["label"], "12***56")

    def test_account_secret_not_plaintext(self):
        self._login()
        raw = (Path(self.dev_db) / ".online" / "account.json").read_text(
            encoding="utf-8")
        data = json.loads(raw)
        self.assertNotEqual(data.get("secret"), "secret")

    def test_legacy_account_file_is_cleaned(self):
        """旧版本把蓝奏会话 ID 当昵称存：读出来要丢掉，不能当账号显示。"""
        path = Path(self.dev_db) / ".online" / "account.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "version": 1, "uid": "4654636", "nickname": "4654636",
            "secret": "x"}), encoding="utf-8")
        legacy = OnlineService(self.dev_db, app_version="2.4.16",
                               account_base=self.account_server.base)
        info = legacy.account_info()
        self.assertEqual(info["username"], "")
        self.assertEqual(info["label"], "")
        self.assertEqual(info["nickname"], "")

    def test_test_cloud_path_creates_and_lists(self):
        self._login()
        info = self.dev.test_cloud_path("test")
        self.assertEqual(info["path"], "test")
        self.assertEqual(info["files"], 0)
        self.assertFalse(info["has_manifest"])
        # 再来一次走的是"已存在"分支，不该重复建目录
        again = self.dev.test_cloud_path("test")
        self.assertEqual(again["files"], 0)

    def test_login_failure(self):
        with self.assertRaises(AuthError):
            self.dev.login("123456", "bad")

    def test_logout_forgets(self):
        self._login()
        self.dev.logout()
        self.assertFalse(self.dev.has_account())

    def test_publish_requires_account(self):
        with self.assertRaises(AuthError):
            self.dev.publish_plan(self.dev_ref)

    def test_publish_requires_cloud_path(self):
        self._login()
        with self.assertRaises(SourceError):
            self.dev.publish_plan(self.dev_ref)

    def test_publish_plan_then_publish(self):
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        self.assertEqual(plan.count_of(diff.UPLOAD), 3)
        self.assertEqual(plan.role, "developer")

        result = self.dev.publish(
            self.dev_ref, plan, diff.selection_of(plan),
            version="2026.10.18", notes="首发")
        self.assertTrue(result.ok, result.failed)
        self.assertEqual(sorted(result.uploaded),
                         ["alpha.zip", "beta.zip", "readme.txt"])
        self.assertTrue(result.share_url)
        self.assertEqual(result.generation, 1)

        record = self.dev.source_of("测试预设")
        self.assertEqual(record["last_version"], "2026.10.18")
        self.assertEqual(record["share_password"], "share")
        history = self.dev.publish_history("测试预设")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["version"], "2026.10.18")

    def _cloud_name(self, manifest, path):
        for entry in manifest.get("files") or []:
            if entry.get("path") == path:
                return entry.get("cloud") or path
        return path

    def _cloud_folder(self, name="测试预设"):
        account = self.account_server
        return account.folder_id(name, account.folder_id("PulsesSwap"))

    def test_failed_upload_keeps_old_version_downloadable(self):
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        first = self.dev.publish(self.dev_ref, plan, diff.selection_of(plan),
                                 version="v1.0.0", notes="首发")
        self.assertTrue(first.ok, first.failed)
        folder = self._cloud_folder()
        before = self.account_server.files_in(folder)
        before_manifest = loads(before[MANIFEST_NAME].decode("utf-8"), fmt="cfg")
        old_readme = self._cloud_name(before_manifest, "readme.txt")
        self.assertEqual(before[old_readme], b"hello")

        write(self.dev_root / "readme.txt", b"hello v2")
        new_readme = ("readme."
                      + hashlib.sha256(b"hello v2").hexdigest()[:8] + ".txt")
        plan = self.dev.publish_plan(self.dev_ref)
        self.account_server.state.fail_uploads.add(new_readme)
        failed = self.dev.publish(self.dev_ref, plan, diff.selection_of(plan),
                                  version="v2.0.0")
        self.assertFalse(failed.ok)

        after = self.account_server.files_in(folder)
        # 旧文件没有被提前删除，旧 manifest 也还在
        self.assertEqual(after[old_readme], b"hello")
        manifest = loads(after[MANIFEST_NAME].decode("utf-8"), fmt="cfg")
        self.assertEqual(manifest["version"], "v1.0.0")
        for entry in manifest["files"]:
            cloud_name = entry.get("cloud") or entry["path"]
            self.assertIn(cloud_name, after)

        # 玩家仍然能完整下载旧版本
        player_root = Path(self.temp.name) / "player" / "测试预设"
        player_root.mkdir(parents=True)
        player = OnlineService(Path(self.temp.name) / "player_db",
                               app_version="2.4.16",
                               account_base=self.account_server.base)
        player.bind("测试预设", first.share_url, first.share_password)
        pref = PresetRef("测试预设", str(player_root), str(player_root))
        pplan = player.check(pref)
        result = player.sync(pref, pplan, diff.selection_of(pplan))
        self.assertTrue(result.ok, result.failed)
        self.assertEqual((player_root / "readme.txt").read_bytes(), b"hello")

    def test_legacy_txt_manifest_migrates_to_cfg(self):
        """旧云端只有 _pulses_manifest.txt 时，仍能读，并在下次发布换成 .cfg。"""
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        first = self.dev.publish(self.dev_ref, plan, diff.selection_of(plan),
                                 version="v1")
        self.assertTrue(first.ok, first.failed)
        folder = self._cloud_folder()
        account = self.dev._require_account()
        files = self.account_server.files_in(folder)
        data = loads(files[MANIFEST_NAME].decode("utf-8"), fmt="cfg")
        legacy = {"schema": 1, "name": data["name"],
                  "version": data["version"], "generation": data["generation"],
                  "min_app": data["min_app"], "notes": data["notes"],
                  "generated_at": data["generated_at"],
                  "files": [{k: v for k, v in entry.items()
                             if k in ("path", "type", "target", "size",
                                      "files", "sha256", "packed_size",
                                      "cloud")}
                            for entry in data["files"]]}
        for info in account.list_files(folder):
            if info["name"] == MANIFEST_NAME:
                self.assertTrue(account.delete_file(info["id"]))
        legacy_path = Path(self.temp.name) / "_pulses_manifest.txt"
        legacy_path.write_text(json.dumps(legacy, ensure_ascii=False),
                               encoding="utf-8")
        account.upload(str(legacy_path), folder)

        plan = self.dev.publish_plan(self.dev_ref)
        self.assertEqual(plan.cloud_version, "v1")
        result = self.dev.publish(self.dev_ref, plan, diff.selection_of(plan),
                                  version="v2")
        self.assertTrue(result.ok, result.failed)
        files = self.account_server.files_in(folder)
        self.assertIn(MANIFEST_NAME, files)
        self.assertNotIn("_pulses_manifest.txt", files)
        upgraded = loads(files[MANIFEST_NAME].decode("utf-8"), fmt="cfg")
        self.assertEqual(upgraded["version"], "v2")
        self.assertEqual(upgraded["schema"], 2)
        self.assertTrue(upgraded["manifest_sha256"])

    def test_unselected_new_file_is_not_in_manifest(self):
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        self.assertTrue(self.dev.publish(self.dev_ref, plan,
                                          diff.selection_of(plan),
                                          version="v1").ok)
        write(self.dev_root / "brand_new.zip", b"new")   # 不需要是真 zip
        plan = self.dev.publish_plan(self.dev_ref)
        selection = diff.selection_of(plan) - {"brand_new.zip"}
        result = self.dev.publish(self.dev_ref, plan, selection, version="v2")
        self.assertTrue(result.ok, result.failed)
        folder = self._cloud_folder()
        files = self.account_server.files_in(folder)
        manifest = loads(files[MANIFEST_NAME].decode("utf-8"), fmt="cfg")
        paths = {e["path"] for e in manifest["files"]}
        self.assertNotIn("brand_new.zip", paths)
        for entry in manifest["files"]:
            cloud_name = entry.get("cloud") or entry["path"]
            self.assertIn(cloud_name, files)

    def test_renamed_cloud_file_is_downloadable_by_path(self):
        """云端同名被改名时，玩家按 path 落盘、按 cloud 下载。"""
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        first = self.dev.publish(self.dev_ref, plan, diff.selection_of(plan),
                                 version="v1")
        self.assertTrue(first.ok)
        write(self.dev_root / "readme.txt", b"hello v2")
        plan = self.dev.publish_plan(self.dev_ref)
        second = self.dev.publish(self.dev_ref, plan, diff.selection_of(plan),
                                  version="v2")
        self.assertTrue(second.ok, second.failed)
        folder = self._cloud_folder()
        files = self.account_server.files_in(folder)
        manifest = loads(files[MANIFEST_NAME].decode("utf-8"), fmt="cfg")
        entry = next(e for e in manifest["files"] if e["path"] == "readme.txt")
        cloud_name = entry.get("cloud") or entry["path"]
        self.assertIn(cloud_name, files)

        player_root = Path(self.temp.name) / "player2" / "测试预设"
        player_root.mkdir(parents=True)
        player = OnlineService(Path(self.temp.name) / "player2_db",
                               app_version="2.4.16",
                               account_base=self.account_server.base)
        player.bind("测试预设", second.share_url, second.share_password)
        pref = PresetRef("测试预设", str(player_root), str(player_root))
        pplan = player.check(pref)
        result = player.sync(pref, pplan, diff.selection_of(pplan))
        self.assertTrue(result.ok, result.failed)
        self.assertEqual((player_root / "readme.txt").read_bytes(), b"hello v2")

    def test_publish_updates_local_version_and_history_notes(self):
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        self.assertTrue(self.dev.publish(self.dev_ref, plan,
                                          diff.selection_of(plan),
                                          version="v1.0.0",
                                          notes="第一次说明").ok)
        index = json.loads((self.dev_root / "index.json").read_text("utf-8"))
        self.assertEqual(index["version"], "v1.0.0")

        write(self.dev_root / "readme.txt", b"hello v2")
        plan = self.dev.publish_plan(self.dev_ref)
        self.assertTrue(self.dev.publish(self.dev_ref, plan,
                                          diff.selection_of(plan),
                                          version="v2.0.0",
                                          notes="第二次说明").ok)
        index = json.loads((self.dev_root / "index.json").read_text("utf-8"))
        self.assertEqual(index["version"], "v2.0.0")
        history = self.dev.publish_history("测试预设")
        self.assertEqual(history[0]["notes"], "第二次说明")

    def test_second_publish_only_changes(self):
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        self.dev.publish(self.dev_ref, plan, diff.selection_of(plan),
                         version="1.0.0")

        write(self.dev_root / "readme.txt", b"hello again")
        plan2 = self.dev.publish_plan(self.dev_ref)
        self.assertEqual([i.path for i in plan2.items
                          if i.action == diff.UPLOAD], ["readme.txt"])
        result = self.dev.publish(self.dev_ref, plan2,
                                  diff.selection_of(plan2), version="1.1.0")
        self.assertTrue(result.ok)
        self.assertEqual(result.uploaded, ["readme.txt"])
        self.assertEqual(result.generation, 2)

    def test_full_loop_publish_then_player_sync(self):
        """开发者发布 → 玩家用分享链接同步 → 内容一致。"""
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        published = self.dev.publish(
            self.dev_ref, plan, diff.selection_of(plan),
            version="2026.10.18", notes="首发")
        self.assertTrue(published.ok, published.failed)
        self.assertTrue(published.share_url)

        base = Path(self.temp.name)
        player_db = base / "player_db"
        player_root = base / "player" / "测试预设"
        player_root.mkdir(parents=True)
        player = OnlineService(player_db, app_version="2.4.16")
        player.bind("测试预设", published.share_url,
                    published.share_password)
        player_ref = PresetRef("测试预设", str(player_root), str(player_root))

        check = player.check(player_ref)
        self.assertFalse(check.offline)
        self.assertEqual(check.count_of(diff.DOWNLOAD), 3)
        self.assertEqual(check.cloud_version, "2026.10.18")

        result = player.sync(player_ref, check, diff.selection_of(check))
        self.assertTrue(result.ok, result.failed)
        self.assertEqual(len(result.installed), 3)

        installed = {e["path"]: e for e in
                     hashing.scan_local(str(player_root))}
        expected = {e["path"]: e for e in hashing.scan_local(str(self.dev_root))}
        self.assertEqual(set(installed), set(expected))
        for path, entry in expected.items():
            self.assertEqual(installed[path]["sha256"], entry["sha256"], path)

        again = player.check(player_ref)
        self.assertTrue(again.is_clean, again.summary())

    def test_player_sees_update_after_republish(self):
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        first = self.dev.publish(self.dev_ref, plan,
                                 diff.selection_of(plan), version="1.0.0")

        base = Path(self.temp.name)
        player_root = base / "player2" / "测试预设"
        player_root.mkdir(parents=True)
        player = OnlineService(base / "player2_db", app_version="2.4.16")
        player.bind("测试预设", first.share_url, first.share_password)
        ref = PresetRef("测试预设", str(player_root), str(player_root))
        check = player.check(ref)
        player.sync(ref, check, diff.selection_of(check))

        # 开发者改一个文件再发
        write(self.dev_root / "alpha.zip", b"changed zip")
        plan2 = self.dev.publish_plan(self.dev_ref)
        self.dev.publish(self.dev_ref, plan2, diff.selection_of(plan2),
                         version="2.0.0")

        update = player.check(ref)
        self.assertEqual([i.path for i in update.items
                          if i.action == diff.DOWNLOAD], ["alpha.zip"])
        self.assertEqual(update.cloud_version, "2.0.0")
        result = player.sync(ref, update, diff.selection_of(update))
        self.assertTrue(result.ok, result.failed)
        self.assertTrue(player.check(ref).is_clean)

    def test_player_sees_deleted_gunpack(self):
        self._login()
        self.dev.set_cloud_path("测试预设", "/PulsesSwap/测试预设")
        plan = self.dev.publish_plan(self.dev_ref)
        first = self.dev.publish(self.dev_ref, plan,
                                 diff.selection_of(plan), version="1.0.0")

        base = Path(self.temp.name)
        player_root = base / "player3" / "测试预设"
        player_root.mkdir(parents=True)
        player = OnlineService(base / "player3_db", app_version="2.4.16")
        player.bind("测试预设", first.share_url, first.share_password)
        ref = PresetRef("测试预设", str(player_root), str(player_root))
        player.sync(ref, player.check(ref),
                    diff.selection_of(player.check(ref)))
        self.assertTrue((player_root / "readme.txt").exists())

        (self.dev_root / "readme.txt").unlink()
        plan2 = self.dev.publish_plan(self.dev_ref)
        # 默认保留云端多余文件，先确认它被识别成"云端多余"
        self.assertIn("readme.txt",
                      [i.path for i in plan2.items
                       if i.action == diff.DELETE_CLOUD])
        self.dev.publish(self.dev_ref, plan2,
                         diff.selection_of(plan2, include_deletes=True),
                         version="1.1.0")

        update = player.check(ref)
        extra = [i for i in update.items if i.action == diff.ASK_DELETE_LOCAL]
        self.assertEqual([i.path for i in extra], ["readme.txt"])


if __name__ == "__main__":
    unittest.main()
