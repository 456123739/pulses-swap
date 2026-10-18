"""打包 / 解包 / 校验。"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online import hashing, packing
from online.errors import PackError


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "gun"
        write(self.root / "pack.json", b'{"a":1}')
        write(self.root / "textures" / "a.png", b"PNGDATA")
        write(self.root / "textures" / "b.png", b"PNGDATA2")
        write(self.root / ".DS_Store", b"junk")
        self.zip = Path(self.temp.name) / "gun.zip"

    def tearDown(self):
        self.temp.cleanup()

    def test_pack_is_deterministic(self):
        packing.pack_folder(str(self.root), str(self.zip))
        first = file_sha(self.zip)
        other = Path(self.temp.name) / "gun2.zip"
        packing.pack_folder(str(self.root), str(other))
        self.assertEqual(first, file_sha(other))

    def test_pack_ignores_junk(self):
        packing.pack_folder(str(self.root), str(self.zip))
        with zipfile.ZipFile(self.zip) as zf:
            names = zf.namelist()
        self.assertNotIn(".DS_Store", names)
        self.assertIn("pack.json", names)
        self.assertIn("textures/a.png", names)

    def test_pack_empty_folder(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        with self.assertRaises(PackError):
            packing.pack_folder(str(empty), str(self.zip))

    def test_unpack_restores_digest(self):
        before = hashing.tree_digest(str(self.root))[0]
        packing.pack_folder(str(self.root), str(self.zip))
        target = Path(self.temp.name) / "out"
        count = packing.unpack_to(str(self.zip), str(target))
        self.assertEqual(count, 3)
        after = hashing.tree_digest(str(target))[0]
        self.assertEqual(before, after)

    def test_unpack_rejects_traversal(self):
        evil = Path(self.temp.name) / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("../escape.txt", b"bad")
        with self.assertRaises(PackError):
            packing.unpack_to(str(evil), str(Path(self.temp.name) / "out2"))
        self.assertFalse((Path(self.temp.name) / "escape.txt").exists())

    def test_unpack_rejects_bomb(self):
        bomb = Path(self.temp.name) / "bomb.zip"
        with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("big.bin", b"\0" * 200000)
        with self.assertRaises(PackError):
            packing.unpack_to(str(bomb), str(Path(self.temp.name) / "out3"),
                              expected_size=100)

    def test_unpack_bad_zip(self):
        broken = Path(self.temp.name) / "broken.zip"
        broken.write_bytes(b"not a zip at all")
        with self.assertRaises(PackError):
            packing.unpack_to(str(broken), str(Path(self.temp.name) / "out4"))

    def test_verify_zip_detects_corruption(self):
        payload = b"PAYLOAD-TO-CORRUPT-" * 64
        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("data.bin", payload)
        raw = bytearray(self.zip.read_bytes())
        offset = raw.find(payload[:16])
        self.assertGreater(offset, 0)
        raw[offset] ^= 0xFF
        self.zip.write_bytes(bytes(raw))
        with self.assertRaises(PackError):
            packing.verify_zip(str(self.zip))

    def test_progress_and_cancel(self):
        seen = []
        packing.pack_folder(str(self.root), str(self.zip),
                            progress=lambda done, total, name: seen.append(name))
        self.assertEqual(len(seen), 3)
        with self.assertRaises(PackError):
            packing.pack_folder(str(self.root), str(self.zip),
                                should_stop=lambda: True)


if __name__ == "__main__":
    unittest.main()
