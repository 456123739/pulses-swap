"""并发下载引擎：多线程真正重叠、结果顺序不变。"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online.downloader import Downloader


class SlowShare:
    """线程安全的假分享：每个下载睡 120ms，用来观察重叠。"""

    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls = []

    def clone(self):
        return self

    def list_files(self):
        return [{"name": name, "size_bytes": len(data),
                 "file_id": name, "raw_id": name}
                for name, data in self.files.items()]

    def download(self, file_id, target, *, raw_id=None, progress=None,
                 cancel=None, expected_size=None):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(file_id)
        try:
            time.sleep(0.12)
            data = self.files[file_id]
            Path(target).parent.mkdir(parents=True, exist_ok=True)
            Path(target).write_bytes(data)
            if progress is not None:
                progress(len(data), len(data))
            return len(data)
        finally:
            with self.lock:
                self.active -= 1


def entry(name: str, data: bytes) -> dict:
    return {"path": name, "type": "zip", "size": len(data),
            "packed_size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


class ParallelDownloaderTest(unittest.TestCase):
    def test_parallel_overlap_and_order(self):
        files = {f"gun_{i}.zip": f"payload-{i}".encode() * 40
                 for i in range(4)}
        entries = [entry(name, data) for name, data in files.items()]
        share = SlowShare(files)
        with tempfile.TemporaryDirectory() as temp:
            downloader = Downloader(share, temp, workers=4)
            started = time.perf_counter()
            results = downloader.run(entries)
            elapsed = time.perf_counter() - started
        self.assertEqual([r.entry["path"] for r in results],
                         [e["path"] for e in entries])
        self.assertTrue(all(r.ok for r in results), [r.error for r in results])
        self.assertGreaterEqual(share.max_active, 2)
        # 4 个 120ms 串行至少 0.48s；并发应明显短于它
        self.assertLess(elapsed, 0.45, elapsed)

    def test_single_worker_still_works(self):
        files = {"a.zip": b"a" * 100, "b.zip": b"b" * 100}
        entries = [entry(name, data) for name, data in files.items()]
        share = SlowShare(files)
        with tempfile.TemporaryDirectory() as temp:
            results = Downloader(share, temp, workers=1).run(entries)
        self.assertTrue(all(r.ok for r in results))
        self.assertEqual(share.max_active, 1)


if __name__ == "__main__":
    unittest.main()

class ParallelCancelTest(unittest.TestCase):
    def test_parallel_cancel(self):
        from online.errors import CancelledError
        files = {f"{i}.zip": b"x" * 100 for i in range(6)}
        entries = [entry(name, data) for name, data in files.items()]
        share = SlowShare(files)
        with tempfile.TemporaryDirectory() as temp:
            downloader = Downloader(share, temp, workers=4,
                                    cancel=lambda: True)
            with self.assertRaises(CancelledError):
                downloader.run(entries)
