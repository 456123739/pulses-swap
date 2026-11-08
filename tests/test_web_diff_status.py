"""枪包列表 / 预设条目的差异状态（新建，供 Web UI 上色用）。"""
import tempfile
import unittest
from pathlib import Path

from online import diff
from online.diff import DiffItem, Plan
from pulses_web import controller as ctl
from pulses_web.controller import AppController


def item(action, *, local=None, cloud=None, path="a.zip"):
    return DiffItem(path=path, action=action, local=local, cloud=cloud)


class DiffStatusTests(unittest.TestCase):
    def test_cloud_only_when_local_missing(self):
        self.assertEqual(ctl._diff_status(item(diff.DOWNLOAD, cloud={"path": "a"})),
                         ctl.STATUS_CLOUD_ONLY)

    def test_download_with_local_is_changed(self):
        self.assertEqual(ctl._diff_status(item(diff.DOWNLOAD, local={"path": "a"},
                                               cloud={"path": "a"})),
                         ctl.STATUS_CHANGED)

    def test_upload_maps_to_local_only_or_changed(self):
        self.assertEqual(ctl._diff_status(item(diff.UPLOAD, local={"path": "a"})),
                         ctl.STATUS_LOCAL_ONLY)
        self.assertEqual(ctl._diff_status(item(diff.UPLOAD, local={"path": "a"},
                                               cloud={"path": "a"})),
                         ctl.STATUS_CHANGED)

    def test_delete_cloud_is_cloud_only(self):
        self.assertEqual(ctl._diff_status(item(diff.DELETE_CLOUD, cloud={"path": "a"})),
                         ctl.STATUS_CLOUD_ONLY)

    def test_local_extra_and_repair_and_blocked(self):
        self.assertEqual(ctl._diff_status(item(diff.ASK_DELETE_LOCAL, local={"path": "a"})),
                         ctl.STATUS_LOCAL_ONLY)
        self.assertEqual(ctl._diff_status(item(diff.DELETE_LOCAL, local={"path": "a"})),
                         ctl.STATUS_LOCAL_ONLY)
        self.assertEqual(ctl._diff_status(item(diff.REPAIR, local={"path": "a"})),
                         ctl.STATUS_CHANGED)
        self.assertEqual(ctl._diff_status(item(diff.SKIP, local={"path": "a"},
                                               cloud={"path": "a"})),
                         ctl.STATUS_SAME)
        self.assertEqual(ctl._diff_status(item(diff.BLOCKED)), ctl.STATUS_BLOCKED)


class PlanSummaryStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.settings.role = "player"

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_summary_carries_status_and_counts(self):
        plan = Plan(role="player", items=[
            item(diff.DOWNLOAD, cloud={"path": "a"}, path="a.zip"),
            item(diff.DOWNLOAD, local={"path": "b"}, cloud={"path": "b"}, path="b.zip"),
            item(diff.ASK_DELETE_LOCAL, local={"path": "c"}, path="c.zip"),
            item(diff.SKIP, local={"path": "d"}, cloud={"path": "d"}, path="d.zip"),
        ])
        summary = self.ctrl._plan_summary(plan)
        self.assertEqual([i["status"] for i in summary["items"]],
                         [ctl.STATUS_CLOUD_ONLY, ctl.STATUS_CHANGED,
                          ctl.STATUS_LOCAL_ONLY, ctl.STATUS_SAME])
        self.assertEqual(summary["status_counts"],
                         {ctl.STATUS_CLOUD_ONLY: 1, ctl.STATUS_CHANGED: 1,
                          ctl.STATUS_LOCAL_ONLY: 1, ctl.STATUS_SAME: 1})

    def test_check_view_counts_by_role(self):
        self.ctrl._checks["p"] = {
            "role": "player",
            "status_counts": {ctl.STATUS_CLOUD_ONLY: 2, ctl.STATUS_CHANGED: 1,
                              ctl.STATUS_LOCAL_ONLY: 3, ctl.STATUS_SAME: 4},
            "summary": "待下载 3 · 本地多余 3",
            "at": 123,
        }
        view = self.ctrl._check_view("p")
        self.assertEqual((view["pending"], view["extra"]), (3, 3))
        self.assertTrue(view["needs_update"])
        self.assertEqual(view["checked_at"], 123)

        self.ctrl.settings.role = "developer"
        # 角色变了，旧的玩家检查结果不能继续用
        self.assertEqual(self.ctrl._check_view("p")["pending"], 0)

        self.ctrl._checks["p"]["role"] = "developer"
        view = self.ctrl._check_view("p")
        self.assertEqual((view["pending"], view["extra"]), (4, 2))

    def test_gunpacks_get_status_by_name(self):
        self.ctrl._checks["p"] = {
            "role": "player",
            "by_name": {"a.zip": ctl.STATUS_CHANGED, "b.zip": ctl.STATUS_CLOUD_ONLY},
        }
        self.ctrl.selected = "p"
        self.ctrl.gunpacks = lambda: [{"name": "a.zip"}, {"name": "b.zip"},
                                      {"name": "unknown.zip"}]
        rows = self.ctrl._gunpacks_with_status()
        self.assertEqual([r["status"] for r in rows],
                         [ctl.STATUS_CHANGED, ctl.STATUS_CLOUD_ONLY, ""])
        self.assertEqual(self.ctrl._gunpack_summary()[ctl.STATUS_CHANGED], 1)


class StateEnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.settings.role = "player"

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_presets_expose_pending_and_needs_update(self):
        class FakePM:
            presets = {
                "a": {"version": "v1", "applied": False, "gunpacks": {"x": 1}},
                "b": {"version": "v1", "applied": False, "gunpacks": {}},
            }

            def get_current_gunpacks_for_preset(self, name):
                return {"x.zip": {"type": "zip"}} if name == "a" else {}

        self.ctrl.preset_manager = FakePM()
        self.ctrl.selected = "a"
        self.ctrl.online = None
        self.ctrl._checks["a"] = {
            "role": "player",
            "status_counts": {ctl.STATUS_CLOUD_ONLY: 1, ctl.STATUS_CHANGED: 2},
            "by_name": {"x.zip": ctl.STATUS_CHANGED},
            "summary": "待下载 3", "at": 9,
        }
        state = self.ctrl.state()
        a = next(p for p in state["presets"] if p["name"] == "a")
        b = next(p for p in state["presets"] if p["name"] == "b")
        self.assertEqual(a["pending"], 3)
        self.assertTrue(a["needs_update"])
        self.assertFalse(b["needs_update"])
        self.assertEqual(state["gunpacks"][0]["status"], ctl.STATUS_CHANGED)
        self.assertEqual(state["gunpack_summary"][ctl.STATUS_CHANGED], 1)


if __name__ == "__main__":
    unittest.main()
