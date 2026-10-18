"""蓝奏解析：列表 / 密码 / 下载链路 / 人机校验 / 错误分类。"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_lanzou import MockLanzou
from online import acw
from online.errors import CancelledError, CaptchaError, SourceError
from online.provider_lanzou import LanzouShare, format_size, parse_size

TEXT = "你好，蓝奏。".encode("utf-8")
BINARY = bytes(range(256)) * 64


class ProviderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cloud = MockLanzou({"说明.txt": TEXT, "pack.bin": BINARY},
                               password="28pm")
        cls.cloud.start()

    @classmethod
    def tearDownClass(cls):
        cls.cloud.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.share = LanzouShare(self.cloud.url, "28pm", retries=2,
                                 sleep=lambda _s: None)

    def tearDown(self):
        self.temp.cleanup()

    def path(self, name="out.bin"):
        return os.path.join(self.temp.name, name)

    # ---------- 列表 ----------
    def test_list_files(self):
        files = self.share.list_files()
        self.assertEqual([f["name"] for f in files], ["pack.bin", "说明.txt"])
        self.assertEqual(files[0]["size_bytes"], len(BINARY))

    def test_wrong_password(self):
        share = LanzouShare(self.cloud.url, "bad", retries=1,
                            sleep=lambda _s: None)
        with self.assertRaises(SourceError) as ctx:
            share.list_files()
        self.assertIn("密码", str(ctx.exception))

    def test_probe(self):
        info = self.share.probe()
        self.assertEqual(info["count"], 2)
        self.assertEqual(info["total_bytes"], len(TEXT) + len(BINARY))
        self.assertFalse(info["has_manifest"])

    def test_bad_url(self):
        with self.assertRaises(SourceError):
            LanzouShare("not a url", "x")

    # ---------- 下载 ----------
    def test_download_text(self):
        target = self.path("a.txt")
        found = self.share.find_file("说明.txt")
        size = self.share.download(found["file_id"], target,
                                   raw_id=found["raw_id"])
        self.assertEqual(size, len(TEXT))
        self.assertEqual(Path(target).read_bytes(), TEXT)

    def test_download_binary(self):
        target = self.path("b.bin")
        found = self.share.find_file("pack.bin")
        self.share.download(found["file_id"], target, raw_id=found["raw_id"])
        self.assertEqual(Path(target).read_bytes(), BINARY)

    def test_download_reports_progress(self):
        seen = []
        found = self.share.find_file("pack.bin")
        self.share.download(found["file_id"], self.path(),
                            raw_id=found["raw_id"],
                            progress=lambda done, total: seen.append(done))
        self.assertTrue(seen)
        self.assertEqual(seen[-1], len(BINARY))

    def test_download_retries_on_server_error(self):
        self.cloud.fail_download("pack.bin", 1)
        found = self.share.find_file("pack.bin")
        target = self.path("retry.bin")
        self.share.download(found["file_id"], target, raw_id=found["raw_id"])
        self.assertEqual(Path(target).read_bytes(), BINARY)

    def test_download_cancel(self):
        found = self.share.find_file("pack.bin")
        with self.assertRaises(CancelledError):
            self.share.download(found["file_id"], self.path(),
                                raw_id=found["raw_id"],
                                cancel=lambda: True)

    def test_challenge_is_solved(self):
        """第一次进下载页必须过 acw 校验，否则拿不到页面。"""
        found = self.share.find_file("说明.txt")
        self.share.download(found["file_id"], self.path("c.txt"),
                            raw_id=found["raw_id"])
        self.assertTrue(self.share._acw_done)

    def test_signature_rejected(self):
        """apifile 拒绝签名时给出准确错误（websign 少了就会这样）。"""
        self.cloud.mark_webpage("pack.bin")
        try:
            found = self.share.find_file("pack.bin")
            with self.assertRaises(SourceError) as ctx:
                self.share.download(found["file_id"], self.path("w.bin"),
                                    raw_id=found["raw_id"])
            self.assertIn("签名", str(ctx.exception))
        finally:
            self.cloud.state.webpage.discard("pack.bin")

    def test_fetch_bytes(self):
        found = self.share.find_file("说明.txt")
        data = self.share.fetch_bytes(found["file_id"], raw_id=found["raw_id"])
        self.assertEqual(data, TEXT)

    def test_fetch_bytes_limit(self):
        found = self.share.find_file("pack.bin")
        with self.assertRaises(SourceError):
            self.share.fetch_bytes(found["file_id"], raw_id=found["raw_id"],
                                   limit=100)


class AcwTest(unittest.TestCase):
    def test_solve_matches_reference(self):
        # 真实页面抓到的 arg1 与算出来的 cookie（当时被服务端接受）
        arg1 = "0B9C45EC00B78C5875A0B9245910DD1738AA8F87"
        self.assertEqual(acw.solve(arg1),
                         "6ad42f6f002411945e4e845ffb7ad4ec53108b0f")

    def test_challenge_detection(self):
        body = b"<html><script>var arg1='0B9C45EC00B78C5875A0B9245910DD1738AA8F87';</script></html>"
        self.assertEqual(acw.challenge_arg1(body),
                         "0B9C45EC00B78C5875A0B9245910DD1738AA8F87")
        self.assertIsNone(acw.challenge_arg1(b"<html>hello</html>"))
        self.assertIsNone(acw.challenge_arg1(b""))

    def test_bad_length(self):
        with self.assertRaises(ValueError):
            acw.solve("ABC")


class SizeTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_size("1.5 K"), 1536)
        self.assertEqual(parse_size("131.8 K"), 134963)
        self.assertEqual(parse_size("2 M"), 2 * 1024 * 1024)
        self.assertEqual(parse_size("512 B"), 512)
        self.assertEqual(parse_size(""), 0)

    def test_format(self):
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(1536), "1.5 KB")
        self.assertEqual(format_size(0), "0 B")


if __name__ == "__main__":
    unittest.main()
