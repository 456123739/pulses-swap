"""Task status snapshots survive a missing frontend event consumer."""
import json
import threading
import unittest
from pulses_web.events import EventBus, JobRunner


def terminal(bus, job_id):
    while True:
        event = bus.queue.get(timeout=2)
        if event.get("jobId") == job_id and event["type"] in (
                "job.done", "job.error", "job.cancelled"):
            return event


class JobStatusTests(unittest.TestCase):
    def test_unknown_job_status(self):
        runner = JobRunner(EventBus())
        out = runner.get_status("missing")
        self.assertEqual(out["status"], "unknown")
        self.assertFalse(out["cancelable"])
        json.dumps(out)

    def test_done_snapshot_and_result_are_isolated(self):
        bus = EventBus()
        runner = JobRunner(bus)
        job = runner.submit("fast", lambda ctx: {"items": [1]}, cancelable=False)
        terminal(bus, job)
        out = runner.get_status(job)
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["result"], {"items": [1]})
        self.assertFalse(out["cancelable"])
        out["result"]["items"].append(2)
        self.assertEqual(runner.get_status(job)["result"], {"items": [1]})
        json.dumps(out)

    def test_running_then_cancelled_snapshot(self):
        bus = EventBus()
        runner = JobRunner(bus)
        started, release = threading.Event(), threading.Event()
        def task(ctx):
            started.set()
            self.assertTrue(release.wait(2))
        job = runner.submit("cancel", task)
        self.assertTrue(started.wait(2))
        self.assertEqual(runner.get_status(job)["status"], "running")
        self.assertTrue(runner.cancel(job))
        release.set()
        terminal(bus, job)
        self.assertEqual(runner.get_status(job)["status"], "cancelled")

    def test_error_snapshot(self):
        bus = EventBus()
        runner = JobRunner(bus)
        def fail(ctx):
            raise ValueError("bad input")
        job = runner.submit("fail", fail)
        terminal(bus, job)
        self.assertEqual(runner.get_status(job)["status"], "error")
        self.assertEqual(runner.get_status(job)["error"], "bad input")
