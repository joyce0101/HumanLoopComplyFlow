"""Opt-in *local Windows* mouse and screen-cursor comparison for LoopLedger.

OS cursor coordinates come from GetCursorPos. A separate pixel measurement
comes from the difference between an MSS cursor-free screenshot and a
Windows Graphics Capture (DXcam WinRT) screenshot with the cursor rendered. Never stores frames, full-screen captures, or a full pointer trace.

Not an anti-bot or identity guarantee: injected inputs, remote desktops,
animated content, pointer visibility or capture backend can defeat detection.
Non-Windows Streamlit servers intentionally cannot claim this check passed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import platform
import statistics
import threading
import time
from typing import Callable, Optional

# A user is prompted to move slowly and pause briefly at several locations.
MIN_PATH_PX = 180.0
MIN_MOVEMENTS = 10
MIN_VISIBLE_CHECKS = 4
MIN_ALIGNMENT_RATE = 0.75
MAX_MONITOR_SECONDS = 125.0
MATCH_TOLERANCE_PX = 30.0


@dataclass(frozen=True)
class MousePoint:
    timestamp: float
    x: int
    y: int


def evaluate_mouse_trace(points: list[MousePoint]) -> dict:
    """Describe a trace; heuristics are signals, *not* proof of humanity."""
    if not points:
        return {"path_px": 0.0, "movements": 0, "teleport_count": 0,
                "median_speed_px_s": None, "behavior": "insufficient_data"}
    path, moves, teleports, speeds = 0.0, 0, 0, []
    for prev, current in zip(points, points[1:]):
        dt = current.timestamp - prev.timestamp
        if dt <= 0:
            continue
        distance = math.hypot(current.x - prev.x, current.y - prev.y)
        if distance >= 2:
            path += distance
            moves += 1
            speed = distance / dt
            speeds.append(speed)
            # An anomaly *flag*, not conclusive evidence of automation.
            if distance >= 500 and dt <= 0.06:
                teleports += 1
    behavior = "insufficient_data"
    if path >= MIN_PATH_PX and moves >= MIN_MOVEMENTS:
        behavior = "unusual_motion" if teleports >= 2 else "observed_motion"
    return {"path_px": round(path, 1), "movements": moves,
            "teleport_count": teleports,
            "median_speed_px_s": round(statistics.median(speeds), 1) if speeds else None,
            "behavior": behavior}


def compare_cursor_locations(os_xy: tuple[int, int], pixel_xy: Optional[tuple[int, int]],
                             tolerance: float = MATCH_TOLERANCE_PX) -> Optional[dict]:
    """Compare two independently sampled cursor positions in screen pixels."""
    if pixel_xy is None:
        return None
    error = math.hypot(pixel_xy[0] - os_xy[0], pixel_xy[1] - os_xy[1])
    return {"distance_px": round(error, 2), "aligned": error <= tolerance}


def find_cursor_difference(without_cursor, with_cursor, *, left: int = 0,
                           top: int = 0) -> Optional[tuple[int, int]]:
    """Estimate visible pointer from two near-simultaneous screenshot crops.

    A small connected foreground component in a difference mask is a cursor
    *candidate*. Scene changes may look similar; counts alone do not validate
    screen-origin authenticity. Inputs are NumPy RGB/BGRA arrays.
    """
    import cv2
    import numpy as np

    a = np.asarray(without_cursor)
    b = np.asarray(with_cursor)
    if a.shape != b.shape or a.ndim != 3 or a.shape[2] < 3:
        return None
    delta = cv2.absdiff(a[:, :, :3], b[:, :, :3])
    mask = (np.max(delta, axis=2) >= 48).astype("uint8")
    pixel_count = int(mask.sum())
    # Reject updates affecting a large portion of the screen (animation etc.).
    if pixel_count < 7 or pixel_count > 1700:
        return None
    count, labels, stats, centres = cv2.connectedComponentsWithStats(mask, 8)
    candidates = []
    for i in range(1, count):
        x, y, w, h, area = [int(z) for z in stats[i]]
        if 6 <= area <= 1100 and 2 <= w <= 70 and 2 <= h <= 70:
            # Ignore isolated tiny noise; favour a compact cursor-shaped region.
            candidates.append((area, x, y, w, h))
    if not candidates:
        return None
    area, x, y, w, h = max(candidates)
    # Mouse hotspots are often near the upper-left of the icon. The centroid
    # can be ~15-25px away, so alignment tolerance accounts for icon geometry.
    return (left + x + w // 2, top + y + h // 2)


def _win_cursor_xy() -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes
    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
    point = POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("GetCursorPos failed")
    return int(point.x), int(point.y)


@dataclass
class MouseScreenMonitor:
    """Per-session opt-in worker. Monitors OS pointer and small screenshot crops.

    Screen capture does not begin until the explicit consent/start action.
    On finish, only aggregate counters are retained. Frames never leave RAM.
    """
    case_id: str
    reviewer: str
    challenge_id: str
    time_limit: float = MAX_MONITOR_SECONDS
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False)
    _points: list[MousePoint] = field(default_factory=list, init=False)
    _screen_checks: int = field(default=0, init=False)
    _screen_matches: int = field(default=0, init=False)
    _screen_missing: int = field(default=0, init=False)
    _visible_trace: list[tuple[int, int, int, int]] = field(default_factory=list, init=False)
    _error: str = field(default="", init=False)
    _enabled_at: float = field(default=0, init=False)
    _finished: bool = field(default=False, init=False)

    def start(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("Screen-cursor comparison requires local Windows desktop mode.")
        if self._thread is not None:
            raise RuntimeError("Mouse monitor already started")
        try:
            import mss  # noqa: F401
            import dxcam  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("Missing mss/dxcam; install requirements-verification.txt") from exc
        self._enabled_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True, name="LoopLedgerMouseCheck")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        with self._lock:
            self._finished = True

    def _run(self) -> None:
        try:
            import mss
            import dxcam
            # Windows MSS has NO documented cursor overlay. WinRT does.
            # Capture only the primary monitor; do not fake a match if a
            # desktop/browser environment cannot expose the actual pointer.
            with mss.mss() as plain, dxcam.create(backend="winrt", output_color="BGRA") as overlay:
                next_screenshot = time.monotonic() + 0.25
                while (not self._stop.is_set() and
                       time.monotonic() - self._enabled_at < self.time_limit):
                    when = time.monotonic()
                    position = _win_cursor_xy()
                    with self._lock:
                        self._points.append(MousePoint(when, *position))
                        if len(self._points) > 4700:
                            self._points = self._points[-4700:]
                    if when >= next_screenshot:
                        next_screenshot = when + 0.35
                        try:
                            self._capture_pair(plain, overlay, position)
                        except Exception:
                            with self._lock:
                                self._screen_missing += 1
                    time.sleep(0.035)
        except Exception as exc:
            with self._lock:
                self._error = f"Screen monitoring unavailable: {type(exc).__name__}: {str(exc)[:130]}"
        finally:
            with self._lock:
                self._finished = True

    def _capture_pair(self, plain, overlay, approx_xy: tuple[int, int]) -> None:
        import numpy as np
        bounds = plain.monitors[1]  # Primary capture output (display 1 only).
        x, y = approx_xy
        left = max(int(bounds["left"]), x - 80)
        top = max(int(bounds["top"]), y - 80)
        right = min(int(bounds["left"] + bounds["width"]), x + 80)
        bottom = min(int(bounds["top"] + bounds["height"]), y + 80)
        if right - left < 70 or bottom - top < 70:
            return
        region = {"left": left, "top": top,
                  "width": right - left, "height": bottom - top}
        before = _win_cursor_xy()
        a = np.asarray(plain.grab(region))
        # DXcam uses coordinates local to its selected (primary) output.
        winrt_region = (left - int(bounds["left"]), top - int(bounds["top"]),
                        right - int(bounds["left"]), bottom - int(bounds["top"]))
        visible = overlay.grab(region=winrt_region, new_frame_only=False)
        after = _win_cursor_xy()
        if visible is None:
            return
        b = np.asarray(visible)
        # Pointer motion while capturing invalidates timestamp alignment.
        if math.hypot(before[0] - after[0], before[1] - after[1]) > 6:
            return
        seen_xy = find_cursor_difference(a, b, left=left, top=top)
        result = compare_cursor_locations(after, seen_xy)
        with self._lock:
            if result is None:
                self._screen_missing += 1
            else:
                self._screen_checks += 1
                self._screen_matches += int(result["aligned"])
                self._visible_trace.append((after[0], after[1], seen_xy[0], seen_xy[1]))
                if len(self._visible_trace) > 250:
                    self._visible_trace = self._visible_trace[-250:]

    def status(self) -> dict:
        with self._lock:
            behavior = evaluate_mouse_trace(self._points)
            n = self._screen_checks
            ratio = (self._screen_matches / n) if n else None
            passed = bool(
                behavior["behavior"] == "observed_motion"
                and n >= MIN_VISIBLE_CHECKS
                and ratio is not None and ratio >= MIN_ALIGNMENT_RATE
            )
            return {"case_id": self.case_id, "reviewer": self.reviewer,
                    "challenge_id": self.challenge_id, "running": bool(self._thread and self._thread.is_alive()),
                    "finished": self._finished, "status": "passed" if passed else
                    ("error" if self._error else "collecting" if not self._finished else "inconclusive"),
                    **behavior, "visible_cursor_checks": n,
                    "aligned_cursor_checks": self._screen_matches,
                    "inconclusive_frames": self._screen_missing,
                    "cursor_alignment_rate": round(ratio, 4) if ratio is not None else None,
                    "error": self._error}

    def trace_preview(self) -> dict:
        """In-memory preview for the logged-in reviewer; never saved to SQLite."""
        with self._lock:
            return {
                "os_trace": [(p.x, p.y) for p in self._points[-1000::10]],
                "screen_pairs": list(self._visible_trace),
            }

    def evidence(self) -> Optional[dict]:
        """Returns aggregate-only evidence after sufficient observations."""
        summary = self.status()
        if summary["status"] != "passed":
            return None
        return {k: summary[k] for k in (
            "status", "path_px", "movements", "teleport_count", "median_speed_px_s",
            "behavior", "visible_cursor_checks", "aligned_cursor_checks",
            "cursor_alignment_rate", "inconclusive_frames")}
