"""一键更新/一键发布的决策合同测试（不访问真实网盘）。"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from online import diff
from pulses_web.controller import AppController


class FakePM:
    def __init__(self):
        self.presets = {
            "P": {"path": str(Path(tempfile.gettempdir()) / "P"),
                  "applied": True, "version": "v1.0.0", "gunpacks": {}},
        }

    def detach_preset(self, name, progress_callback=None):
        self.presets[name]["applied"] = False
        return True


class FakeOnline:
    def __init__(self, plan):
        self.plan = plan
        self.synced = None
        self.published = None

    def check(self, ref, role="player", on_phase=None):
        assert role == self.plan.role
        return self.plan

    def is_bound(self, name):
        return True

    def sync(self, ref, plan, selection, on_item=None, on_progress=None,
             cancel=None):
        self.synced = list(selection)
        return {"ok": True, "selection": list(selection)}

    def publish_plan(self, ref, on_phase=None):
        if on_phase:
            on_phase("准备")
        return self.plan

    def publish(self, ref, plan, selection, **kwargs):
        self.published = (list(selection), kwargs)
        return {"ok": True, "version": kwargs.get("version", "")}


class AutoActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.preset_manager = FakePM()
        self.ctrl.selected = "P"
        self.ctrl.state = lambda: {"ok": True}
        self.ctrl.apply_preset = lambda name, ctx=None: {"state": {"ok": True}}

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def plan(self, role, *actions, cloud_version="v1.2.3", offline=False):
        p = diff.Plan(role=role, cloud_version=cloud_version, offline=offline)
        for i, action in enumerate(actions):
            p.items.append(diff.DiffItem(f"f{i}.zip", action,
                                         local={"path": f"f{i}.zip", "sha256": "a"},
                                         cloud={"path": f"f{i}.zip", "sha256": "b"},
                                         size=10))
        return p

    def test_sync_auto_downloads_safe_items_and_reapplies(self):
        self.ctrl.settings.role = "player"
        self.ctrl.settings.online_sync_clean = True
        plan = self.plan("player", diff.DOWNLOAD, diff.REPAIR,
                         diff.ASK_DELETE_LOCAL, diff.BLOCKED, diff.SKIP)
        self.ctrl.online = FakeOnline(plan)
        applied = []
        self.ctrl.apply_preset = lambda name, ctx=None: (
            applied.append(name) or {"state": {"applied": True}})
        out = self.ctrl.sync_auto("P")
        self.assertEqual(set(self.ctrl.online.synced),
                         {"f0.zip", "f1.zip", "f2.zip"})
        self.assertEqual(applied, ["P"])
        self.assertTrue(out["applied"])
        self.assertIn("已重新替换", out["message"])

    def test_sync_auto_respects_keep_extras(self):
        self.ctrl.settings.role = "player"
        self.ctrl.settings.online_sync_clean = False
        self.ctrl.preset_manager.presets["P"]["applied"] = False
        self.ctrl.online = FakeOnline(self.plan(
            "player", diff.DOWNLOAD, diff.ASK_DELETE_LOCAL))
        out = self.ctrl.sync_auto("P")
        self.assertEqual(self.ctrl.online.synced, ["f0.zip"])
        self.assertFalse(out["applied"])

    def test_sync_auto_clean_plan_does_not_transfer(self):
        self.ctrl.settings.role = "player"
        self.ctrl.online = FakeOnline(self.plan("player", diff.SKIP))
        out = self.ctrl.sync_auto("P")
        self.assertIsNone(self.ctrl.online.synced)
        self.assertIn("最新", out["message"])

    def test_sync_auto_rejects_offline_plan(self):
        self.ctrl.settings.role = "player"
        self.ctrl.online = FakeOnline(self.plan("player", diff.DOWNLOAD,
                                                offline=True))
        with self.assertRaises(ValueError):
            self.ctrl.sync_auto("P")

    def test_publish_auto_uploads_only_safe_items_and_bumps_version(self):
        self.ctrl.settings.role = "developer"
        plan = self.plan("developer", diff.UPLOAD, diff.DELETE_CLOUD,
                         diff.SKIP, cloud_version="v1.2.3")
        self.ctrl.online = FakeOnline(plan)
        captured = {}

        def fake_publish(name, version, notes="", min_app="", selection=None,
                         ctx=None):
            captured.update(name=name, version=version, notes=notes,
                            selection=list(selection or []))
            return {"result": {"ok": True}, "state": {"ok": True}}

        self.ctrl.publish = fake_publish
        out = self.ctrl.publish_auto("P")
        self.assertEqual(captured["selection"], ["f0.zip"])
        self.assertEqual(captured["version"], "v1.2.4")
        self.assertIn("上传 1 项", captured["notes"])
        self.assertIn("发布完成", out["message"])

    def test_publish_auto_clean_plan_is_noop(self):
        self.ctrl.settings.role = "developer"
        self.ctrl.online = FakeOnline(self.plan("developer", diff.SKIP))
        called = []
        self.ctrl.publish = lambda *a, **k: called.append(1)
        out = self.ctrl.publish_auto("P")
        self.assertEqual(called, [])
        self.assertIn("最新", out["message"])

    def test_publish_auto_refuses_offline_plan(self):
        self.ctrl.settings.role = "developer"
        self.ctrl.online = FakeOnline(self.plan("developer", diff.UPLOAD,
                                                offline=True))
        with self.assertRaises(ValueError):
            self.ctrl.publish_auto("P")

    def test_sync_all_auto_updates_every_bound_preset(self):
        self.ctrl.settings.role = "player"
        self.ctrl.settings.online_sync_clean = True
        self.ctrl.preset_manager.presets["Q"] = {
            "path": str(Path(tempfile.gettempdir()) / "Q"),
            "applied": False, "version": "v1.0.0", "gunpacks": {},
        }
        self.ctrl.online = FakeOnline(self.plan(
            "player", diff.DOWNLOAD, diff.SKIP))
        applied = []
        self.ctrl.apply_preset = lambda name, ctx=None: (
            applied.append(name) or {"state": {"ok": True}})
        out = self.ctrl.sync_all_auto()
        self.assertEqual(len(out["result"]["updated"]), 2)
        self.assertEqual(len(applied), 1)  # 只有 applied=True 的 P 自动替换
        self.assertIn("更新 2 个", out["message"])

    def test_sync_all_auto_isolates_one_failure(self):
        self.ctrl.settings.role = "player"
        self.ctrl.preset_manager.presets["Q"] = {
            "path": str(Path(tempfile.gettempdir()) / "Q"),
            "applied": False, "version": "v1.0.0", "gunpacks": {},
        }

        class FailOne(FakeOnline):
            def check(self, ref, role="player", on_phase=None):
                if ref.name == "Q":
                    raise RuntimeError("模拟网络失败")
                return self.plan

        self.ctrl.online = FailOne(self.plan("player", diff.DOWNLOAD))
        out = self.ctrl.sync_all_auto()
        self.assertEqual(out["result"]["updated"], ["P"])
        self.assertEqual(out["result"]["failed"][0][0], "Q")
        self.assertFalse(out["result"]["ok"])

    def test_publish_all_auto_publishes_every_bound_preset(self):
        self.ctrl.settings.role = "developer"
        self.ctrl.preset_manager.presets["Q"] = {
            "path": str(Path(tempfile.gettempdir()) / "Q"),
            "applied": False, "version": "v1.0.0", "gunpacks": {},
        }
        self.ctrl.online = FakeOnline(self.plan(
            "developer", diff.UPLOAD))
        calls = []

        def fake_publish(name, version, notes="", min_app="", selection=None,
                         ctx=None):
            calls.append((name, version, list(selection or [])))
            return {"result": {"ok": True}, "state": {"ok": True}}

        self.ctrl.publish = fake_publish
        out = self.ctrl.publish_all_auto()
        self.assertEqual([c[0] for c in calls], ["P", "Q"])
        self.assertEqual(len(out["result"]["published"]), 2)
        self.assertIn("发布 2 个", out["message"])

    def test_next_version(self):
        self.assertEqual(AppController._next_version("v1.0.4"), "v1.0.5")
        self.assertEqual(AppController._next_version("2.3.9"), "v2.3.10")
        self.assertEqual(AppController._next_version(""), "v1.0.1")
        self.assertEqual(AppController._next_version("bad"), "v1.0.1")


if __name__ == "__main__":
    unittest.main()
