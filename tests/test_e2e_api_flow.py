"""真实 HTTP 的端到端：走软件自己的 Api 调用，不直接碰内部函数。

覆盖：首次上传（含初始化 manifest）→ 第一次更新 → 分享页故障时仍能更新
→ 玩家绑定 → 检查 → 一键更新。使用本地蓝奏模拟服务（真 HTTP，不是 monkeypatch）。
"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mock_lanzou_account import MockLanzouAccount
from online.service import OnlineService
from pulses_web.api import Api
from pulses_web.controller import AppController
from pulses_web.events import EventBus, JobRunner


class ApiFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.server = MockLanzouAccount("123456", "secret")
        self.server.start()
        self.pack = self.base / "整合包"
        (self.pack / "tacz").mkdir(parents=True)

    def tearDown(self):
        self.server.stop()
        self.tmp.cleanup()

    def _api(self, db_name):
        ctrl = AppController(base_dir=self.base / db_name)
        bus = EventBus()
        jobs = JobRunner(bus, logger=ctrl.add_log)
        api = Api(ctrl, bus, jobs)
        return ctrl, api, jobs

    def _wait(self, jobs, job_id, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            job = jobs._jobs.get(job_id)
            if job and job.status in ("done", "error", "cancelled"):
                return job
            time.sleep(0.05)
        raise TimeoutError(job_id)

    def _job(self, api, jobs, method, params):
        out = api.invoke(method, params)
        self.assertTrue(out.get("ok"), out)
        return self._wait(jobs, out["data"]["jobId"])

    def _zip(self, path: Path, name: str, payload: bytes):
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr(name, payload)

    def test_first_upload_update_then_player_sync(self):
        ctrl, api, jobs = self._api("dev_db")
        self._job(api, jobs, "pack.open", {"path": str(self.pack)})
        ctrl.online = OnlineService(self.base / "dev_online",
                                    account_base=self.server.base)
        self.assertTrue(api.invoke("account.login",
                                   {"username": "123456", "password": "secret"})["ok"])
        api.invoke("app.role.switch", {"role": "developer"})
        name = ctrl.selected
        if ctrl.preset_manager.presets[name].get("applied"):
            api.invoke("preset.detach", {"name": name})
        self._zip(self.base / "alpha.zip", "a.json", b'{"a":1}')
        self._job(api, jobs, "preset.import",
                  {"name": name, "paths": [str(self.base / "alpha.zip")]})
        first = self._job(api, jobs, "online.publish.new",
                          {"name": name, "cloud_path": "/PulsesSwap/e2e",
                           "version": "v1.0.0", "notes": "首发"})
        self.assertEqual(first.status, "done", first.error)
        record = ctrl.online.source_of(name) or {}
        self.assertTrue((record.get("lanzou") or {}).get("url"))

        # 第一次更新
        self._zip(self.base / "beta.zip", "b.json", b'{"b":2}')
        self._job(api, jobs, "preset.import",
                  {"name": name, "paths": [str(self.base / "beta.zip")]})
        second = self._job(api, jobs, "online.publish.auto",
                           {"name": name, "notes": "新增 beta"})
        self.assertEqual(second.status, "done", second.error)

        # 分享页故障（账号接口仍然可用）：更新不能失败，也不能假装“云端不可用”
        folder_id = (ctrl.online.source_of(name) or {}).get("folder_id")
        share = self.server.share_server(folder_id)
        if share is not None:
            share.stop()
            self.server._shares.pop(folder_id, None)
        self._zip(self.base / "gamma.zip", "c.json", b'{"c":3}')
        self._job(api, jobs, "preset.import",
                  {"name": name, "paths": [str(self.base / "gamma.zip")]})
        third = self._job(api, jobs, "online.publish.auto",
                          {"name": name, "notes": "分享页故障时更新"})
        self.assertEqual(third.status, "done", third.error)

        diag = ctrl.net_diagnose(name)["steps"]
        self.assertTrue(diag and all(step["ok"] for step in diag), diag)

        # 玩家：用软件 API 绑定 → 检查 → 一键更新
        url, pwd = self.server.share_url(folder_id)
        player_pack = self.base / "玩家整合包"
        (player_pack / "tacz").mkdir(parents=True)
        pctrl, papi, pjobs = self._api("player_db")
        self._job(papi, pjobs, "pack.open", {"path": str(player_pack)})
        pctrl.online = OnlineService(self.base / "player_online",
                                     account_base=self.server.base)
        pname = pctrl.selected
        bind = papi.invoke("online.bind", {"name": pname, "url": url,
                                           "password": pwd})
        self.assertTrue(bind.get("ok"), bind)
        check = self._job(papi, pjobs, "online.check", {"name": pname})
        self.assertEqual(check.status, "done", check.error)
        summary = (check.result or {}).get("plan", {}).get("summary", "")
        self.assertIn("待下载", summary)
        sync = self._job(papi, pjobs, "online.sync.auto", {"name": pname})
        self.assertEqual(sync.status, "done", sync.error)
        tacz_files = [p for p in (player_pack / "tacz").rglob("*") if p.is_file()]
        self.assertTrue(tacz_files, "更新后 tacz 里没有枪包")


if __name__ == "__main__":
    unittest.main()
