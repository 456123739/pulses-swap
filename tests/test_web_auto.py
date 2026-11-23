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
                  "applied": True, "version": "v1.0.0",
                  "gunpacks": {"f0.zip": {"type": "zip"}}},
        }

    def detach_preset(self, name, progress_callback=None):
        self.presets[name]["applied"] = False
        return True


class FakeOnline:
    def __init__(self, plan, bound=True):
        self.plan = plan
        self.synced = None
        self.published = None
        self.bound = bound
        self.bind_args = None

    def check(self, ref, role="player", on_phase=None, **kwargs):
        assert role == self.plan.role
        return self.plan

    def is_bound(self, name):
        return self.bound

    def source_of(self, name):
        return {}

    def bind(self, name, url, password="", *, cloud_path="", **_kwargs):
        self.bind_args = (name, url, password, cloud_path)
        self.bound = True
        return {"lanzou": {"url": url}, "cloud_path": cloud_path}

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
            def check(self, ref, role="player", on_phase=None, **kwargs):
                if ref.name == "Q":
                    raise RuntimeError("模拟网络失败")
                return self.plan

        self.ctrl.online = FailOne(self.plan("player", diff.DOWNLOAD))
        out = self.ctrl.sync_all_auto()
        self.assertEqual(out["result"]["updated"], ["P"])
        self.assertEqual(out["result"]["failed"][0][0], "Q")
        self.assertFalse(out["result"]["ok"])

    def test_publish_new_creates_cloud_path_for_unbound_preset(self):
        self.ctrl.settings.role = "developer"
        self.ctrl.online = FakeOnline(self.plan("developer", diff.UPLOAD),
                                      bound=False)
        captured = {}

        def fake_publish(name, version, notes="", min_app="", selection=None,
                         ctx=None):
            captured.update(name=name, version=version, selection=list(selection or []))
            return {"result": {"ok": True}, "state": {"ok": True}}

        self.ctrl.publish = fake_publish
        out = self.ctrl.publish_new("P")
        self.assertEqual(self.ctrl.online.bind_args[0], "P")
        self.assertEqual(self.ctrl.online.bind_args[3], "/PulsesSwap/P")
        self.assertEqual(captured["selection"], ["f0.zip"])
        self.assertIn("云端 /PulsesSwap/P", out["message"])

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

class ApiSurfaceTests(unittest.TestCase):
    def test_auto_methods_are_exposed_to_frontend(self):
        from pulses_web.api import Api
        api = Api(SimpleNamespace(), SimpleNamespace(), SimpleNamespace())
        expected = {
            "online.sync.auto", "online.publish.auto",
            "online.sync.all", "online.publish.all",
        }
        self.assertTrue(expected.issubset(api._methods))


if __name__ == "__main__":
    unittest.main()


class PublishNotesTests(unittest.TestCase):
    """一键发布/一键上传全部要能把用户写的更新说明带下去。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.preset_manager = FakePM()
        self.ctrl.preset_manager.presets["P"]["applied"] = False
        self.ctrl.selected = "P"
        self.ctrl.state = lambda: {"ok": True}
        self.ctrl.settings.role = "developer"
        self.ctrl.apply_preset = lambda name, ctx=None: {"state": {"ok": True}}

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def _plan(self):
        p = diff.Plan(role="developer", cloud_version="v1.0.0")
        p.items.append(diff.DiffItem("f0.zip", diff.UPLOAD,
                                     local={"path": "f0.zip", "sha256": "a"},
                                     cloud={"path": "f0.zip", "sha256": "b"}))
        return p

    def test_custom_notes_reach_publish(self):
        fake = FakeOnline(self._plan())
        self.ctrl.online = fake
        self.ctrl.publish_auto("P", notes="新增两把枪")
        self.assertEqual(fake.published[1].get("notes"), "新增两把枪")

    def test_blank_notes_fall_back_to_default_text(self):
        fake = FakeOnline(self._plan())
        self.ctrl.online = fake
        self.ctrl.publish_auto("P", notes="   ")
        self.assertIn("一键发布", fake.published[1].get("notes", ""))

    def test_publish_all_forwards_notes(self):
        fake = FakeOnline(self._plan())
        self.ctrl.online = fake
        self.ctrl.publish_all_auto(notes="统一说明")
        self.assertEqual(fake.published[1].get("notes"), "统一说明")

    def test_empty_version_is_rejected(self):
        with self.assertRaises(ValueError):
            self.ctrl.save_version("P", "   ")


class FirstUploadTests(unittest.TestCase):
    """首次上传：可指定云端文件夹/版本/说明，并留下初始化步骤日志。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.preset_manager = FakePM()
        self.ctrl.preset_manager.presets["P"]["applied"] = False
        self.ctrl.selected = "P"
        self.ctrl.state = lambda: {"ok": True}
        self.ctrl.settings.role = "developer"
        self.ctrl.apply_preset = lambda name, ctx=None: {"state": {"ok": True}}
        p = diff.Plan(role="developer", cloud_version="")
        p.items.append(diff.DiffItem("f0.zip", diff.UPLOAD,
                                     local={"path": "f0.zip", "sha256": "a"},
                                     cloud=None))
        self.fake = FakeOnline(p, bound=False)
        self.ctrl.online = self.fake

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_custom_cloud_path_and_version(self):
        out = self.ctrl.publish_new("P", cloud_path="/PulsesSwap/我的预设/子目录",
                                    version="v9.9.9", notes="首次上传")
        self.assertTrue(out.get("changed"))
        self.assertEqual(self.fake.bind_args[3], "/PulsesSwap/我的预设/子目录")
        self.assertEqual(self.fake.published[1].get("version"), "v9.9.9")
        self.assertEqual(self.fake.published[1].get("notes"), "首次上传")

    def test_invalid_folder_name_rejected(self):
        with self.assertRaises(ValueError):
            self.ctrl.publish_new("P", cloud_path="/PulsesSwap/坏:名字")

    def test_init_steps_are_logged(self):
        self.ctrl.publish_new("P", cloud_path="/PulsesSwap/P")
        joined = "\n".join(str(getattr(x, "message", x)) for x in self.ctrl.logs)
        self.assertIn("步骤 1/6", joined)
        self.assertIn("初始化上传", joined)


