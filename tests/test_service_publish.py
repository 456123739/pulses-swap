"""发布 → 分享 → 玩家同步 的完整闭环（两个本地模拟服务对接）。"""
from __future__ import annotations

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

        # 新实例用记住的凭据静默登录
        again = OnlineService(self.dev_db, app_version="2.4.16",
                              account_base=self.account_server.base)
        self.assertTrue(again.has_account())
        self.assertTrue(again.restore_account())

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
