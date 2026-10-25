"""窗口出现/关闭动画的几何计算与补间首帧语义。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import importlib

tween_module = importlib.import_module("pulses.animation.tween")
from pulses.animation.tween import cancel_tween, tween
from pulses.ui.window_motion import WindowRect, lerp_rect, parse_geometry, pop_rect


class WindowMotionMathTest(unittest.TestCase):
    def test_parse_geometry(self):
        self.assertEqual(
            parse_geometry("1280x900+102+1130"),
            WindowRect(x=102, y=1130, width=1280, height=900),
        )
        self.assertEqual(
            parse_geometry("800x600-12+40"),
            WindowRect(x=-12, y=40, width=800, height=600),
        )

    def test_negative_position_round_trips(self):
        rect = WindowRect(x=-12, y=40, width=800, height=600)
        self.assertEqual(rect.geometry(), "800x600-12+40")
        self.assertEqual(parse_geometry(rect.geometry()), rect)

    def test_parse_geometry_rejects_invalid(self):
        for value in ("", None, "1280x900", "1280x900+1", "abc+1+2",
                      "1280x900+1+2+3"):
            self.assertIsNone(parse_geometry(value), value)

    def test_pop_rect_keeps_size_when_scale_is_one(self):
        final = WindowRect(102, 1130, 1280, 900)
        start = pop_rect(final, scale=1.0, offset_y=26)
        self.assertEqual(start.width, final.width)
        self.assertEqual(start.height, final.height)
        self.assertEqual(start.x, final.x)
        self.assertEqual(start.y, final.y + 26)

    def test_pop_rect_scales_around_center(self):
        final = WindowRect(100, 200, 1000, 800)
        start = pop_rect(final, scale=0.5, offset_y=0)
        self.assertEqual((start.width, start.height), (500, 400))
        self.assertEqual(start.x, 350)
        self.assertEqual(start.y, 400)

    def test_lerp_rect_endpoints_and_midpoint(self):
        start = WindowRect(0, 0, 100, 100)
        end = WindowRect(100, 50, 200, 300)
        self.assertEqual(lerp_rect(start, end, 0.0), start)
        self.assertEqual(lerp_rect(start, end, 1.0), end)
        self.assertEqual(
            lerp_rect(start, end, 0.5),
            WindowRect(50, 25, 150, 200),
        )


class FakeWidget:
    """只实现 tween 用到的 after / bind 接口。"""

    def __init__(self):
        self.jobs = {}
        self._seq = 0

    def after(self, _ms, callback):
        self._seq += 1
        self.jobs[self._seq] = callback
        return self._seq

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def bind(self, *_args, **_kwargs):
        return None

    def winfo_toplevel(self):
        return self

    def run_next(self):
        job = next(iter(self.jobs))
        callback = self.jobs.pop(job)
        callback()


class TweenFirstFrameTest(unittest.TestCase):
    def test_start_on_first_frame_ignores_initial_layout_stall(self):
        widget = FakeWidget()
        frames = []
        done = []
        # tween 内部不会提前取时间；第一次 step 在 100ms，第二次在 130ms。
        with mock.patch.object(
                tween_module.config, "ANIMATIONS_ENABLED", True), \
             mock.patch.object(
                tween_module.time, "perf_counter",
                side_effect=[100.0, 130.0]):
            tween(widget, "window_open", 30, lambda _e, raw: frames.append(raw),
                  on_done=lambda: done.append(True), fps=60,
                  start_on_first_frame=True)
            widget.run_next()
            self.assertEqual(frames, [0.0])
            widget.run_next()
        self.assertEqual(frames[-1], 1.0)
        self.assertEqual(done, [True])
        cancel_tween(widget, "window_open")

    def test_without_first_frame_semantics_starts_at_call_time(self):
        widget = FakeWidget()
        frames = []
        with mock.patch.object(
                tween_module.config, "ANIMATIONS_ENABLED", True), \
             mock.patch.object(
                tween_module.time, "perf_counter",
                side_effect=[100.0, 130.0]):
            tween(widget, "plain", 30, lambda _e, raw: frames.append(raw),
                  fps=60)
            widget.run_next()
        self.assertEqual(frames, [1.0])
        cancel_tween(widget, "plain")


if __name__ == "__main__":
    unittest.main()