class LastOpStatusTests(unittest.TestCase):
    """上次上传/更新失败或取消后，不能继续显示“已是最新”。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.preset_manager = FakePM()
        self.ctrl.selected = "P"
        self.ctrl.settings.role = "developer"
        self.ctrl.apply_preset = lambda name, ctx=None: {"state": {"ok": True}}

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_failed_publish_marks_last_op_failed(self):
        plan = diff.Plan(role="developer", cloud_version="v1.0.0")
        plan.items.append(diff.DiffItem("f0.zip", diff.UPLOAD,
                                        local={"path": "f0.zip", "sha256": "a"},
                                        cloud=None))
        fake = FakeOnline(plan, bound=True)
        fake.account_info = lambda: {"label": "测试账号"}

        def boom(*args, **kwargs):
            raise RuntimeError("上传失败：网络中断")
        fake.publish = boom
        self.ctrl.online = fake
        with self.assertRaises(RuntimeError):
            self.ctrl.publish_auto("P", notes="x")
        preset = next(p for p in self.ctrl.state()["presets"] if p["name"] == "P")
        self.assertFalse(preset["last_op"]["ok"])
        self.assertIn("网络中断", preset["last_op"]["message"])

    def test_cancelled_publish_marks_failed(self):
        plan = diff.Plan(role="developer", cloud_version="v1.0.0")
        plan.items.append(diff.DiffItem("f0.zip", diff.UPLOAD,
                                        local={"path": "f0.zip", "sha256": "a"},
                                        cloud=None))
        fake = FakeOnline(plan, bound=True)
        fake.account_info = lambda: {"label": "测试账号"}
        fake.publish = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("操作已取消"))
        self.ctrl.online = fake
        with self.assertRaises(RuntimeError):
            self.ctrl.publish_auto("P")
        preset = next(p for p in self.ctrl.state()["presets"] if p["name"] == "P")
        self.assertFalse(preset["last_op"]["ok"])

    def test_success_clears_failure(self):
        plan = diff.Plan(role="developer", cloud_version="v1.0.0")
        plan.items.append(diff.DiffItem("f0.zip", diff.UPLOAD,
                                        local={"path": "f0.zip", "sha256": "a"},
                                        cloud=None))
        fake = FakeOnline(plan, bound=True)
        fake.account_info = lambda: {"label": "测试账号"}
        self.ctrl.online = fake
        self.ctrl.publish_auto("P")
        preset = next(p for p in self.ctrl.state()["presets"] if p["name"] == "P")
        self.assertTrue(preset["last_op"]["ok"])


class LastOpSyncTests(unittest.TestCase):
    """玩家端：上次更新失败/取消后也要留下记录。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.preset_manager = FakePM()
        self.ctrl.preset_manager.presets["P"]["applied"] = False
        self.ctrl.selected = "P"
        self.ctrl.settings.role = "player"
        self.ctrl.apply_preset = lambda name, ctx=None: {"state": {"ok": True}}

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_failed_sync_marks_last_op(self):
        plan = diff.Plan(role="player", cloud_version="v1.0.0")
        plan.items.append(diff.DiffItem("f0.zip", diff.DOWNLOAD,
                                        local=None,
                                        cloud={"path": "f0.zip", "sha256": "b"}))
        fake = FakeOnline(plan, bound=True)
        fake.account_info = lambda: {"label": "测试账号"}
        fake.sync = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("下载中断"))
        self.ctrl.online = fake
        with self.assertRaises(RuntimeError):
            self.ctrl.sync_auto("P")
        preset = next(p for p in self.ctrl.state()["presets"] if p["name"] == "P")
        self.assertFalse(preset["last_op"]["ok"])
        self.assertEqual(preset["last_op"]["action"], "sync")


class CloudSummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.state = lambda: {"ok": True}

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_quota_is_human_readable(self):
        class FakeQuota:
            def account_quota(self):
                return {"used": 1073741824, "total": 10737418240}
        self.ctrl.online = FakeQuota()
        out = self.ctrl.cloud_quota()["quota"]
        self.assertEqual(out["used_text"], "1.0 GB")
        self.assertEqual(out["total_text"], "10.0 GB")
        self.assertEqual(out["percent"], 10.0)

    def test_cloud_share_forwards(self):
        class FakeShare:
            def cloud_share_path(self, path):
                return {"path": path, "url": "https://x/b01", "password": "p"}
        self.ctrl.online = FakeShare()
        out = self.ctrl.cloud_share("/PulsesSwap/测试")
        self.assertEqual(out["share"]["path"], "/PulsesSwap/测试")


class AuditGuardTests(unittest.TestCase):
    """审计修复：空勾选、离线计划、登录角色、成功后的状态。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.preset_manager = FakePM()
        self.ctrl.preset_manager.presets["P"]["applied"] = False
        self.ctrl.selected = "P"
        self.ctrl.state = lambda: {"ok": True}
        self.ctrl.settings.role = "developer"
        self.ctrl.apply_preset = lambda name, ctx=None: {"state": {"ok": True}}

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def _plan(self, offline=False):
        p = diff.Plan(role="developer", cloud_version="v1.0.0", offline=offline)
        p.items.append(diff.DiffItem("f0.zip", diff.UPLOAD,
                                     local={"path": "f0.zip", "sha256": "a"},
                                     cloud=None))
        return p

    def test_empty_selection_is_rejected(self):
        fake = FakeOnline(self._plan(), bound=True)
        fake.account_info = lambda: {"label": "测试"}
        self.ctrl.online = fake
        fake.publish_plan = lambda ref, on_phase=None: self._plan()
        self.ctrl.publish_plan("P")
        with self.assertRaises(ValueError):
            self.ctrl.publish("P", "v1.0.1", "", "", [])
        self.assertIsNone(fake.published)

    def test_offline_plan_cannot_publish(self):
        fake = FakeOnline(self._plan(), bound=True)
        fake.account_info = lambda: {"label": "测试"}
        self.ctrl.online = fake
        fake.publish_plan = lambda ref, on_phase=None: self._plan(offline=True)
        self.ctrl.publish_plan("P")
        with self.assertRaises(ValueError):
            self.ctrl.publish("P", "v1.0.1", "", "", ["f0.zip"])

    def test_login_does_not_switch_role(self):
        class FakeAccount:
            def login(self, *a, **k):
                return {"label": "测试"}
        self.ctrl.online = FakeAccount()
        self.ctrl.settings.role = "player"
        self.ctrl.login("u", "p")
        self.assertEqual(self.ctrl.settings.role, "player")

    def test_success_writes_clean_check(self):
        fake = FakeOnline(self._plan(), bound=True)
        fake.account_info = lambda: {"label": "测试"}
        self.ctrl.online = fake
        fake.publish_plan = lambda ref, on_phase=None: self._plan()
        self.ctrl.publish_plan("P")
        self.ctrl.state = AppController.state.__get__(self.ctrl)
        self.ctrl.publish("P", "v1.0.1", "", "", ["f0.zip"])
        preset = next(p for p in self.ctrl.state()["presets"] if p["name"] == "P")
        self.assertTrue(preset["checked_at"])
        self.assertEqual(preset["pending"], 0)

    def test_state_plan_has_preset_name(self):
        fake = FakeOnline(self._plan(), bound=True)
        fake.account_info = lambda: {"label": "测试"}
        self.ctrl.online = fake
        self.ctrl.state = AppController.state.__get__(self.ctrl)
        fake.publish_plan = lambda ref, on_phase=None: self._plan()
        self.ctrl.publish_plan("P")
        self.assertEqual(self.ctrl.state()["plan"]["preset"], "P")


class PersistenceAndGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_last_op_survives_restart(self):
        c1 = AppController(base_dir=self.base)
        c1._record_op("P", False, "publish", "网络中断")
        c1._stop_watcher()
        c2 = AppController(base_dir=self.base)
        try:
            self.assertEqual(c2._last_ops["P"]["message"], "网络中断")
        finally:
            c2._stop_watcher()

    def test_cannot_delete_bound_cloud_folder(self):
        ctrl = AppController(base_dir=self.base)
        ctrl.settings.role = "developer"
        ctrl._bound_names = lambda: ["P"]
        ctrl.online = type("Fake", (), {
            "source_of": lambda self, name: {"cloud_path": "/PulsesSwap/P"},
            "cloud_delete": lambda self, kind, obj_id: {"ok": True},
        })()
        try:
            with self.assertRaises(ValueError):
                ctrl.cloud_delete("folder", 1, "/PulsesSwap/P")
        finally:
            ctrl._stop_watcher()
