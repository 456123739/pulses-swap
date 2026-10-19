"""替换预设的护栏：只读 tacz 必须整体失败，不能半途而废还标成已应用。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulses.managers import PresetManager


class _Log:
    def __init__(self):
        self.lines = []

    def log(self, message, level="INFO", **kwargs):
        self.lines.append((level, str(message)))


class ApplyGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.pack = base / "pack"
        self.tacz = self.pack / "tacz"
        self.db = self.pack / "PulsesSwap_database"
        self.tacz.mkdir(parents=True)
        self.db.mkdir(parents=True)
        self.log = _Log()
        self.manager = PresetManager(self.db, self.log, self.tacz)
        for name, payload in (("A", b"aaaa"), ("B", b"bbbb")):
            self.assertTrue(self.manager.create_preset(name, "v1.0.0"))
            folder = Path(self.manager.presets[name]["path"])
            (folder / f"{name}.zip").write_bytes(payload)
        self.manager.load_all_presets(use_cache=False)
        self.assertTrue(self.manager.apply_preset("A"))

    def tearDown(self):
        try:
            os.chmod(self.tacz, 0o700)
        except OSError:
            pass
        self.temp.cleanup()

    def test_readonly_tacz_refuses_without_touching_state(self):
        os.chmod(self.tacz, 0o500)
        ok = self.manager.apply_preset("B")
        self.assertFalse(ok)
        self.assertTrue(self.manager.presets["A"]["applied"])
        self.assertFalse(self.manager.presets["B"]["applied"])
        self.assertEqual(self.manager.current_preset, "A")
        self.assertTrue((self.tacz / "A.zip").exists())
        self.assertTrue(any("不可写" in msg for _, msg in self.log.lines))

    def test_apply_moves_everything_and_marks_state(self):
        self.assertTrue(self.manager.apply_preset("B"))
        self.assertFalse(self.manager.presets["A"]["applied"])
        self.assertTrue(self.manager.presets["B"]["applied"])
        self.assertEqual(self.manager.current_preset, "B")
        self.assertEqual(sorted(p.name for p in self.tacz.iterdir()), ["B.zip"])
        self.assertEqual(sorted(p.name for p in Path(
            self.manager.presets["B"]["path"]).iterdir()),
            ["index.json", "version.txt"])


if __name__ == "__main__":
    unittest.main()
