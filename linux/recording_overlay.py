"""Recording overlay — Linux, modelled on the macOS notch pill.

A black pill hangs from the top edge of the screen, centred on whichever
monitor the pointer is on. It slides down on appear and shows three states:

- **dots** — three cycling dots while the mic warms up
- **wave** — nine capsule bars driven by the live microphone level, with a
  travelling-wave shimmer so it never looks frozen while you pause
- **processing** — the same bars driven purely by sine waves while the
  transcript is in flight

GTK3 + Cairo rather than Tk, for one reason: rounded corners. Tk on X11 has
no per-pixel alpha, and the X SHAPE extension does not help — XWayland keeps
the surface rectangular and paints the clipped-away region black instead of
transparent. A GTK window on an RGBA visual gets real alpha, which KWin
composites correctly, and Cairo anti-aliases the capsules for free.

The window runs on the X11 GDK backend (`linux/vocali` pins `GDK_BACKEND`):
Wayland forbids a client from positioning its own windows, and this one has
to sit at a specific spot on a specific monitor.

There is no main loop here. pystray's AppIndicator tray already runs
`Gtk.main()` on the main thread, and a second GTK loop in a second thread
would be a crash waiting to happen — so every state change hops onto that
existing loop with `GLib.idle_add`, and the animation is a `GLib.timeout_add`.

Self-check for the geometry maths (no display needed):

    PYTHONPATH=../windows .venv/bin/python recording_overlay.py
"""

from __future__ import annotations

import logging
import math
import time
from typing import Literal

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

import audio_recorder  # noqa: E402

log = logging.getLogger("vocali.overlay")

State = Literal["idle", "recording", "transcribing", "edit_recording"]

# macOS RecordingOverlay.swift geometry, in points; at 96 dpi these are pixels.
HEIGHT = 38
WIDTH = 92
WIDTH_EDIT = 180          # Mac widens the pill in command mode
CORNER_RADIUS = 12
SLIDE_MS = 180
FRAME_MS = 33             # ~30 fps, same cadence as the Mac TimelineView

# The Mac rounds only the bottom corners: the pill hangs off the top edge of
# the screen, so its top corners are never visible. Set this True for a
# free-floating pill rounded on all four sides.
ROUND_TOP_CORNERS = False

BAR_COUNT = 9
BAR_WIDTH = 3
BAR_GAP = 2.5
BAR_MIN_H = 2
BAR_MAX_H = 20
MULTIPLIERS = (0.35, 0.55, 0.75, 0.9, 1.0, 0.9, 0.75, 0.55, 0.35)
PROCESSING_MULTIPLIERS = (0.42, 0.58, 0.76, 0.9, 1.0, 0.9, 0.76, 0.58, 0.42)

DOT_RADIUS = 2.25
DOT_GAP = 4
DOT_PERIOD_S = 0.5

# How long the dots show before the waveform takes over, if the mic hasn't
# produced a level yet. The Mac has an explicit "initializing" phase; here
# the first non-zero sample ends it, and this is just the ceiling.
WARMUP_MAX_S = 0.6

# Per-bar smoothing. The Mac uses a SwiftUI spring (response 0.18, damping
# 0.88); a plain asymmetric lerp reads the same at this size and cadence.
ATTACK = 0.55
RELEASE = 0.22


