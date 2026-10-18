"""两方比对：动作判定 / 阻塞 / 统计。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from online import diff
from online.manifest import normalize

SHA_A = "a" * 64
SHA_B = "b" * 64


def item(path, sha=SHA_A, kind="zip", size=100, **extra):
    data = {"path": path, "type": kind, "size": size, "sha256": sha,
            "packed_size": size}
    if kind == "folder":
        data["target"] = extra.pop("target", path[:-4])
    data.update(extra)
    return data


def cloud(files, **extra):
    data = {"name": "测试预设", "version": "1.2.0", "generation": 3,
            "files": files}
    data.update(extra)
    return normalize(data)


class PlayerDiffTest(unittest.TestCase):
    def test_basic_matrix(self):
        local = [item("same.zip"), item("changed.zip", SHA_A), item("local.zip")]
        remote = cloud([item("same.zip"), item("changed.zip", SHA_B),
                        item("new.zip")])
        plan = diff.compare(local, remote, role="player")
        actions = {i.path: i.action for i in plan.items}
        self.assertEqual(actions["same.zip"], diff.SKIP)
        self.assertEqual(actions["changed.zip"], diff.DOWNLOAD)
        self.assertEqual(actions["new.zip"], diff.DOWNLOAD)
        self.assertEqual(actions["local.zip"], diff.ASK_DELETE_LOCAL)

    def test_summary_and_totals(self):
        local = [item("a.zip")]
        remote = cloud([item("b.zip", size=2048), item("a.zip")])
        plan = diff.compare(local, remote, role="player")
        self.assertIn("待下载 1", plan.summary())
        self.assertEqual(plan.download_bytes, 2048)
        self.assertTrue(plan.has_changes)

    def test_clean_plan(self):
        local = [item("a.zip")]
        plan = diff.compare(local, cloud([item("a.zip")]), role="player")
        self.assertTrue(plan.is_clean)
        self.assertEqual(plan.summary(), "一致 1")

    def test_type_change_is_download(self):
        local = [item("gun.zip", kind="zip")]
        remote = cloud([item("gun.zip", kind="folder", target="gun")])
        plan = diff.compare(local, remote, role="player")
        self.assertEqual(plan.items[0].action, diff.DOWNLOAD)
        self.assertIn("类型", plan.items[0].reason)

    def test_missing_sha_means_differs(self):
        local = [{"path": "a.zip", "type": "zip", "size": 1, "sha256": ""}]
        plan = diff.compare(local, cloud([item("a.zip")]), role="player")
        self.assertEqual(plan.items[0].action, diff.DOWNLOAD)

    def test_oversize_blocked(self):
        local = []
        remote = cloud([item("big.zip", size=200 * 1024 * 1024)])
        plan = diff.compare(local, remote, role="player")
        self.assertEqual(plan.items[0].action, diff.BLOCKED)
        self.assertIn("上限", plan.items[0].reason)

    def test_min_app_blocks(self):
        remote = cloud([item("a.zip")], min_app="9.0.0")
        plan = diff.compare([], remote, role="player", app_version="2.4.16")
        self.assertTrue(plan.blocked)
        self.assertIn("9.0.0", plan.blocked[0])

    def test_min_app_ignored_for_developer(self):
        remote = cloud([item("a.zip")], min_app="9.0.0")
        plan = diff.compare([item("a.zip")], remote, role="developer",
                            app_version="2.4.16")
        self.assertFalse(plan.blocked)

    def test_default_checked(self):
        local = [item("old.zip")]
        remote = cloud([item("new.zip")])
        plan = diff.compare(local, remote, role="player")
        selected = diff.selection_of(plan)
        self.assertEqual(selected, {"new.zip"})
        with_deletes = diff.selection_of(plan, include_deletes=True)
        self.assertEqual(with_deletes, {"new.zip", "old.zip"})


class DeveloperDiffTest(unittest.TestCase):
    def test_basic_matrix(self):
        local = [item("same.zip"), item("changed.zip", SHA_B), item("local.zip")]
        remote = cloud([item("same.zip"), item("changed.zip", SHA_A),
                        item("cloud.zip")])
        plan = diff.compare(local, remote, role="developer")
        actions = {i.path: i.action for i in plan.items}
        self.assertEqual(actions["same.zip"], diff.SKIP)
        self.assertEqual(actions["changed.zip"], diff.UPLOAD)
        self.assertEqual(actions["local.zip"], diff.UPLOAD)
        self.assertEqual(actions["cloud.zip"], diff.DELETE_CLOUD)

    def test_keep_cloud_option(self):
        plan = diff.compare([], cloud([item("cloud.zip")]), role="developer",
                            allow_delete_cloud=False)
        self.assertEqual(plan.items[0].action, diff.SKIP)
        self.assertIn("保留", plan.items[0].reason)

    def test_upload_bytes(self):
        plan = diff.compare([item("a.zip", size=500)], cloud([]),
                            role="developer")
        self.assertEqual(plan.upload_bytes, 500)

    def test_folder_upload_detected(self):
        local = [item("gun.zip", kind="folder", target="gun", sha=SHA_A)]
        remote = cloud([item("gun.zip", kind="folder", target="gun",
                             sha=SHA_B)])
        plan = diff.compare(local, remote, role="developer")
        self.assertEqual(plan.items[0].action, diff.UPLOAD)


class PlanHelpersTest(unittest.TestCase):
    def test_selected_items_filters_skip(self):
        plan = diff.compare([item("a.zip")], cloud([item("a.zip")]),
                            role="player")
        self.assertEqual(plan.selected_items({"a.zip"}), [])

    def test_counts(self):
        plan = diff.compare([], cloud([item("a.zip"), item("b.zip")]),
                            role="player")
        self.assertEqual(plan.counts(), {diff.DOWNLOAD: 2})
        self.assertEqual(plan.count_of(diff.DOWNLOAD), 2)


if __name__ == "__main__":
    unittest.main()
