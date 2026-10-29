"""PyWebView 迁移层的基础合同测试（无真实 WebView）。"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from pulses_web.api import Api
from pulses_web.controller import AppController
from pulses_web.events import EventBus, EventPump, JobRunner


class FakeWindow:
    def __init__(self):
        self.calls = []
        self.gate = None

    def evaluate_js(self, script):
        self.calls.append(script)
        if self.gate is not None:
            self.gate.wait(2)


class WebBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus = EventBus()
        self.ctrl = AppController(base_dir=Path(self.tmp.name) / "db",
                                  bus=self.bus)
        self.jobs = JobRunner(self.bus)
        self.api = Api(self.ctrl, self.bus, self.jobs)

    def tearDown(self):
        self.ctrl._stop_watcher()
        self.tmp.cleanup()

    def wait_event(self, kind, timeout=3):
        end = time.time() + timeout
        while time.time() < end:
            try:
                event = self.bus.queue.get(timeout=0.05)
            except Exception:
                continue
            if event.get("type") == kind:
                return event
        return None

    def test_unknown_method_and_validation(self):
        result = self.api.invoke("nope", {})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "UNKNOWN_METHOD")
        result = self.api.invoke("pack.open", {})
        self.assertFalse(result["ok"])

    def test_job_events_have_job_id_and_sequence(self):
        pack = Path(self.tmp.name) / "pack"
        (pack / "tacz").mkdir(parents=True)
        result = self.api.invoke("pack.open", {"path": str(pack)})
        self.assertTrue(result["ok"], result)
        job_id = result["data"]["jobId"]
        done = None
        end = time.time() + 3
        while time.time() < end and done is None:
            event = self.wait_event("job.done", timeout=0.5)
            if event is not None and event.get("jobId") == job_id:
                done = event
        self.assertIsNotNone(done)
        self.assertIn("seq", done)
        state = done["data"]["result"]["state"]
        self.assertTrue(state["pack"]["loaded"])
        self.assertEqual(len(state["presets"]), 1)

    def test_drop_folder_opens_pack(self):
        pack = Path(self.tmp.name) / "dropped"
        (pack / "tacz").mkdir(parents=True)
        result = self.api.handle_drop([str(pack)])
        self.assertTrue(result["ok"], result)
        job_id = result["data"]["jobId"]
        done = None
        end = time.time() + 3
        while time.time() < end and done is None:
            event = self.wait_event("job.done", timeout=0.5)
            if event is not None and event.get("jobId") == job_id:
                done = event
        self.assertIsNotNone(done)
        self.assertTrue(done["data"]["result"]["state"]["pack"]["loaded"])

    def test_drop_without_tacz_is_rejected(self):
        folder = Path(self.tmp.name) / "plain"
        folder.mkdir()
        result = self.api.handle_drop([str(folder)])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "NO_TACZ")

    def test_drop_without_paths_emits_error(self):
        result = self.api.handle_drop([])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "NO_PATH")
        event = self.wait_event("dnd.error")
        self.assertIsNotNone(event)

    def test_cancel_job(self):
        job_id = self.jobs.submit("slow", lambda ctx: time.sleep(0.2))
        self.assertTrue(self.jobs.cancel(job_id))

    def test_non_cancelable_job_rejects_cancel(self):
        job_id = self.jobs.submit("fixed", lambda ctx: None, cancelable=False)
        self.assertFalse(self.jobs.cancelable(job_id))
        self.assertFalse(self.jobs.cancel(job_id))

    def test_event_pump_serializes_events(self):
        win = FakeWindow()
        pump = EventPump(self.bus, win).start()
        try:
            self.bus.emit("state.changed", {"ok": True})
            time.sleep(0.2)
        finally:
            pump.stop()
        self.assertTrue(any("window.PS" in call for call in win.calls))
        self.assertTrue(any("\"type\": \"state.changed\"" in call
                            for call in win.calls))


if __name__ == "__main__":
    unittest.main()
