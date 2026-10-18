"""本地扫描 / 树摘要 / 哈希缓存。"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online import hashing


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class TreeDigestTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "gun"
        write(self.root / "a.txt", b"hello")
        write(self.root / "sub" / "b.bin", b"\x00\x01\x02")
        write(self.root / "sub" / "deep" / "c.txt", b"ccc")

    def tearDown(self):
        self.temp.cleanup()

    def test_digest_shape(self):
        digest, size, count = hashing.tree_digest(str(self.root))
        self.assertEqual(len(digest), 64)
        self.assertEqual(count, 3)
        self.assertEqual(size, 5 + 3 + 3)

    def test_digest_is_stable(self):
        first = hashing.tree_digest(str(self.root))[0]
        second = hashing.tree_digest(str(self.root))[0]
        self.assertEqual(first, second)

    def test_digest_changes_with_content(self):
        before = hashing.tree_digest(str(self.root))[0]
        write(self.root / "a.txt", b"hello!")
        after = hashing.tree_digest(str(self.root))[0]
        self.assertNotEqual(before, after)

    def test_digest_changes_with_rename(self):
        before = hashing.tree_digest(str(self.root))[0]
        os.replace(self.root / "a.txt", self.root / "renamed.txt")
        after = hashing.tree_digest(str(self.root))[0]
        self.assertNotEqual(before, after)

    def test_ignored_files_do_not_matter(self):
        before = hashing.tree_digest(str(self.root))[0]
        write(self.root / ".DS_Store", b"junk")
        write(self.root / "sub" / "x.tmp", b"junk")
        after = hashing.tree_digest(str(self.root))[0]
        self.assertEqual(before, after)

    def test_empty_folder(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        digest, size, count = hashing.tree_digest(str(empty))
        self.assertEqual(len(digest), 64)
        self.assertEqual((size, count), (0, 0))

    def test_cancel(self):
        with self.assertRaises(hashing.CancelledError):
            hashing.tree_digest(str(self.root), should_stop=lambda: True)


class ScanLocalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "preset"
        write(self.root / "alpha.zip", b"zipdata")
        write(self.root / "beta" / "one.txt", b"1")
        write(self.root / "beta" / "two.txt", b"22")
        write(self.root / "readme.txt", b"notes")
        write(self.root / "index.json", b"{}")
        write(self.root / "version.txt", b"v1")
        write(self.root / "tacz_default_gun" / "x.json", b"{}")

    def tearDown(self):
        self.temp.cleanup()

    def test_entries(self):
        entries = hashing.scan_local(str(self.root))
        by_path = {e["path"]: e for e in entries}
        self.assertEqual(set(by_path), {"alpha.zip", "beta.zip", "readme.txt"})
        self.assertEqual(by_path["alpha.zip"]["type"], "zip")
        self.assertEqual(by_path["readme.txt"]["type"], "file")
        beta = by_path["beta.zip"]
        self.assertEqual(beta["type"], "folder")
        self.assertEqual(beta["target"], "beta")
        self.assertEqual(beta["files"], 2)
        self.assertEqual(beta["size"], 3)

    def test_folder_name_collision(self):
        write(self.root / "beta.zip", b"also a zip")
        entries = hashing.scan_local(str(self.root))
        paths = {e["path"] for e in entries}
        self.assertIn("beta.zip", paths)
        self.assertIn("beta.folder.zip", paths)
        folder = next(e for e in entries if e["type"] == "folder")
        self.assertEqual(folder["target"], "beta")

    def test_missing_root(self):
        self.assertEqual(hashing.scan_local(str(self.root / "nope")), [])

    def test_sorted(self):
        entries = hashing.scan_local(str(self.root))
        keys = [e["path"].lower() for e in entries]
        self.assertEqual(keys, sorted(keys))


class HashCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "preset"
        write(self.root / "a.zip", b"aaa")
        write(self.root / "folder" / "b.txt", b"bbb")
        self.cache_path = Path(self.temp.name) / "cache.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_cache_reuse(self):
        calls = {"n": 0}
        original = hashing.sha256_file

        def counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        hashing.sha256_file = counting
        try:
            cache = hashing.HashCache(self.cache_path, root=str(self.root))
            hashing.scan_local(str(self.root), cache)
            first = calls["n"]
            self.assertEqual(first, 2)

            cache2 = hashing.HashCache(self.cache_path, root=str(self.root))
            hashing.scan_local(str(self.root), cache2)
            self.assertEqual(calls["n"], first, "第二次扫描不应该重算哈希")
        finally:
            hashing.sha256_file = original

    def test_cache_invalidates_on_change(self):
        cache = hashing.HashCache(self.cache_path, root=str(self.root))
        first = {e["path"]: e["sha256"] for e in
                 hashing.scan_local(str(self.root), cache)}
        write(self.root / "a.zip", b"changed")
        future = time.time() + 5
        os.utime(self.root / "a.zip", (future, future))
        cache2 = hashing.HashCache(self.cache_path, root=str(self.root))
        second = {e["path"]: e["sha256"] for e in
                  hashing.scan_local(str(self.root), cache2)}
        self.assertNotEqual(first["a.zip"], second["a.zip"])
        self.assertEqual(first["folder.zip"], second["folder.zip"])

    def test_cache_prunes_removed_files(self):
        cache = hashing.HashCache(self.cache_path, root=str(self.root))
        hashing.scan_local(str(self.root), cache)
        self.assertIn("folder/b.txt", cache.entries)
        (self.root / "folder" / "b.txt").unlink()
        cache2 = hashing.HashCache(self.cache_path, root=str(self.root))
        hashing.scan_local(str(self.root), cache2)
        self.assertNotIn("folder/b.txt", cache2.entries)

    def test_cache_wrong_root_discarded(self):
        cache = hashing.HashCache(self.cache_path, root=str(self.root))
        hashing.scan_local(str(self.root), cache)
        other = hashing.HashCache(self.cache_path, root=str(self.root) + "_other")
        self.assertEqual(other.entries, {})


class NameTest(unittest.TestCase):
    def test_folder_zip_name(self):
        self.assertEqual(hashing.folder_zip_name("x", set()), "x.zip")
        self.assertEqual(hashing.folder_zip_name("x", {"x.zip"}), "x.folder.zip")
        self.assertEqual(hashing.folder_zip_name("x", {"x.zip", "x.folder.zip"}),
                         "x.folder2.zip")

    def test_target_of(self):
        self.assertEqual(hashing.target_of("x.zip"), "x")
        self.assertEqual(hashing.target_of("x.folder.zip"), "x")
        self.assertEqual(hashing.target_of("x.bin"), "x.bin")


if __name__ == "__main__":
    unittest.main()
