"""一键更新/发布共享执行器的回归测试。"""
import unittest
from types import SimpleNamespace

from online import diff
from pulses.auto_actions import AutoActions, next_version


class FakePM:
    def __init__(self):
        self.presets = {
            "P": {"path": "/tmp/P", "applied": True, "version": "v1.2.3"},
            "Q": {"path": "/tmp/Q", "applied": False, "version": "v1.0.0"},
        }
        self.detached = []
        self.applied = []

    def detach_preset(self, name):
        self.detached.append(name)
        self.presets[name]["applied"] = False
        return True

    def apply_preset(self, name):
        self.applied.append(name)
        self.presets[name]["applied"] = True
        return True


class FakeService:
    def __init__(self, plan, publish_ok=True):
        self.plan = plan
        self.publish_ok = publish_ok
        self.synced = None
        self.published = None

    def is_bound(self, name):
        return name in ("P", "Q")

    def cloud_path_of(self, name):
        return ""

    def check(self, ref, role="player", on_phase=None):
        assert role == "player"
        return self.plan

    def publish_plan(self, ref, on_phase=None):
        return self.plan

    def sync(self, ref, plan, selection, on_progress=None, cancel=None):
        self.synced = list(selection)
        return SimpleNamespace(ok=True, failed=[], cancelled=False,
                               summary="ok", selection=list(selection))

    def publish(self, ref, plan, selection, **kwargs):
        self.published = (list(selection), kwargs)
        return SimpleNamespace(ok=self.publish_ok, failed=[], cancelled=False,
                               summary="published", version=kwargs.get("version"),
                               generation=1, bytes_uploaded=10,
                               uploaded=list(selection), share_url="")


class AutoActionsTests(unittest.TestCase):
    def setUp(self):
        self.pm = FakePM()
        self.settings = SimpleNamespace(online_sync_clean=True)
        self.calls = []

    def plan(self, role, *actions, version="v1.2.3"):
        p = diff.Plan(role=role, cloud_version=version)
        for i, action in enumerate(actions):
            p.items.append(diff.DiffItem(
                f"f{i}.zip", action, local={"path": f"f{i}.zip"},
                cloud={"path": f"f{i}.zip"}, size=10))
        return p

    def runner(self, service):
        return AutoActions(
            service, self.pm, self.settings,
            ref_for=lambda name: SimpleNamespace(name=name,
                                                path=self.pm.presets[name]["path"],
                                                root=self.pm.presets[name]["path"],
                                                applied=False),
            apply_preset=lambda name: self.pm.apply_preset(name),
            log=lambda *a, **k: self.calls.append(("log", a)),
            progress=lambda *a: self.calls.append(("progress", a)))

    def test_sync_one_detaches_full_sync_and_reapplies(self):
        service = FakeService(self.plan(
            "player", diff.DOWNLOAD, diff.REPAIR, diff.ASK_DELETE_LOCAL,
            diff.DELETE_CLOUD, diff.BLOCKED, diff.SKIP))
        out = self.runner(service).sync_one("P")
        self.assertEqual(self.pm.detached, ["P"])
        self.assertEqual(set(service.synced), {"f0.zip", "f1.zip", "f2.zip"})
        self.assertEqual(self.pm.applied, ["P"])
        self.assertEqual(out["changed"], 3)

    def test_sync_one_respects_keep_extras(self):
        self.settings.online_sync_clean = False
        service = FakeService(self.plan(
            "player", diff.DOWNLOAD, diff.ASK_DELETE_LOCAL))
        self.runner(service).sync_one("Q")
        self.assertEqual(service.synced, ["f0.zip"])

    def test_publish_one_bumps_version_and_preserves_cloud_extras(self):
        plan = self.plan("developer", diff.UPLOAD, diff.UPLOAD,
                         diff.DELETE_CLOUD, version="v1.2.3")
        service = FakeService(plan)
        self.pm.presets["P"]["applied"] = True
        out = self.runner(service).publish_one("P")
        self.assertEqual(out["version"], "v1.2.4")
        self.assertEqual(len(service.published[0]), 2)
        self.assertNotIn("f2.zip", service.published[0])

    def test_run_all_isolates_failure_and_continues(self):
        class S(FakeService):
            def sync(self, ref, plan, selection, on_progress=None, cancel=None):
                if ref.name == "P":
                    raise RuntimeError("boom")
                return super().sync(ref, plan, selection,
                                    on_progress=on_progress, cancel=cancel)
        service = S(self.plan("player", diff.DOWNLOAD))
        out = self.runner(service).run_all("sync", ["P", "Q"])
        self.assertEqual(out["failed"][0][0], "P")
        self.assertIn("Q", out["changed"])

    def test_next_version(self):
        self.assertEqual(next_version("v1.2.3"), "v1.2.4")
        self.assertEqual(next_version("1.9.9"), "v1.9.10")
        self.assertEqual(next_version(""), "v1.0.1")


if __name__ == "__main__":
    unittest.main()
