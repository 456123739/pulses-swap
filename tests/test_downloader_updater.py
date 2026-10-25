"""下载 + 安装的端到端测试（本地模拟蓝奏）。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_lanzou import MockLanzou
from online import diff, hashing, packing, updater
from online.downloader import Downloader
from online.manifest import normalize
from online.provider_lanzou import LanzouShare


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def make_zip(path: Path, name: str, payload: bytes) -> None:
    import zipfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, payload)


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.dev_root = base / "dev_preset"
        self.player_root = base / "player_preset"
        self.staging = base / "staging"
        self.upload_dir = base / "upload"
        self.player_root.mkdir(parents=True)

        make_zip(self.dev_root / "alpha.zip", "alpha.json", b'{"gun":1}')
        write(self.dev_root / "beta" / "pack.json", b'{"beta":true}')
        write(self.dev_root / "beta" / "textures" / "a.png", b"PNG" * 100)
        write(self.dev_root / "readme.txt", b"hello")
        write(self.dev_root / "index.json", b'{"ignored":true}')

        self.entries = hashing.scan_local(str(self.dev_root))
        self.assertEqual(len(self.entries), 3)

        # 模拟发布：文件夹打包，其它原样
        uploads: dict[str, bytes] = {}
        for entry in self.entries:
            if entry["type"] == "folder":
                archive = self.upload_dir / entry["path"]
                packing.pack_folder(str(self.dev_root / entry["target"]),
                                    str(archive))
                uploads[entry["path"]] = archive.read_bytes()
                entry["packed_size"] = archive.stat().st_size
                entry["packed_sha256"] = hashing.sha256_file(str(archive))
            else:
                uploads[entry["path"]] = (self.dev_root / entry["path"]).read_bytes()

        self.cloud_manifest = normalize({
            "name": "测试预设", "version": "2026.10.18", "generation": 1,
            "files": self.entries})
        self.cloud = MockLanzou(uploads, password="28pm")
        self.cloud.start()
        self.share = LanzouShare(self.cloud.url, "28pm", retries=2,
                                 sleep=lambda _s: None)

    def tearDown(self):
        self.cloud.stop()
        self.temp.cleanup()

    # ------------------------------------------------------------------
    def _sync(self, entries):
        downloader = Downloader(self.share, str(self.staging))
        results = downloader.run(entries)
        installer = updater.Installer(str(self.player_root), str(self.staging))
        for result in results:
            self.assertTrue(result.ok, f"{result.entry['path']}: {result.error}")
            installer.install(result.entry, result.staged)
        return results

    def test_full_sync(self):
        plan = diff.compare([], self.cloud_manifest, role="player")
        self.assertEqual(plan.count_of(diff.DOWNLOAD), 3)

        self._sync(plan.transfer_items)

        installed = {e["path"]: e for e in hashing.scan_local(str(self.player_root))}
        self.assertEqual(set(installed), {"alpha.zip", "beta.zip", "readme.txt"})
        for entry in self.entries:
            self.assertEqual(installed[entry["path"]]["sha256"],
                             entry["sha256"], entry["path"])

        again = diff.compare(hashing.scan_local(str(self.player_root)),
                             self.cloud_manifest, role="player")
        self.assertTrue(again.is_clean)

    def test_parallel_six_files_via_real_share(self):
        """4 线程 + 真实 LanzouShare.clone() 走一遍 mock 服务。"""
        extra = Path(self.temp.name) / "parallel_dev"
        extra.mkdir()
        for index in range(6):
            make_zip(extra / f"parallel_{index}.zip", "pack.json",
                     json.dumps({"index": index}).encode())
        entries = hashing.scan_local(str(extra))
        uploads = {entry["path"]: (extra / entry["path"]).read_bytes()
                   for entry in entries}
        cloud = MockLanzou(uploads, password="28pm")
        cloud.start()
        self.addCleanup(cloud.stop)
        share = LanzouShare(cloud.url, "28pm", retries=2,
                            sleep=lambda _s: None)
        manifest = normalize({
            "name": "并发预设", "version": "1.0", "generation": 1,
            "files": entries})
        plan = diff.compare([], manifest, role="player")
        values = []
        with tempfile.TemporaryDirectory() as staging:
            results = Downloader(share, staging, workers=4).run(
                plan.transfer_items,
                on_progress=lambda value, *_: values.append(value))
            self.assertEqual(len(results), 6)
            self.assertTrue(all(r.ok for r in results),
                            [r.error for r in results])
            self.assertEqual(values, sorted(values))
            self.assertEqual(values[-1],
                             sum(e["packed_size"] for e in entries))

    def test_second_sync_downloads_nothing(self):
        plan = diff.compare([], self.cloud_manifest, role="player")
        self._sync(plan.transfer_items)
        second = diff.compare(hashing.scan_local(str(self.player_root)),
                              self.cloud_manifest, role="player")
        self.assertEqual(second.transfer_items, [])

    def test_corrupt_file_fails_item(self):
        self.cloud.corrupt("alpha.zip")
        plan = diff.compare([], self.cloud_manifest, role="player")
        downloader = Downloader(self.share, str(self.staging))
        results = downloader.run(plan.transfer_items)
        bad = [r for r in results if not r.ok]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].entry["path"], "alpha.zip")
        self.assertIn("校验", bad[0].error)
        # 其余文件照样成功
        self.assertEqual(len([r for r in results if r.ok]), 2)

    def test_bad_packed_digest_fails_before_unpack(self):
        entry = next(e for e in self.cloud_manifest["files"]
                     if e["type"] == "folder")
        entry["packed_sha256"] = "f" * 64
        plan = diff.compare([], self.cloud_manifest, role="player")
        downloader = Downloader(self.share, str(self.staging))
        results = downloader.run(plan.transfer_items)
        bad = [r for r in results if not r.ok]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].entry["path"], entry["path"])
        self.assertIn("传输包校验", bad[0].error)
        self.assertFalse((Path(self.staging) / "new" / entry["target"]).exists())

    def test_cancel_stops(self):
        plan = diff.compare([], self.cloud_manifest, role="player")
        downloader = Downloader(self.share, str(self.staging),
                                cancel=lambda: True)
        with self.assertRaises(hashing.CancelledError):
            downloader.run(plan.transfer_items)

    def test_install_replaces_existing_folder(self):
        # 先放一份旧内容，确认安装后是新的
        write(self.player_root / "beta" / "stale.txt", b"old")
        plan = diff.compare(hashing.scan_local(str(self.player_root)),
                            self.cloud_manifest, role="player")
        self._sync([i for i in plan.transfer_items
                    if i.action == diff.DOWNLOAD])
        self.assertFalse((self.player_root / "beta" / "stale.txt").exists())
        self.assertTrue((self.player_root / "beta" / "pack.json").exists())

    def test_remove_local_goes_away(self):
        write(self.player_root / "extra.zip", b"junk")
        installer = updater.Installer(str(self.player_root), str(self.staging))
        ok = installer.remove_local({"path": "extra.zip", "type": "zip"})
        self.assertTrue(ok)
        self.assertFalse((self.player_root / "extra.zip").exists())


class InstallerRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root = base / "preset"
        self.root.mkdir()
        self.staging = base / "staging"
        self.staging.mkdir()
        self.installer = updater.Installer(str(self.root), str(self.staging))

    def tearDown(self):
        self.temp.cleanup()

    def _journal(self, ops):
        path = self.staging / "journal.json"
        path.write_text(json.dumps({"root": str(self.root), "ops": ops}),
                        encoding="utf-8")

    def test_recover_completes_swap(self):
        dest = self.root / "gun"
        temp = self.root / ".gun.pulses-new"
        old = self.root / ".gun.pulses-old"
        old.mkdir()
        write(old / "old.txt", b"old")
        temp.mkdir()
        write(temp / "new.txt", b"new")
        self._journal([{"kind": "dir", "dest": str(dest), "temp": str(temp),
                        "old": str(old), "state": "swapping"}])

        notes = self.installer.recover()
        self.assertTrue((dest / "new.txt").exists())
        self.assertFalse(old.exists())
        self.assertTrue(notes)

    def test_recover_rolls_back(self):
        dest = self.root / "gun"
        old = self.root / ".gun.pulses-old"
        old.mkdir()
        write(old / "old.txt", b"old")
        self._journal([{"kind": "dir", "dest": str(dest),
                        "temp": str(self.root / ".gun.pulses-new"),
                        "old": str(old), "state": "swapping"}])

        self.installer.recover()
        self.assertTrue((dest / "old.txt").exists())

    def test_recover_cleans_file_temp(self):
        temp = self.root / ".a.zip.pulses-new"
        write(temp, b"half")
        self._journal([{"kind": "file", "dest": str(self.root / "a.zip"),
                        "temp": str(temp)}])
        self.installer.recover()
        self.assertFalse(temp.exists())

    def test_sweep_leftovers(self):
        write(self.root / ".x.zip.pulses-old", b"junk")
        notes = self.installer.recover()
        self.assertFalse((self.root / ".x.zip.pulses-old").exists())
        self.assertTrue(any("清理" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
