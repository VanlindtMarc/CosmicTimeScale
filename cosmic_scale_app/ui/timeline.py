import datetime
import tkinter as tk
from typing import Optional
import math

from ..core.shared import (
    ASTRO_YEAR_SECONDS,
    PALETTE,
    CosmicEvent,
    CosmicPeriod,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
    SECONDS_PER_YEAR,
    format_axis_label,
    format_calendar_year,
    format_real_date_label,
    now_year_decimal,
    pick_tick_step,
    session_now,
)
class ZoomableTimeline(tk.Canvas):
    # 1e12 lets us drill down to ~30 microseconds on a 1-year target — far below
    # second resolution, with float64 precision still safe.
    MAX_ZOOM = 1e12

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=PALETTE["panel"], highlightthickness=0, **kwargs)
        self.events:  list[CosmicEvent]  = []
        self.periods: list[CosmicPeriod] = []
        self.target_seconds = SECONDS_PER_YEAR
        self.realtime_ref_years: Optional[float] = None
        self._view_start = 0.0
        self._view_end   = 1.0
        self._drag_x     = None
        self._drag_vs    = None
        self._period_scroll_y = 0.0
        self._period_scroll_drag = None
        self._bar_drag = None
        self._bar_y_ratio = 0.52
        self._tooltip_win = None

        self.bind("<Configure>",       lambda _: self._redraw())
        self.bind("<MouseWheel>",      self._on_wheel)
        self.bind("<ButtonPress-1>",   self._on_drag_start)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_drag_release)
        self.bind("<Motion>",          self._on_motion)
        self.bind("<Leave>",           self._hide_tooltip)
        self.bind("<Double-Button-1>", lambda _: self.reset_zoom())

    def set_events(self, events):
        self.events = events
        self._redraw()

    def set_periods(self, periods):
        self.periods = periods
        self._period_scroll_y = 0.0
        self._redraw()

    def set_target(self, target_seconds, realtime_ref_years: Optional[float] = None):
        self.target_seconds = target_seconds
        self.realtime_ref_years = realtime_ref_years
        self._redraw()

    def reset_zoom(self):
        self._view_start, self._view_end = 0.0, 1.0
        self._redraw()

    def focus_on_event(self, fraction: float):
        """Pan / zoom so the event sits in the centre of the view."""
        span = self._view_end - self._view_start
        # Zoom in if currently fully zoomed-out (or close to it).
        if span > 0.5:
            span = 0.05
        s = fraction - span / 2
        e = s + span
        if s < 0: s, e = 0.0, span
        if e > 1: s, e = 1.0 - span, 1.0
        self._view_start, self._view_end = s, e
        self._redraw()

    def focus_on_period(self, frac_start: float, frac_end: float):
        """Set the view to encompass [frac_start, frac_end] with margin."""
        inner  = max(1e-12, frac_end - frac_start)
        margin = max(inner * 0.15, 1e-9)
        s = max(0.0, frac_start - margin)
        e = min(1.0, frac_end   + margin)
        if e - s < 1e-12:
            e = s + 1e-12
        self._view_start, self._view_end = s, e
        self._redraw()

    def _frac_to_x(self, frac):
        w = self.winfo_width()
        return (frac - self._view_start) / (self._view_end - self._view_start) * w

    def _x_to_frac(self, x):
        w = self.winfo_width()
        return self._view_start + x / w * (self._view_end - self._view_start)

    def _clamp_view(self, s: float, e: float) -> tuple[float, float]:
        # Guard against degenerate spans coming out of float math.
        span = e - s
        if not (span > 0):
            span = 1.0
            e = s + span
        # Allow up to a full span of overscroll past either edge so the user
        # can drag the period boundary all the way to the centre of the canvas
        # before zooming in.
        margin = span
        if s < -margin: s, e = -margin, -margin + span
        if e > 1 + margin: e, s = 1 + margin, 1 + margin - span
        # Always keep a meaningful slice of [0, 1] in view so items don't
        # vanish at the edges.  We require ≥10% of the visible span to
        # actually be inside the period.
        overlap = max(0.0, min(e, 1.0) - max(s, 0.0))
        if overlap < span * 0.10:
            center = (s + e) * 0.5
            if center < 0.5:
                # Snap so 90% of the view is overscroll on the left,
                # 10% inside the period from frac=0.
                s = -span * 0.9
                e = s + span
            else:
                e = 1.0 + span * 0.9
                s = e - span
        return s, e

    def _on_wheel(self, event):
        factor   = 0.75 if event.delta > 0 else 1.0 / 0.75
        frac_at  = self._x_to_frac(event.x)
        # Snap a cursor sitting in the overscroll void back onto [0, 1]
        # so zooming there doesn't push the whole view out of the period.
        if   frac_at < 0.0: frac_at = 0.0
        elif frac_at > 1.0: frac_at = 1.0
        span     = self._view_end - self._view_start
        if not (span > 0):
            span = 1.0
        new_span = max(1.0 / self.MAX_ZOOM, min(3.0, span * factor))
        ratio    = (frac_at - self._view_start) / span
        ns = frac_at - ratio * new_span
        ne = ns + new_span
        ns, ne = self._clamp_view(ns, ne)
        self._view_start, self._view_end = ns, ne
        self._redraw()

    def _on_drag_start(self, event):
        if self._start_period_scroll_drag(event):
            return
        if self._start_bar_drag(event):
            return
        self._drag_x  = event.x
        self._drag_vs = (self._view_start, self._view_end)

    def _on_drag(self, event):
        if self._period_scroll_drag is not None:
            self._drag_period_scroll(event)
            return
        if self._bar_drag is not None:
            self._drag_timeline_bar(event)
            return
        if self._drag_x is None: return
        w    = self.winfo_width()
        span = self._view_end - self._view_start
        dx   = (event.x - self._drag_x) / w * span
        s, e = self._drag_vs[0] - dx, self._drag_vs[1] - dx
        s, e = self._clamp_view(s, e)
        self._view_start, self._view_end = s, e
        self._redraw()

    def _on_drag_release(self, _):
        self._drag_x = None
        self._period_scroll_drag = None
        self._bar_drag = None

    def _period_scroll_metrics(self):
        return getattr(self, "_period_scroll_metrics_cache", None)

    def _clamp_period_scroll(self):
        metrics = self._period_scroll_metrics()
        max_scroll = metrics["max_scroll"] if metrics else 0.0
        self._period_scroll_y = max(0.0, min(max_scroll, self._period_scroll_y))

    def _point_in_rect(self, x, y, rect):
        if rect is None:
            return False
        x0, y0, x1, y1 = rect
        return x0 <= x <= x1 and y0 <= y <= y1

    def _bar_y_bounds(self, h: Optional[int] = None) -> tuple[int, int]:
        h = h if h is not None else self.winfo_height()
        return (max(70, h // 5), max(90, h - 110))

    def _current_bar_y(self, h: Optional[int] = None) -> int:
        h = h if h is not None else self.winfo_height()
        y_min, y_max = self._bar_y_bounds(h)
        if y_max <= y_min:
            return h // 2
        self._bar_y_ratio = max(0.0, min(1.0, self._bar_y_ratio))
        return round(y_min + self._bar_y_ratio * (y_max - y_min))

    def _timeline_bar_hit_rect(self):
        return getattr(self, "_timeline_bar_hit_rect_cache", None)

    def _start_bar_drag(self, event) -> bool:
        hit_rect = self._timeline_bar_hit_rect()
        if not self._point_in_rect(event.x, event.y, hit_rect):
            return False
        self._bar_drag = {
            "start_y": event.y,
            "start_ratio": self._bar_y_ratio,
        }
        self._drag_x = None
        return True

    def _drag_timeline_bar(self, event):
        h = self.winfo_height()
        y_min, y_max = self._bar_y_bounds(h)
        span = max(1, y_max - y_min)
        dy = event.y - self._bar_drag["start_y"]
        self._bar_y_ratio = self._bar_drag["start_ratio"] + dy / span
        self._bar_y_ratio = max(0.0, min(1.0, self._bar_y_ratio))
        self._clamp_period_scroll()
        self._redraw()

    def _scroll_periods_by(self, delta_y: float):
        self._period_scroll_y += delta_y
        self._clamp_period_scroll()
        self._redraw()

    def _scroll_periods_with_wheel(self, event) -> bool:
        metrics = self._period_scroll_metrics()
        if not metrics or metrics["max_scroll"] <= 0:
            return False
        if not self._point_in_rect(event.x, event.y, metrics["area_rect"]):
            return False
        direction = -1 if event.delta > 0 else 1
        self._scroll_periods_by(direction * metrics["row_h"] * 2)
        return True

    def _start_period_scroll_drag(self, event) -> bool:
        metrics = self._period_scroll_metrics()
        if not metrics or metrics["max_scroll"] <= 0:
            return False
        if self._point_in_rect(event.x, event.y, metrics["thumb_rect"]):
            self._period_scroll_drag = {
                "start_y": event.y,
                "start_scroll": self._period_scroll_y,
            }
            self._drag_x = None
            return True
        if self._point_in_rect(event.x, event.y, metrics["track_rect"]):
            _, thumb_y0, _, thumb_y1 = metrics["thumb_rect"]
            page = metrics["viewport_h"] * (1 if event.y > thumb_y1 else -1)
            self._scroll_periods_by(page)
            self._period_scroll_drag = {
                "start_y": event.y,
                "start_scroll": self._period_scroll_y,
            }
            self._drag_x = None
            return True
        return False

    def _drag_period_scroll(self, event):
        metrics = self._period_scroll_metrics()
        if not metrics or metrics["max_scroll"] <= 0:
            return
        track_h = metrics["track_h"]
        thumb_h = metrics["thumb_h"]
        travel = max(1.0, track_h - thumb_h)
        dy = event.y - self._period_scroll_drag["start_y"]
        ratio = metrics["max_scroll"] / travel
        self._period_scroll_y = self._period_scroll_drag["start_scroll"] + dy * ratio
        self._clamp_period_scroll()
        self._redraw()

    def _on_motion(self, event):
        # Period hits take priority over events when the cursor is below the
        # bar (in the period-block zone) so the event proximity fallback can
        # never steal a hover targeted at a period block.
        hit_p = self._find_period_at(event.x, event.y)
        if hit_p:
            self._show_period_tooltip(event.x_root, event.y_root, hit_p)
            return
        # Cached pill/diamond rectangles for events.
        hit_ev = self._find_event_at(event.x, event.y)
        if hit_ev is None:
            # Horizontal-proximity fallback — restricted to the strip just
            # around the bar (where events live) so it doesn't trigger when
            # the cursor is on a period block far below.
            ev_strip = self._event_y_strip()
            if ev_strip is not None and ev_strip[0] <= event.y <= ev_strip[1]:
                hit_ev = next(
                    (ev for ev in self.events
                     if abs(self._frac_to_x(ev.fraction) - event.x) <= 7),
                    None)
        if hit_ev:
            self._show_event_tooltip(event.x_root, event.y_root, hit_ev)
            return
        self._hide_tooltip()

    def _event_y_strip(self):
        """Return (y_min, y_max) covering all visible event hit zones, or None."""
        hits = getattr(self, "_event_hits", None)
        if not hits:
            return None
        y_min = min(h[2] for h in hits)
        y_max = max(h[4] for h in hits)
        return (y_min - 4, y_max + 4)

    def _find_event_at(self, x: float, y: float):
        for ev, x0, y0, x1, y1 in getattr(self, "_event_hits", ()):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return ev
        return None

    def _find_period_at(self, x: float, y: float) -> Optional["CosmicPeriod"]:
        for p, x0, y0, x1, y1 in getattr(self, "_period_hits", ()):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return p
        return None

    def _build_tooltip(self, rx: int, ry: int, key) -> tk.Frame:
        """Open a fresh tooltip window and return its inner frame for content."""
        if self._tooltip_win and getattr(self._tooltip_win, "_key", None) is key:
            return None  # already showing this exact item
        self._hide_tooltip()
        win = tk.Toplevel(self)
        win._key = key
        win.wm_overrideredirect(True)
        win.wm_geometry(f"+{rx + 12}+{ry - 10}")
        win.configure(bg=PALETTE["border"])
        inner = tk.Frame(win, bg=PALETTE["panel2"], padx=10, pady=8)
        inner.pack(padx=1, pady=1)
        self._tooltip_win = win
        return inner

    def _show_event_tooltip(self, rx, ry, ev: CosmicEvent):
        inner = self._build_tooltip(rx, ry, ev)
        if inner is None: return
        tk.Label(inner, text=ev.name, bg=PALETTE["panel2"],
                 fg=ev.color, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(inner, text=f"Il y a {ev.years_ago:,.0f} ans",
                 bg=PALETTE["panel2"], fg=PALETTE["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w")
        for line in ev.result_str.split("\n"):
            tk.Label(inner, text=line, bg=PALETTE["panel2"],
                     fg=PALETTE["text"], font=("Segoe UI", 9)).pack(anchor="w")
        if ev.description:
            tk.Frame(inner, bg=PALETTE["border"], height=1).pack(
                fill="x", pady=(6, 4))
            tk.Label(inner, text=ev.description, bg=PALETTE["panel2"],
                     fg=PALETTE["text"], font=("Segoe UI", 9),
                     wraplength=320, justify="left").pack(anchor="w")

    def _show_period_tooltip(self, rx, ry, p: "CosmicPeriod"):
        inner = self._build_tooltip(rx, ry, p)
        if inner is None: return
        title = p.name + ("  (en cours)" if getattr(p, "is_ongoing", False) else "")
        tk.Label(inner, text=title, bg=PALETTE["panel2"],
                 fg=p.color, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        if getattr(p, "is_ongoing", False):
            range_text = f"Il y a {p.years_ago_start:,.0f} ans → en cours"
        else:
            range_text = (f"Il y a {p.years_ago_start:,.0f} → "
                           f"{p.years_ago_end:,.0f} ans")
        tk.Label(inner, text=range_text,
                 bg=PALETTE["panel2"], fg=PALETTE["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(inner, text=f"Durée affichée : {p.duration_str}",
                 bg=PALETTE["panel2"], fg=PALETTE["text"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(2, 0))
        # Dates on the target scale
        if p.start_str:
            tk.Label(inner,
                     text="Début : " + p.start_str.split("\n")[0]
                          + ("  ·  " + p.start_str.split("\n")[1]
                             if "\n" in p.start_str else ""),
                     bg=PALETTE["panel2"], fg=PALETTE["text"],
                     font=("Segoe UI", 9)).pack(anchor="w")
        if getattr(p, "is_ongoing", False):
            tk.Label(inner, text="Fin :    en cours",
                     bg=PALETTE["panel2"], fg=PALETTE["accent"],
                     font=("Segoe UI", 9, "bold")).pack(anchor="w")
        elif p.end_str:
            tk.Label(inner,
                     text="Fin :    " + p.end_str.split("\n")[0]
                          + ("  ·  " + p.end_str.split("\n")[1]
                             if "\n" in p.end_str else ""),
                     bg=PALETTE["panel2"], fg=PALETTE["text"],
                     font=("Segoe UI", 9)).pack(anchor="w")
        if p.description:
            tk.Frame(inner, bg=PALETTE["border"], height=1).pack(
                fill="x", pady=(6, 4))
            tk.Label(inner, text=p.description, bg=PALETTE["panel2"],
                     fg=PALETTE["text"], font=("Segoe UI", 9),
                     wraplength=320, justify="left").pack(anchor="w")

    def _hide_tooltip(self, _=None):
        if self._tooltip_win:
            self._tooltip_win.destroy()
            self._tooltip_win = None

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2: return

        self._timeline_bar_hit_rect_cache = None
        BAR_Y = self._current_bar_y(h)
        BAR_H = 8

        self.create_rectangle(0, 0, w, h, fill=PALETTE["panel"], outline="")

        # Shade the regions outside [0, 1] so overscrolled "void" is visually distinct.
        x0 = self._frac_to_x(0.0)
        x1 = self._frac_to_x(1.0)
        if x0 > 0:
            self.create_rectangle(0, 0, x0, h,
                                   fill=PALETTE["bg"], outline="")
        if x1 < w:
            self.create_rectangle(x1, 0, w, h,
                                   fill=PALETTE["bg"], outline="")

        # Active bar only spans the period [0, 1].
        bar_x0 = max(0, x0)
        bar_x1 = min(w, x1)
        if bar_x1 > bar_x0:
            self.create_rectangle(bar_x0, BAR_Y - BAR_H // 2,
                                   bar_x1, BAR_Y + BAR_H // 2,
                                   fill=PALETTE["border"], outline="")
            self._timeline_bar_hit_rect_cache = (
                bar_x0, BAR_Y - BAR_H - 4,
                bar_x1, BAR_Y + BAR_H + 4,
            )

        # Edge markers (start / end of period) when visible.
        for frac, label, color in ((0.0, "Début", PALETTE["accent"]),
                                    (1.0, "Aujourd'hui", PALETTE["accent2"])):
            x = self._frac_to_x(frac)
            if -2 <= x <= w + 2:
                self.create_line(x, 0, x, h - 8,
                                  fill=color, width=1, dash=(2, 3))
                self.create_text(x + 3 if frac == 0 else x - 3, 4,
                                  text=label, anchor="nw" if frac == 0 else "ne",
                                  fill=color, font=("Segoe UI", 8, "bold"))

        self._draw_axis(w, BAR_Y, BAR_H)
        self._draw_events(w, h, BAR_Y, BAR_H)
        self._draw_periods(w, h, BAR_Y, BAR_H)
        self._draw_minimap(w, h)

        zoom = 1.0 / (self._view_end - self._view_start)
        self.create_text(w - 6, 4,
                         text=f"×{zoom:.1f}" if zoom >= 10 else f"×{zoom:.2f}",
                         anchor="ne", fill=PALETTE["muted"], font=("Segoe UI", 8))

    def _draw_axis(self, w, bar_y, bar_h):
        # Real-time mode uses a dedicated path that walks calendar dates
        # directly: when the period spans Ga and the user zooms to a few days,
        # `target_seconds ~ 4e17` makes float64 ULP ≈ 96 s at that magnitude,
        # which mis-aligns ticks against event markers (the marker is computed
        # from years_ago, the tick from t/target — the rounding errors differ).
        if self.realtime_ref_years is not None:
            self._draw_axis_realtime(w, bar_y, bar_h)
            return

        # ── Standard target-seconds path (1 day / 1 an / siècle / etc.) ──
        view_sec_start = self._view_start * self.target_seconds
        view_sec_end   = self._view_end   * self.target_seconds
        span_sec       = view_sec_end - view_sec_start
        target_ticks   = max(4, min(10, w // 110))
        step_sec       = pick_tick_step(span_sec, target_ticks)

        first_tick = math.floor(view_sec_start / step_sec) * step_sec
        eps        = step_sec * 1e-6
        t          = first_tick
        safety     = 0
        while t <= view_sec_end + eps and safety < 500:
            safety += 1
            if t >= view_sec_start - eps:
                frac = t / self.target_seconds
                x    = self._frac_to_x(frac)
                self.create_line(x, bar_y + bar_h // 2,
                                 x, bar_y + bar_h // 2 + 5,
                                 fill=PALETTE["muted"], width=1)
                label = format_axis_label(t, self.target_seconds, step_sec)
                for j, line in enumerate(label.split("\n")):
                    self.create_text(x, bar_y + bar_h // 2 + 7 + j * 10,
                                     text=line, anchor="n",
                                     fill=PALETTE["muted"], font=("Segoe UI", 7))
            t += step_sec

    def _draw_axis_realtime(self, w, bar_y, bar_h):
        """Draw axis ticks aligned to real calendar boundaries.

        We walk datetimes directly (microsecond precision) and convert each
        tick back to a `fraction` via the same formula used for events :
        `fraction = (ref - years_ago) / ref`.  Both pipelines are then
        consistent, eliminating the 12 h drift visible at deep zoom.

        The whole body is wrapped in a guard: any OverflowError (which can
        happen when overscroll pushes the visible date below year 1) is
        swallowed — without it the rest of `_redraw` (events, periods,
        minimap, zoom indicator) would also stop being drawn.
        """
        ref = self.realtime_ref_years
        if not ref:
            return
        try:
            self._draw_axis_realtime_inner(w, bar_y, bar_h, ref)
        except (OverflowError, OSError, ValueError):
            # Out-of-range datetime — skip the axis but let the rest render.
            return

    def _draw_axis_realtime_inner(self, w, bar_y, bar_h, ref):
        ya_start = ref * (1.0 - self._view_start)   # older bound
        ya_end   = ref * (1.0 - self._view_end)     # more recent
        if ya_start < ya_end:
            ya_start, ya_end = ya_end, ya_start

        # Cap the date range to what `datetime` can represent (years 1..9999).
        # Without this the timedelta arithmetic raises and the whole redraw
        # collapses, leaving the canvas visually empty. Negative years_ago
        # are future dates, so clamp them against MAX_DT instead of snapping
        # them back to "now".
        now_dt   = session_now()
        MIN_DT   = datetime.datetime(1, 1, 2)
        MAX_DT   = datetime.datetime(9999, 12, 30)
        max_back = max(0.0, (now_dt - MIN_DT).total_seconds())
        max_fwd  = max(0.0, (MAX_DT - now_dt).total_seconds())
        raw_start_sec = ya_start * ASTRO_YEAR_SECONDS
        raw_end_sec   = ya_end   * ASTRO_YEAR_SECONDS
        if raw_start_sec > max_back or raw_end_sec > max_back:
            self._draw_axis_realtime_approx(w, bar_y, bar_h,
                                            ya_start, ya_end, ref)
            return

        def clamp_years_ago_seconds(years_ago: float) -> float:
            seconds = years_ago * ASTRO_YEAR_SECONDS
            return max(-max_fwd, min(max_back, seconds))

        ya_start_sec = clamp_years_ago_seconds(ya_start)
        ya_end_sec   = clamp_years_ago_seconds(ya_end)
        start_dt = now_dt - datetime.timedelta(seconds=ya_start_sec)
        end_dt   = now_dt - datetime.timedelta(seconds=ya_end_sec)
        if end_dt < start_dt:
            start_dt, end_dt = end_dt, start_dt

        span_seconds = max(1e-6, (end_dt - start_dt).total_seconds())
        target_ticks = max(4, min(10, w // 110))
        step_sec     = pick_tick_step(span_seconds, target_ticks)

        # Align the first tick to a multiple of step_sec from the Unix epoch
        # so days, hours, minutes fall on exact calendar boundaries.
        epoch        = datetime.datetime(1970, 1, 1)
        start_offset = (start_dt - epoch).total_seconds()
        first_offset = math.floor(start_offset / step_sec) * step_sec
        # Clamp the first tick to the representable range so the timedelta
        # below never overflows.
        epoch_min = (MIN_DT - epoch).total_seconds()
        epoch_max = (MAX_DT - epoch).total_seconds()
        first_offset = max(epoch_min, min(epoch_max, first_offset))
        cur_dt = epoch + datetime.timedelta(seconds=first_offset)

        half_step = datetime.timedelta(seconds=step_sec * 0.5)
        full_step = datetime.timedelta(seconds=step_sec)

        safety = 0
        while cur_dt <= end_dt + half_step and safety < 500:
            safety += 1
            if cur_dt >= start_dt - half_step:
                ya = (now_dt - cur_dt).total_seconds() / ASTRO_YEAR_SECONDS
                frac = (ref - ya) / ref
                x    = self._frac_to_x(frac)
                self.create_line(x, bar_y + bar_h // 2,
                                 x, bar_y + bar_h // 2 + 5,
                                 fill=PALETTE["muted"], width=1)
                label = format_real_date_label(ya, step_sec)
                for j, line in enumerate(label.split("\n")):
                    self.create_text(x, bar_y + bar_h // 2 + 7 + j * 10,
                                     text=line, anchor="n",
                                     fill=PALETTE["muted"], font=("Segoe UI", 7))
            try:
                cur_dt += full_step
            except OverflowError:
                break

    def _draw_axis_realtime_approx(self, w, bar_y, bar_h,
                                   ya_start: float, ya_end: float, ref: float):
        """Draw an approximate axis for calendar years outside datetime range."""
        span_seconds = max(1e-6, (ya_start - ya_end) * ASTRO_YEAR_SECONDS)
        target_ticks = max(4, min(10, w // 110))
        step_sec     = pick_tick_step(span_seconds, target_ticks)

        if step_sec >= ASTRO_YEAR_SECONDS:
            now_year = now_year_decimal()
            step_years = max(1.0, step_sec / ASTRO_YEAR_SECONDS)
            year_start = now_year - ya_start
            year_end   = now_year - ya_end
            first_year = math.floor(year_start / step_years) * step_years
            year = first_year
            eps = step_years * 1e-6
            safety = 0
            while year <= year_end + eps and safety < 500:
                safety += 1
                if year >= year_start - eps:
                    ya = now_year - year
                    label = format_calendar_year(math.floor(year))
                    self._draw_realtime_tick(w, bar_y, bar_h, ref, ya, label)
                year += step_years
            return

        first_tick = math.floor((ya_end * ASTRO_YEAR_SECONDS) / step_sec) * step_sec
        end_tick = ya_start * ASTRO_YEAR_SECONDS
        t = first_tick
        eps = step_sec * 1e-6
        safety = 0
        while t <= end_tick + eps and safety < 500:
            safety += 1
            ya = t / ASTRO_YEAR_SECONDS
            if ya >= ya_end - eps / ASTRO_YEAR_SECONDS:
                label = format_real_date_label(ya, step_sec)
                self._draw_realtime_tick(w, bar_y, bar_h, ref, ya, label)
            t += step_sec

    def _draw_realtime_tick(self, w, bar_y, bar_h, ref, years_ago, label):
        frac = (ref - years_ago) / ref
        x    = self._frac_to_x(frac)
        self.create_line(x, bar_y + bar_h // 2,
                         x, bar_y + bar_h // 2 + 5,
                         fill=PALETTE["muted"], width=1)
        for j, line in enumerate(label.split("\n")):
            self.create_text(x, bar_y + bar_h // 2 + 7 + j * 10,
                             text=line, anchor="n",
                             fill=PALETTE["muted"], font=("Segoe UI", 7))

    def _draw_events(self, w, h, bar_y, bar_h):
        # Cleared each redraw — hover hit-test uses these rectangles.
        self._event_hits = []

        if not self.events:
            self.create_text(w//2, bar_y - 40,
                             text="Aucun évènement — ajoutez-en dans le panneau gauche",
                             fill=PALETTE["muted"], font=("Segoe UI", 9, "italic"))
            return

        visible = [ev for ev in self.events
                   if self._view_start - 0.001 <= ev.fraction <= self._view_end + 0.001]
        if not visible:
            self.create_text(w//2, bar_y - 40,
                             text="Aucun évènement visible — dézoomez ou faites glisser la vue",
                             fill=PALETTE["muted"], font=("Segoe UI", 9, "italic"))
            return

        rows = self._assign_rows(visible, w)
        ROW_H = 16

        for ev in visible:
            x   = self._frac_to_x(ev.fraction)
            row = rows.get(id(ev), 0)
            top = bar_y - bar_h//2 - (row + 1) * ROW_H - 4

            # Dashed line
            self.create_line(x, top + ROW_H - 2, x, bar_y - bar_h//2,
                             fill=ev.color, width=1, dash=(3, 2))

            # Diamond on bar
            s = 5
            self.create_polygon(x, bar_y - bar_h//2 - s,
                                 x + s, bar_y,
                                 x, bar_y + bar_h//2 + s,
                                 x - s, bar_y,
                                 fill=ev.color, outline="")

            # Label pill
            label = ev.name if len(ev.name) <= 22 else ev.name[:20] + "…"
            lw    = len(label) * 5 + 10
            ly    = top + ROW_H - 4
            x0_pill, y0_pill = x - lw//2, ly - 12
            x1_pill, y1_pill = x + lw//2, ly + 2
            self.create_rectangle(x0_pill, y0_pill, x1_pill, y1_pill,
                                   fill=PALETTE["panel2"], outline=ev.color, width=1)
            self.create_text(x, ly - 5, text=label, anchor="center",
                             fill=ev.color, font=("Segoe UI", 7, "bold"))

            # Cache an enlarged hit zone covering pill, dashed line and diamond
            # so hovering anywhere on the event triggers the tooltip.
            self._event_hits.append((
                ev,
                min(x0_pill, x - s) - 1,
                y0_pill - 1,
                max(x1_pill, x + s) + 1,
                bar_y + bar_h // 2 + s + 1,
            ))

    def _assign_rows(self, events, w):
        MIN_GAP = 84
        rows: list[float] = []
        result: dict[int, int] = {}
        for ev in sorted(events, key=lambda e: e.fraction):
            x      = self._frac_to_x(ev.fraction)
            placed = False
            for r, last_x in enumerate(rows):
                if x - last_x >= MIN_GAP:
                    result[id(ev)] = r
                    rows[r] = x
                    placed = True
                    break
            if not placed:
                result[id(ev)] = len(rows)
                rows.append(x)
        return result

    def _draw_periods(self, w, h, bar_y, bar_h):
        self._period_hits = []  # cleared each redraw, used for hover detection
        self._period_scroll_metrics_cache = None
        if not self.periods:
            return

        # Reserve area below the axis labels and above the minimap.
        AREA_TOP = bar_y + bar_h // 2 + 44   # below axis ticks/labels
        AREA_BOT = h - 14                    # above minimap
        if AREA_BOT - AREA_TOP < 22:
            return

        # Filter & assign vertical rows to avoid overlap.
        visible = [p for p in self.periods
                   if not (p.fraction_end < self._view_start - 0.001
                           or p.fraction_start > self._view_end + 0.001)]
        if not visible:
            return

        rows: list[float] = []
        assignment: dict[int, int] = {}
        for p in sorted(visible, key=lambda x: x.fraction_start):
            xs = self._frac_to_x(p.fraction_start)
            xe = self._frac_to_x(p.fraction_end)
            placed = False
            for r, last_xe in enumerate(rows):
                if xs - last_xe >= 4:
                    assignment[id(p)] = r
                    rows[r] = xe
                    placed = True
                    break
            if not placed:
                assignment[id(p)] = len(rows)
                rows.append(xe)

        n_rows = max(len(rows), 1)
        viewport_h = AREA_BOT - AREA_TOP
        row_h  = max(20, min(40, viewport_h // n_rows))
        content_h = n_rows * row_h
        max_scroll = max(0.0, content_h - viewport_h)
        self._period_scroll_y = max(0.0, min(max_scroll, self._period_scroll_y))

        scrollbar_w = 8
        gutter = 14 if max_scroll > 0 else 0
        period_right = w - gutter
        track_rect = (w - scrollbar_w - 3, AREA_TOP, w - 3, AREA_BOT)
        thumb_rect = None
        if max_scroll > 0:
            track_h = viewport_h
            thumb_h = max(24, track_h * viewport_h / max(content_h, 1))
            travel = max(1.0, track_h - thumb_h)
            thumb_y = AREA_TOP + (self._period_scroll_y / max_scroll) * travel
            thumb_rect = (track_rect[0], thumb_y, track_rect[2], thumb_y + thumb_h)
            self._period_scroll_metrics_cache = {
                "area_rect": (0, AREA_TOP, w, AREA_BOT),
                "track_rect": track_rect,
                "thumb_rect": thumb_rect,
                "track_h": track_h,
                "thumb_h": thumb_h,
                "viewport_h": viewport_h,
                "content_h": content_h,
                "max_scroll": max_scroll,
                "row_h": row_h,
            }

        for p in visible:
            xs = self._frac_to_x(p.fraction_start)
            xe = self._frac_to_x(p.fraction_end)
            x0 = max(-2, xs)
            x1 = min(period_right + 2, xe)
            row = assignment.get(id(p), 0)
            y0  = AREA_TOP + row * row_h - self._period_scroll_y
            y1  = y0 + row_h - 4
            if y1 < AREA_TOP or y0 > AREA_BOT:
                continue
            cy0 = max(AREA_TOP, y0)
            cy1 = min(AREA_BOT, y1)
            if cy1 - cy0 < 3:
                continue

            # Cache hit-test rectangle for tooltip on hover.
            self._period_hits.append((p, x0, cy0, x1, cy1))

            # Hatched fill block, solid colored border.
            self.create_rectangle(x0, cy0, x1, cy1,
                                   fill=p.color, outline=p.color, width=1,
                                   stipple="gray25")
            # End-cap markers: vertical bars at start & end (clipped to view).
            if xs >= -2:
                self.create_line(xs, cy0, xs, cy1, fill=p.color, width=2)
            if xe <= period_right + 2:
                self.create_line(xe, cy0, xe, cy1, fill=p.color, width=2)

            block_w = x1 - x0
            suffix  = "  ·  en cours" if getattr(p, "is_ongoing", False) \
                      else f"  ·  {p.duration_str}"
            label   = f"{p.name}{suffix}"
            label_y = (cy0 + cy1) // 2
            if cy1 - cy0 >= 12 and block_w >= 90:
                self.create_text((x0 + x1) // 2, label_y,
                                  text=label, fill=PALETTE["text"],
                                  font=("Segoe UI", 8, "bold"))
            elif cy1 - cy0 >= 12 and block_w >= 36:
                self.create_text((x0 + x1) // 2, label_y,
                                  text=p.name[:14], fill=PALETTE["text"],
                                  font=("Segoe UI", 7, "bold"))
            # When block is too narrow to hold any label, draw it just to the right.
            elif cy1 - cy0 >= 12 and xe < period_right:
                self.create_text(xe + 4, label_y,
                                  text=label, anchor="w",
                                  fill=p.color, font=("Segoe UI", 7))

        if max_scroll > 0 and thumb_rect is not None:
            self.create_rectangle(track_rect[0], track_rect[1],
                                  track_rect[2], track_rect[3],
                                  fill=PALETTE["bg"], outline=PALETTE["border"])
            self.create_rectangle(thumb_rect[0], thumb_rect[1],
                                  thumb_rect[2], thumb_rect[3],
                                  fill=PALETTE["muted"], outline="")

    def _draw_minimap(self, w, h):
        mm_h = 4
        mm_y = h - mm_h - 2
        self.create_rectangle(0, mm_y, w, mm_y + mm_h,
                               fill=PALETTE["border"], outline="")
        self.create_rectangle(int(self._view_start * w), mm_y,
                               int(self._view_end * w), mm_y + mm_h,
                               fill=PALETTE["accent"], outline="")
        for ev in self.events:
            mx = int(ev.fraction * w)
            self.create_rectangle(mx - 1, mm_y, mx + 1, mm_y + mm_h,
                                   fill=ev.color, outline="")
        # Periods on the minimap as thin colored lanes.
        for p in self.periods:
            mxs = int(p.fraction_start * w)
            mxe = int(p.fraction_end   * w)
            self.create_rectangle(mxs, mm_y - 2, mxe, mm_y - 1,
                                   fill=p.color, outline="")


# ── Edit dialog ────────────────────────────────────────────────────────────────
