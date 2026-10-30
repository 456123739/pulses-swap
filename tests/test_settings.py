"""设置默认值与旧配置迁移（完全同步 / 本地多余枪包）。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulses.managers import AppSettings


class SyncCleanSettingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "db"

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, data: dict) -> None:
        self.db.mkdir(parents=True, exist_ok=True)
        (self.db / ".settings.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> AppSettings:
        settings = AppSettings()
        settings.bind_database(self.db)
        return settings

    def test_new_database_defaults_to_full_sync(self):
        settings = self._load()
        self.assertTrue(settings.online_sync_clean)
        self.assertFalse(settings.online_sync_clean_set)
        self.assertFalse(settings.advanced_actions)

    def test_old_false_default_migrates_to_full_sync(self):
        self._write({"storage_mode": "isolated", "role": "player",
                     "online_sync_clean": False})
        settings = self._load()
        self.assertTrue(settings.online_sync_clean)

    def test_explicit_false_is_preserved(self):
        self._write({"storage_mode": "isolated", "role": "player",
                     "online_sync_clean": False,
                     "online_sync_clean_set": True})
        settings = self._load()
        self.assertFalse(settings.online_sync_clean)

    def test_advanced_actions_defaults_off_and_saves(self):
        settings = self._load()
        self.assertFalse(settings.advanced_actions)
        settings.advanced_actions = True
        self.assertTrue(settings.save())
        data = json.loads((self.db / ".settings.json").read_text("utf-8"))
        self.assertTrue(data["advanced_actions"])

    def test_toggle_marks_explicit_and_saves(self):
        settings = self._load()
        settings.online_sync_clean = False
        settings.online_sync_clean_set = True
        self.assertTrue(settings.save())
        data = json.loads((self.db / ".settings.json").read_text("utf-8"))
        self.assertFalse(data["online_sync_clean"])
        self.assertTrue(data["online_sync_clean_set"])


if __name__ == "__main__":
    unittest.main()
