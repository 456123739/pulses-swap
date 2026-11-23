"""Outcome and plan lifecycle regressions; no network or real accounts."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from online import diff
from online.service import SyncResult
from pulses_web.controller import AppController


class WebSyncOutcomes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")
        self.ctrl.settings.role = "player"
        self.ctrl.preset_manager = SimpleNamespace(presets={
            "P": {"path": self.tmp.name, "applied": False, "gunpacks": {"a.zip": {}}}})
        self.ctrl.selected = "P"
        self.ctrl.state = lambda: {"checks": dict(self.ctrl._checks),
                                   "last_ops": dict(self.ctrl._last_ops)}
        self.plan = diff.Plan(role="player", items=[
            diff.DiffItem(p, diff.DOWNLOAD, cloud={"path": p}, size=1)
            for p in ("a.zip", "b.zip")])
        self.outcome = SyncResult(preset="P", installed=["a.zip"])
        self.ctrl.online = SimpleNamespace(
            check=lambda *a, **kw: self.plan,
            sync=lambda *a, **kw: self.outcome)
        self.ctrl.check("P")

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_failed_download_never_marks_same_and_consumes_plan(self):
        self.outcome.failed = [("b.zip", "network failed")]
        out = self.ctrl.sync("P", ["a.zip", "b.zip"])
        self.assertEqual(out["result"]["failed"], [("b.zip", "network failed")])
        self.assertNotIn("P", self.ctrl._checks)
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])
        with self.assertRaises(ValueError):
            self.ctrl.sync("P", ["a.zip"])

    def test_partial_success_is_unverified_not_latest(self):
        self.ctrl.sync("P", ["a.zip"])
        self.assertNotIn("P", self.ctrl._checks)
        self.assertIn("重新检查", self.ctrl._last_ops["P"]["message"])
        self.assertNotIn("最新", self.ctrl._last_ops["P"]["message"])

    def test_cancelled_auto_restores_applied_preset_and_records_failure(self):
        info = self.ctrl.preset_manager.presets["P"]
        info["applied"] = True
        restored = []
        self.ctrl.preset_manager.detach_preset = lambda name: info.update(applied=False) or True
        self.ctrl.apply_preset = lambda name, ctx=None: restored.append(name) or {"state": {}}
        self.outcome = SyncResult(preset="P", cancelled=True)
        out = self.ctrl.sync_auto("P")
        self.assertEqual(restored, ["P"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["changed"], 0)
        self.assertIn("取消", out["message"])
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])
        self.assertNotIn("P", self.ctrl._checks)

    def test_auto_counts_actual_changes_on_partial_failure(self):
        self.outcome.failed = [("b.zip", "download failed")]
        out = self.ctrl.sync_auto("P")
        self.assertEqual(out["changed"], 1)
        self.assertFalse(out["ok"])

    def test_batch_failure_is_not_counted_as_unchanged_or_updated(self):
        self.ctrl._bound_names = lambda: ["P"]
        self.outcome.failed = [("b.zip", "network")]
        out = self.ctrl.sync_all_auto()
        self.assertFalse(out["result"]["ok"])
        self.assertEqual(out["result"]["updated"], [])
        self.assertEqual(out["result"]["unchanged"], [])
        self.assertEqual(out["result"]["failed"][0][0], "P")

    def test_blocked_only_sync_is_failure_not_latest(self):
        self.plan.items = [diff.DiffItem("large.zip", diff.BLOCKED, size=999)]
        with self.assertRaisesRegex(ValueError, "受限"):
            self.ctrl.sync_auto("P")
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])

    def test_minimum_app_blocks_auto_before_transfer(self):
        self.plan.blocked = ["需要升级应用"]
        with self.assertRaisesRegex(ValueError, "需要升级"):
            self.ctrl.sync_auto("P")
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])

    def test_cancelled_clean_sync_restores_without_success(self):
        self.plan.items = []
        info = self.ctrl.preset_manager.presets["P"]
        info["applied"] = True
        restored = []
        self.ctrl.preset_manager.detach_preset = lambda name: info.update(applied=False) or True
        self.ctrl.apply_preset = lambda name, ctx=None: restored.append(name) or {"state": {}}
        ctx = SimpleNamespace(cancelled=True, progress=lambda *a, **kw: None)
        with self.assertRaisesRegex(RuntimeError, "取消"):
            self.ctrl.sync_auto("P", ctx)
        self.assertEqual(restored, ["P"])
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])

    def test_blocked_only_publish_is_failure_not_latest(self):
        self.ctrl.settings.role = "developer"
        self.plan.role = "developer"
        self.plan.items = [diff.DiffItem("large.zip", diff.BLOCKED, size=999)]
        self.ctrl.online.publish_plan = lambda *a, **kw: self.plan
        with self.assertRaisesRegex(ValueError, "受限"):
            self.ctrl.publish_auto("P")
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])

    def test_cancelled_clean_publish_is_not_success(self):
        self.ctrl.settings.role = "developer"
        self.plan.role = "developer"
        self.plan.items = []
        self.ctrl.online.publish_plan = lambda *a, **kw: self.plan
        ctx = SimpleNamespace(cancelled=True, progress=lambda *a, **kw: None)
        with self.assertRaisesRegex(RuntimeError, "取消"):
            self.ctrl.publish_auto("P", ctx)
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])

    def test_failed_recheck_invalidates_previous_sync_plan(self):
        def fail(*a, **kw):
            raise RuntimeError("offline")
        self.ctrl.online.check = fail
        with self.assertRaises(RuntimeError):
            self.ctrl.check("P")
        self.assertIsNone(self.ctrl._plan_for("P"))
        self.assertNotIn("P", self.ctrl._checks)

    def test_failed_publish_recheck_invalidates_previous_publish_plan(self):
        self.ctrl.settings.role = "developer"
        self.ctrl.last_publish_plan = self.plan
        self.ctrl._publish_owner = self.ctrl._owner("P")
        def fail(*a, **kw):
            raise RuntimeError("offline")
        self.ctrl.online.publish_plan = fail
        with self.assertRaises(RuntimeError):
            self.ctrl.publish_plan("P")
        self.assertIsNone(self.ctrl._publish_for("P"))

    def test_transfer_exception_invalidates_plan_and_check(self):
        def fail(*a, **kw):
            raise OSError("disk full")
        self.ctrl.online.sync = fail
        with self.assertRaises(OSError):
            self.ctrl.sync("P", ["a.zip"])
        self.assertIsNone(self.ctrl._plan_for("P"))
        self.assertNotIn("P", self.ctrl._checks)
        self.assertFalse(self.ctrl._last_ops["P"]["ok"])

    def test_restart_does_not_trust_persisted_checks(self):
        self.ctrl._checks["P"] = {"summary": "已是最新"}
        self.ctrl._save_online_state()
        other = AppController(base_dir=Path(self.tmp.name) / "db")
        try:
            self.assertEqual(other._checks, {})
        finally:
            other._stop_watcher()

    def test_bound_cloud_ancestor_cannot_be_deleted(self):
        self.ctrl.settings.role = "developer"
        self.ctrl._bound_names = lambda: ["P"]
        self.ctrl.online.source_of = lambda name: {"cloud_path": "/PulsesSwap/P"}
        deleted = []
        self.ctrl.online.cloud_delete = lambda *args: deleted.append(args)
        for path in ("/PulsesSwap", "/", "/PulsesSwap/P", "/other/../PulsesSwap", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.ctrl.cloud_delete("folder", 1, path)
        self.assertEqual(deleted, [])
        self.ctrl.cloud_delete("folder", 2, "/PulsesSwap/P2")
        self.assertEqual(deleted, [("folder", 2)])

    def test_successful_publish_does_not_claim_full_equality_or_allow_replay(self):
        self.ctrl.settings.role = "developer"
        self.plan.role = "developer"
        self.plan.items = [diff.DiffItem(p, diff.UPLOAD, local={"path": p}, size=1)
                           for p in ("a.zip", "b.zip")]
        self.ctrl.online.publish_plan = lambda *a, **kw: self.plan
        self.ctrl.online.publish = lambda *a, **kw: {"ok": True, "uploaded": ["a.zip"]}
        self.ctrl.publish_plan("P")
        self.ctrl.publish("P", "v2", selection=["a.zip"])
        self.assertNotIn("P", self.ctrl._checks)
        self.assertIsNone(self.ctrl._publish_for("P"))
        with self.assertRaises(ValueError):
            self.ctrl.publish("P", "v2", selection=["a.zip"])


if __name__ == "__main__":
    unittest.main()
