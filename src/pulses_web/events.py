"""线程安全事件总线与 JobRunner。

pywebview 的 js_api 方法运行在独立线程，而且官方明确说这些函数不是线程
安全的。所有会改文件/网络的操作因此都通过 JobRunner 串行执行；UI 只收
事件，不直接碰核心对象。
"""
from __future__ import annotations

import json
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    title: str
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status: str = "queued"          # queued / running / done / error / cancelled
    created_at: float = field(default_factory=time.time)
    result: Any = None
    error: str = ""


class EventBus:
    """单调递增 seq 的事件出口；队列由 EventPump 在 WebView 就绪后消费。"""

    def __init__(self):
        self._seq = 0
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._sink: Callable[[dict], None] | None = None

    @property
    def queue(self):
        return self._queue

    def set_sink(self, sink: Callable[[dict], None] | None):
        self._sink = sink

    def emit(self, kind: str, data: Any = None, *, job_id: str | None = None,
             revision: int | None = None):
        with self._lock:
            self._seq += 1
            event = {"v": 1, "seq": self._seq, "type": kind}
            if job_id:
                event["jobId"] = job_id
            if revision is not None:
                event["revision"] = revision
            if data is not None:
                event["data"] = data
        sink = self._sink
        if sink is not None:
            try:
                sink(event)
                return event
            except Exception:
                pass
        self._queue.put(event)
        return event


class EventPump:
    """唯一调用 window.evaluate_js 的线程。"""

    def __init__(self, bus: EventBus, window, logger=None):
        self.bus = bus
        self.window = window
        self.logger = logger
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name="pulses-web-events", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        pending = []
        while not self._stop.is_set():
            try:
                event = self.bus.queue.get(timeout=0.15)
            except queue.Empty:
                event = None
            if event is not None:
                # 合并同一 Job 的连续进度，最多保留最新一条
                if event.get("type") == "job.progress":
                    pending = [e for e in pending
                               if not (e.get("type") == "job.progress"
                                       and e.get("jobId") == event.get("jobId"))]
                    pending.append(event)
                else:
                    pending.append(event)
            while pending:
                batch, pending = pending, []
                for item in batch:
                    self._send(item)
                if self._stop.is_set():
                    return
                try:
                    nxt = self.bus.queue.get_nowait()
                except queue.Empty:
                    break
                if nxt.get("type") == "job.progress":
                    pending = [e for e in pending
                               if not (e.get("type") == "job.progress"
                                       and e.get("jobId") == nxt.get("jobId"))]
                pending.append(nxt)
            time.sleep(0.035)

    def _send(self, event):
        try:
            payload = json.dumps(event, ensure_ascii=False)
            self.window.evaluate_js(
                f"window.PS && window.PS.push({payload});")
        except Exception as exc:
            # 窗口关闭/页面重载时不能把 EventPump 搞崩
            if self.logger:
                try:
                    self.logger(f"事件推送失败: {exc}", "WARNING")
                except Exception:
                    pass


class JobRunner:
    """单写者任务队列：所有修改文件/数据库/网络的操作按提交顺序执行。"""

    def __init__(self, bus: EventBus, logger=None):
        self.bus = bus
        self.logger = logger
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(
            target=self._run, name="pulses-web-jobs", daemon=True)
        self._worker.start()

    def submit(self, title: str, fn: Callable[["JobContext"], Any]) -> str:
        job = Job(id="j_" + uuid.uuid4().hex[:10], title=title)
        with self._lock:
            self._jobs[job.id] = job
        self.bus.emit("job.queued", {"title": title}, job_id=job.id)
        self._queue.put((job, fn))
        return job.id

    def cancel(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            job.cancel_event.set()
            self.bus.emit("job.cancelling", {}, job_id=job_id)
            return True
        return False

    def _run(self):
        while True:
            job, fn = self._queue.get()
            if job.cancel_event.is_set():
                job.status = "cancelled"
                self.bus.emit("job.cancelled", {}, job_id=job.id)
                continue
            job.status = "running"
            ctx = JobContext(self, job)
            self.bus.emit("job.started", {"title": job.title}, job_id=job.id)
            try:
                result = fn(ctx)
                if job.cancel_event.is_set():
                    job.status = "cancelled"
                    self.bus.emit("job.cancelled", {}, job_id=job.id)
                else:
                    job.status = "done"
                    job.result = result
                    self.bus.emit("job.done", {"result": result}, job_id=job.id)
            except Exception as exc:
                job.status = "error"
                job.error = str(exc)
                if self.logger:
                    try:
                        self.logger(f"任务失败: {exc}\n{traceback.format_exc()}",
                                    "ERROR")
                    except Exception:
                        pass
                self.bus.emit("job.error", {
                    "message": str(exc),
                    "code": getattr(exc, "code", "JOB_ERROR"),
                }, job_id=job.id)


class JobContext:
    def __init__(self, runner: JobRunner, job: Job):
        self.runner = runner
        self.job = job
        self._last = 0.0

    @property
    def cancelled(self):
        return self.job.cancel_event.is_set()

    def cancel_check(self):
        if self.cancelled:
            raise JobCancelled("任务已取消")

    def progress(self, percent=None, *, phase="", message="",
                 current=None, total=None, force=False):
        now = time.time()
        if not force and now - self._last < 0.04:
            return
        self._last = now
        self.runner.bus.emit("job.progress", {
            "phase": phase,
            "message": message,
            "percent": percent,
            "current": current,
            "total": total,
            "indeterminate": percent is None,
        }, job_id=self.job.id)

    def log(self, message, level="INFO"):
        self.runner.bus.emit("job.log", {"message": message, "level": level},
                             job_id=self.job.id)


class JobCancelled(Exception):
    code = "CANCELLED"
