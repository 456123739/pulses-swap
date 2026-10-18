"""manifest 规范化 / 版本比较 / 落盘。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online import manifest
from online.errors import ManifestError

SHA = "a" * 64


def entry(path="a.zip", **extra):
    data = {"path": path, "type": "zip", "size": 10, "sha256": SHA}
    data.update(extra)
    return data


class NormalizeTest(unittest.TestCase):
    def test_minimal(self):
        data = manifest.normalize({"files": [entry()]})
        self.assertEqual(data["schema"], manifest.SCHEMA)
        self.assertEqual(len(data["files"]), 1)
        self.assertEqual(data["files"][0]["path"], "a.zip")
        self.assertEqual(data["files"][0]["packed_size"], 10)

    def test_schema_too_new(self):
        with self.assertRaises(ManifestError):
            manifest.normalize({"schema": manifest.SCHEMA + 1, "files": []})

    def test_missing_files(self):
        with self.assertRaises(ManifestError):
            manifest.normalize({"schema": 1})

    def test_duplicate_path_case_insensitive(self):
        with self.assertRaises(ManifestError):
            manifest.normalize({"files": [entry("A.zip"), entry("a.zip")]})

    def test_bad_paths(self):
        for bad in ("../x.zip", "a/../../b.zip", "a/b:c.zip",
                    "a//b.zip", "C:/x.zip"):
            with self.subTest(path=bad):
                with self.assertRaises(ManifestError):
                    manifest.normalize({"files": [entry(bad)]})

    def test_leading_slash_is_stripped(self):
        data = manifest.normalize({"files": [entry("/abs.zip")]})
        self.assertEqual(data["files"][0]["path"], "abs.zip")

    def test_unknown_type(self):
        with self.assertRaises(ManifestError):
            manifest.normalize({"files": [entry(type="rar")]})

    def test_bad_sha(self):
        with self.assertRaises(ManifestError):
            manifest.normalize({"files": [entry(sha256="xyz")]})

    def test_folder_target_default(self):
        data = manifest.normalize({"files": [
            {"path": "gun.zip", "type": "folder", "size": 5, "sha256": SHA}]})
        self.assertEqual(data["files"][0]["target"], "gun")

    def test_folder_target_nested_rejected(self):
        with self.assertRaises(ManifestError):
            manifest.normalize({"files": [
                {"path": "gun.zip", "type": "folder", "target": "a/b",
                 "size": 5, "sha256": SHA}]})

    def test_folder_packed_size_falls_back_to_size(self):
        data = manifest.normalize({"files": [
            {"path": "gun.zip", "type": "folder", "target": "gun",
             "size": 100, "sha256": SHA}]})
        self.assertEqual(data["files"][0]["packed_size"], 100)

    def test_sorted_by_path(self):
        data = manifest.normalize({"files": [entry("b.zip"), entry("a.zip")]})
        self.assertEqual([e["path"] for e in data["files"]], ["a.zip", "b.zip"])


class VersionTest(unittest.TestCase):
    def test_tuple(self):
        self.assertEqual(manifest.version_tuple("2.5.0"), (2, 5))
        self.assertEqual(manifest.version_tuple("2026.10.18"), (2026, 10, 18))
        self.assertEqual(manifest.version_tuple(""), (0,))

    def test_is_newer(self):
        self.assertTrue(manifest.is_newer("2.5.0", "2.4.16"))
        self.assertFalse(manifest.is_newer("2.4.16", "2.5.0"))
        self.assertFalse(manifest.is_newer("2.5.0", "2.5"))
        self.assertTrue(manifest.is_newer("2026.10.18", "2026.9.30"))


class SaveLoadTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "m.json")
            data = manifest.save({"name": "测试", "version": "1.0",
                                  "files": [entry()]}, path, generation=3)
            self.assertEqual(data["generation"], 3)
            self.assertTrue(data["generated_at"])
            loaded = manifest.load(path)
            self.assertEqual(loaded["name"], "测试")
            self.assertEqual(loaded["generation"], 3)
            self.assertEqual(loaded["files"][0]["sha256"], SHA)
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_load_broken(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "m.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            with self.assertRaises(ManifestError):
                manifest.load(path)

    def test_index_by_path(self):
        data = manifest.normalize({"files": [entry("A.zip"), entry("b.zip")]})
        index = manifest.index_by_path(data)
        self.assertEqual(set(index), {"a.zip", "b.zip"})


if __name__ == "__main__":
    unittest.main()
