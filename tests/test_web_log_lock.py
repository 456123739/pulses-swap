"""Network-reader logging must not wait on the task's controller lock."""
import tempfile
import threading
import unittest
from pathlib import Path
from pulses_web.controller import AppController


class LogLockTests(unittest.TestCase):
    def test_network_worker_can_log_while_task_holds_state_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctrl = AppController(base_dir=Path(tmp))
            completed = threading.Event()
            def reader():
                ctrl.add_log("清单读取成功")
                completed.set()
            with ctrl.lock:
                worker = threading.Thread(target=reader, daemon=True)
                worker.start()
                finished_without_unlock = completed.wait(1)
            worker.join(1)
            self.assertTrue(finished_without_unlock,
                            "网络线程日志等待业务锁会导致清单读取假超时")
            self.assertTrue(any(e['message'] == '清单读取成功'
                                for e in ctrl._log_snapshot()))
            ctrl._stop_watcher()
