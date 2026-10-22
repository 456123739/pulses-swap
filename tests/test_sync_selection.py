"""玩家「更新」默认完全同步：本地多余枪包默认进入删除选择。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online import diff
from online.manifest import normalize
from pulses.ui.online import OnlineMixin

SHA_A = "a" * 64
SHA_B = "b" * 64


def entry(path, sha=SHA_A):
    return {"path": path, "type": "zip", "size": 100, "sha256": sha,
            "packed_size": 100}


class FakeApp:
    def __init__(self, clean: bool):
        self.settings = SimpleNamespace(online_sync_clean=clean)
        self.online = object()
        self.is_developer = False
        self.is_applying = False
        self.selection = None
        self.plan = diff.compare(
            [entry("old.zip")],
            normalize({"name": "p", "version": "v1", "files": [
                entry("new.zip", SHA_B)]}),
            role="player")

    def _online_state(self, _name):
        return {"plan": self.plan}

    def toast(self, *_args, **_kwargs):
        pass

    def _run_sync(self, _name, _plan, selection):
        self.selection = set(selection)
        return True


class FullSyncSelectionTest(unittest.TestCase):
    def test_default_includes_local_extras(self):
        app = FakeApp(True)
        self.assertTrue(OnlineMixin._sync_now(app, "p"))
        self.assertEqual(app.selection, {"new.zip", "old.zip"})

    def test_keep_mode_excludes_local_extras(self):
        app = FakeApp(False)
        self.assertTrue(OnlineMixin._sync_now(app, "p"))
        self.assertEqual(app.selection, {"new.zip"})


if __name__ == "__main__":
    unittest.main()
