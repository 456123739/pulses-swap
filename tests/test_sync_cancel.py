"""同步取消：不能把本地版本/manifest 推进到云端，也不能谎报完成。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online import diff
from online.errors import CancelledError
from online.service import OnlineService, PresetRef


class _FakeDownloader:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, *args, **kwargs):
        raise CancelledError("同步已取消")


class SyncCancelTest(unittest.TestCase):
    def test_cancelled_sync_keeps_old_version_and_source_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            db = base / "db"
            root = base / "preset"
            root.mkdir()
            (root / "index.json").write_text(
                json.dumps({"name": "P", "version": "v1.0.0",
                            "gunpacks": {}, "applied": False}),
                encoding="utf-8")
            service = OnlineService(db)
            service.bind("P", "https://example.com/b123", "pwd")
            ref = PresetRef("P", str(root), str(root))
            plan = diff.Plan(
                role="player", cloud_version="v9.9.9", cloud_generation=9,
                items=[diff.DiffItem(
                    path="a.zip", action=diff.DOWNLOAD, size=10,
                    cloud={"path": "a.zip", "type": "zip", "size": 10})])
            with mock.patch("online.service.Downloader", _FakeDownloader):
                result = service.sync(ref, plan, {"a.zip"})
            self.assertTrue(result.cancelled)
            data = json.loads((root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(data.get("version"), "v1.0.0")
            source = service.source_of("P")
            self.assertEqual(source.get("last_version", ""), "")
            self.assertEqual(source.get("last_generation", 0), 0)


if __name__ == "__main__":
    unittest.main()