def _ease_out_back(t: float) -> float:
    """cubic-bezier(0.34, 1.56, 0.64, 1) — the Mac's slide-down curve."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _monitor_geometry() -> tuple[int, int, int, int]:
    """(x, y, width, height) of the monitor holding the pointer.

    A multi-head desk has no single "screen": the union of a portrait panel
    and a landscape one has a centre that lands in dead space between them.
    """
    display = Gdk.Display.get_default()
    monitor = None
    try:
        pointer = display.get_default_seat().get_pointer()
        _screen, x, y = pointer.get_position()
        monitor = display.get_monitor_at_point(x, y)
    except Exception as e:
        log.info("Pointer lookup failed (%s); using the primary monitor.", e)
    if monitor is None:
        monitor = display.get_primary_monitor() or display.get_monitor(0)
    g = monitor.get_geometry()
    return g.x, g.y, g.width, g.height


class RecordingOverlay:
    def __init__(self) -> None:
        self._window: Gtk.Window | None = None
        self._state: State = "idle"
        self._phase = "dots"          # dots | wave | processing
        self._shown_at = 0.0
        self._slide_started = 0.0
        self._amplitudes = [0.0] * BAR_COUNT
        self._width = WIDTH
        self._origin = (0, 0)
        self._timer: int | None = None

    # ---- public API (same shape as the Windows overlay) ----

    def start(self) -> None:
        Gtk.init_check([])
        GLib.idle_add(self._build)

    def stop(self) -> None:
        GLib.idle_add(self._destroy)

    def set_state(self, state: State) -> None:
        # Called from the hotkey and pipeline threads; GLib.idle_add is the
        # thread-safe way into the GTK loop.
        GLib.idle_add(self._apply_state, state)

    # ---- everything below runs on the GTK main loop ----

    def _build(self) -> bool:
        if self._window is not None:
            return False
        window = Gtk.Window(type=Gtk.WindowType.POPUP)   # no focus, no decoration
        visual = window.get_screen().get_rgba_visual()
        if visual is not None:
            window.set_visual(visual)                    # per-pixel alpha
        else:
            log.info("No RGBA visual; the pill will have square opaque corners.")
        window.set_app_paintable(True)
        window.set_keep_above(True)
        window.set_default_size(self._width, HEIGHT)
        window.connect("draw", self._on_draw)
        window.realize()
        # Let clicks fall through to whatever is underneath.
        window.get_window().input_shape_combine_region(
            cairo.Region(cairo.RectangleInt(0, 0, 0, 0)), 0, 0)
        self._window = window
        return False

    def _destroy(self) -> bool:
        self._stop_timer()
        if self._window is not None:
            self._window.destroy()
            self._window = None
        return False

    def _stop_timer(self) -> None:
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _apply_state(self, state: State) -> bool:
        if self._window is None:
            self._build()
        if state == self._state:
            return False
        self._state = state

        if state == "idle":
            self._stop_timer()
            if self._window is not None:
                self._window.hide()
            return False

        was_hidden = not self._window.get_visible()
        if state == "transcribing":
            self._phase = "processing"
            width = self._width          # Mac locks the width while transcribing
        else:
            self._phase = "dots"
            self._amplitudes = [0.0] * BAR_COUNT
            width = WIDTH_EDIT if state == "edit_recording" else WIDTH

        self._place(width)
        self._shown_at = time.monotonic()
        self._slide_started = self._shown_at if was_hidden else 0.0
        self._window.show_all()

        if self._timer is None:
            self._timer = GLib.timeout_add(FRAME_MS, self._tick)
        return False

    # ---- geometry ----

    def _place(self, width: int) -> None:
        assert self._window is not None
        self._width = width
        mx, my, mw, _mh = _monitor_geometry()
        self._origin = (mx + (mw - width) // 2, my)
        self._window.resize(width, HEIGHT)
        self._window.move(*self._origin)

    def _slide_offset(self) -> int:
        """Vertical offset while the pill drops in, 0 once it has landed."""
        if not self._slide_started:
            return 0
        t = (time.monotonic() - self._slide_started) * 1000 / SLIDE_MS
        if t >= 1.0:
            self._slide_started = 0.0
            return 0
        return round(-HEIGHT * (1.0 - _ease_out_back(t)))

    # ---- animation ----

    def _tick(self) -> bool:
        if self._window is None or self._state == "idle":
            self._timer = None
            return False

        offset = self._slide_offset()
        if offset:
            self._window.move(self._origin[0], self._origin[1] + offset)
        elif self._slide_started == 0.0:
            self._window.move(*self._origin)

        if self._phase == "dots":
            level = audio_recorder.current_level()
            if level > 0 or time.monotonic() - self._shown_at > WARMUP_MAX_S:
                self._phase = "wave"
        if self._phase == "wave":
            self._advance_wave(time.monotonic())

        self._window.queue_draw()
        return True

    def _advance_wave(self, now: float) -> None:
        """Live level shaped per bar, plus the Mac's travelling-wave pulse so
        the pill keeps breathing while you pause mid-sentence."""
        level = max(audio_recorder.current_level(), 0.0)
        for i in range(BAR_COUNT):
            base = min(level * MULTIPLIERS[i], 1.0)
            travelling = 0.5 + 0.5 * math.sin(now * 6.2 - i * 0.78)
            shimmer = 0.5 + 0.5 * math.sin(now * 3.1 + i * 0.5)
            pulse = travelling * 0.22 + shimmer * 0.06
            target = min(base * (0.74 + pulse) + (1.0 - base) * (0.04 + pulse * 0.28),
                         1.0)
            blend = ATTACK if target > self._amplitudes[i] else RELEASE
            self._amplitudes[i] += (target - self._amplitudes[i]) * blend

    def _processing_amplitudes(self, now: float) -> list[float]:
        values = []
        for i in range(BAR_COUNT):
            wave = 0.5 + 0.5 * math.sin(now * 5.6 - i * 0.5)
            shimmer = 0.5 + 0.5 * math.sin(now * 2.8 + i * 0.75)
            values.append(min(0.16 + wave * PROCESSING_MULTIPLIERS[i] * 0.52
                              + shimmer * 0.08, 1.0))
        return values

    # ---- drawing ----

    def _bar_positions(self) -> list[float]:
        span = BAR_COUNT * BAR_WIDTH + (BAR_COUNT - 1) * BAR_GAP
        left = (self._width - span) / 2 + BAR_WIDTH / 2
        return [left + i * (BAR_WIDTH + BAR_GAP) for i in range(BAR_COUNT)]

    def _on_draw(self, _widget, cr: cairo.Context) -> bool:
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)          # clear to fully transparent
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        self._pill_path(cr)
        cr.set_source_rgba(0, 0, 0, 1)
        cr.fill()

        now = time.monotonic()
        if self._phase == "dots":
            self._draw_dots(cr, now)
        elif self._phase == "processing":
            self._draw_bars(cr, self._processing_amplitudes(now), processing=True)
        else:
            self._draw_bars(cr, self._amplitudes, processing=False)
        return False

    def _pill_path(self, cr: cairo.Context) -> None:
        w, h, r = self._width, HEIGHT, CORNER_RADIUS
        cr.new_sub_path()
        if ROUND_TOP_CORNERS:
            cr.arc(w - r, r, r, -math.pi / 2, 0)
        else:
            cr.move_to(w, 0)
        cr.arc(w - r, h - r, r, 0, math.pi / 2)
        cr.arc(r, h - r, r, math.pi / 2, math.pi)
        if ROUND_TOP_CORNERS:
            cr.arc(r, r, r, math.pi, 1.5 * math.pi)
        else:
            cr.line_to(0, 0)
        cr.close_path()

    def _draw_bars(self, cr: cairo.Context, amplitudes: list[float],
                   processing: bool) -> None:
        cr.set_line_width(BAR_WIDTH)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cy = HEIGHT / 2
        now = time.monotonic()
        for i, x in enumerate(self._bar_positions()):
            height = BAR_MIN_H + (BAR_MAX_H - BAR_MIN_H) * amplitudes[i]
            half = max((height - BAR_WIDTH) / 2, 0.01)   # round caps add the rest
            if processing:
                wave = 0.5 + 0.5 * math.sin(now * 5.6 - i * 0.5)
                cr.set_source_rgba(1, 1, 1, 0.45 + wave * 0.5)
            else:
                cr.set_source_rgba(1, 1, 1, 1)
            cr.move_to(x, cy - half)
            cr.line_to(x, cy + half)
            cr.stroke()

    def _draw_dots(self, cr: cairo.Context, now: float) -> None:
        active = int(now / DOT_PERIOD_S) % 3
        span = 3 * (2 * DOT_RADIUS) + 2 * DOT_GAP
        left = (self._width - span) / 2 + DOT_RADIUS
        cy = HEIGHT / 2
        for i in range(3):
            x = left + i * (2 * DOT_RADIUS + DOT_GAP)
            cr.set_source_rgba(1, 1, 1, 0.9 if i == active else 0.25)
            cr.arc(x, cy, DOT_RADIUS, 0, 2 * math.pi)
            cr.fill()


if __name__ == "__main__":
    # Self-check for the pure geometry/easing maths — no display needed.
    assert abs(_ease_out_back(0.0)) < 1e-9
    assert abs(_ease_out_back(1.0) - 1.0) < 1e-9
    assert max(_ease_out_back(t / 100) for t in range(101)) > 1.0, "should overshoot"

    overlay = RecordingOverlay()
    for width in (WIDTH, WIDTH_EDIT):
        overlay._width = width
        positions = overlay._bar_positions()
        assert len(positions) == BAR_COUNT
        span = positions[-1] - positions[0] + BAR_WIDTH
        assert abs((positions[0] - BAR_WIDTH / 2 + span / 2) - width / 2) < 0.01, \
            "bars off-centre"
        gaps = {round(b - a - BAR_WIDTH, 6) for a, b in zip(positions, positions[1:])}
        assert gaps == {BAR_GAP}, gaps

    # Silence must still leave a visible dot, never a zero-height bar.
    overlay._advance_wave(0.0)
    assert all(a > 0 for a in overlay._amplitudes)

    print("overlay geometry checks passed")
