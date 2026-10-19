"""替换预设的护栏：只读 tacz 必须整体失败，不能半途而废还标成已应用。"""
from __future__ import annotations

import json
import os
import shutil
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

    def test_partial_move_failure_rolls_back_without_losing_files(self):
        """搬到一半失败：已搬进 tacz 的新预设文件要搬回去，重试不能丢。"""
        real_move = self.manager._move_items
        target = Path(self.manager.presets["B"]["path"])
        (target / "B2.zip").write_bytes(b"bbbb2")

        def flaky(src, dst, exclude=None, progress_callback=None):
            if Path(src) == target:
                item = target / "B.zip"
                shutil.move(str(item), str(Path(dst) / item.name))
                return [item.name]
            return real_move(src, dst, exclude, progress_callback)

        self.manager._move_items = flaky
        self.assertFalse(self.manager.apply_preset("B"))
        self.assertEqual(sorted(p.name for p in target.iterdir()),
                         ["B.zip", "B2.zip", "index.json", "version.txt"])
        self.assertEqual(sorted(p.name for p in self.tacz.iterdir()), [])
        self.assertFalse(self.manager.presets["B"]["applied"])

        self.manager._move_items = real_move
        self.assertTrue(self.manager.apply_preset("B"))
        self.assertEqual(sorted(p.name for p in self.tacz.iterdir()),
                         ["B.zip", "B2.zip"])

    def test_unowned_tacz_files_are_adopted_not_deleted(self):
        # 模拟索引/缓存损坏：没有任何 applied 标记，但 tacz 里有用户枪包
        self.manager.presets["A"]["applied"] = False
        self.manager.current_preset = None
        (self.tacz / "user_precious.zip").write_bytes(b"user-data")
        self.assertTrue(self.manager.apply_preset("B"))
        rescue = [n for n in self.manager.presets
                  if n.startswith("恢复的枪包")]
        self.assertEqual(len(rescue), 1, list(self.manager.presets))
        rescue_dir = Path(self.manager.presets[rescue[0]]["path"])
        self.assertTrue((rescue_dir / "user_precious.zip").exists())
        self.assertTrue((rescue_dir / "A.zip").exists())
        self.assertEqual(sorted(p.name for p in self.tacz.iterdir()), ["B.zip"])

    def test_rename_failure_keeps_applied_state(self):
        # 目标目录已存在（孤儿目录）→ 改名失败，但状态不能被打成“未应用”
        (self.db / "C").mkdir()
        self.assertFalse(self.manager.rename_preset("A", "C"))
        self.assertTrue(self.manager.presets["A"]["applied"])
        self.assertEqual(self.manager.current_preset, "A")
        self.assertTrue((self.tacz / "A.zip").exists())

    def test_create_preset_rejects_unsafe_names(self):
        for bad in ("../escape", "/tmp/evil", "CON", ".hidden",
                    "a/b", "x" * 81):
            self.assertFalse(self.manager.create_preset(bad), bad)
        self.assertFalse((self.pack / "escape").exists())
        self.assertFalse((self.db / ".hidden").exists())

    def test_multiple_applied_flags_are_reset_on_load(self):
        # 合并/拷贝数据库后可能出现两个 applied：加载时必须重置，避免幽灵状态
        for name in ("A", "B"):
            index = Path(self.manager.presets[name]["path"]) / "index.json"
            data = json.loads(index.read_text(encoding="utf-8"))
            data["applied"] = True
            index.write_text(json.dumps(data), encoding="utf-8")
        self.manager.load_all_presets(use_cache=False)
        self.assertFalse(any(info.get("applied")
                             for info in self.manager.presets.values()))
        self.assertIsNone(self.manager.current_preset)

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
