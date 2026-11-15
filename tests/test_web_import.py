"""导入枪包到预设（新入口，之前没有）。"""
import tempfile
import unittest
from pathlib import Path

from pulses_web.controller import AppController


class FakePM:
    def __init__(self, root: Path):
        self.presets = {"demo": {"path": str(root), "applied": False,
                                 "version": "v1.0.0", "gunpacks": {}}}
        self.index_calls = 0
        self.saved = 0

    def update_preset_index(self, name):
        self.index_calls += 1
        return True

    def save_cache(self):
        self.saved += 1


class ImportGunpacksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ctrl = AppController(base_dir=self.root / "db")
        self.ctrl.preset_manager = FakePM(self.root / "preset")
        (self.root / "preset").mkdir()

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_copies_file_and_refreshes_index(self):
        src = self.root / "gun.zip"
        src.write_bytes(b"zip")
        out = self.ctrl.import_gunpacks("demo", [str(src)])
        self.assertEqual(out["imported"], ["gun.zip"])
        self.assertTrue((self.root / "preset" / "gun.zip").is_file())
        self.assertEqual(self.ctrl.preset_manager.index_calls, 1)
        self.assertEqual(self.ctrl.preset_manager.saved, 1)

    def test_same_name_is_skipped_not_overwritten(self):
        src = self.root / "gun.zip"
        src.write_bytes(b"new")
        (self.root / "preset" / "gun.zip").write_bytes(b"old")
        out = self.ctrl.import_gunpacks("demo", [str(src)])
        self.assertEqual(out["imported"], [])
        self.assertEqual((self.root / "preset" / "gun.zip").read_bytes(), b"old")

    def test_applied_preset_is_refused(self):
        self.ctrl.preset_manager.presets["demo"]["applied"] = True
        with self.assertRaises(ValueError):
            self.ctrl.import_gunpacks("demo", [str(self.root)])

    def test_empty_selection_is_refused(self):
        with self.assertRaises(ValueError):
            self.ctrl.import_gunpacks("demo", [])


if __name__ == "__main__":
    unittest.main()


class ReorderPresetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")

        class PM:
            def __init__(self):
                self.presets = {"a": {"path": ""}, "b": {"path": ""}, "c": {"path": ""}}
                self.saved = 0

            def save_cache(self):
                self.saved += 1

        self.ctrl.preset_manager = PM()

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_reorders_and_persists(self):
        self.ctrl.reorder_presets(["c", "a"])
        self.assertEqual(list(self.ctrl.preset_manager.presets), ["c", "a", "b"])
        self.assertEqual(self.ctrl.preset_manager.saved, 1)

    def test_unknown_names_are_ignored(self):
        self.ctrl.reorder_presets(["x", "b"])
        self.assertEqual(list(self.ctrl.preset_manager.presets), ["b", "a", "c"])


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db")

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def test_empty_preset_cannot_be_applied(self):
        root = Path(self.tmp.name) / "empty"

        class PM:
            presets = {"empty": {"path": str(root), "applied": False, "gunpacks": {}}}

            def update_preset_index(self, name):
                return True

        self.ctrl.preset_manager = PM()
        with self.assertRaises(ValueError):
            self.ctrl.apply_preset("empty")

    def test_detach_clears_applied_and_refreshes(self):
        class PM:
            def __init__(self):
                self.presets = {"p": {"path": "", "applied": True}}
                self.detached = 0

            def detach_preset(self, name):
                self.presets[name]["applied"] = False
                self.detached += 1
                return True

        self.ctrl.preset_manager = PM()
        self.ctrl.detach_preset("p")
        self.assertFalse(self.ctrl.preset_manager.presets["p"]["applied"])
        self.assertEqual(self.ctrl.preset_manager.detached, 1)
