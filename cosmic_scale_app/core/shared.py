"""
Cosmic Time Scale
Transpose any event from a cosmic period onto a human-scale reference.
Supports "X years ago", absolute date/time entry, and preset events.
Multiple events displayed on a zoomable, pannable timeline.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import datetime
import math
import sys


def _app_dir() -> Path:
    """Folder where `autosave.events` and user `.events` files live.

    - When running as a script  → the project root (parents[2] of this file).
    - When packaged with PyInstaller (`--onefile` or `--onedir`) →
      the directory that *contains the .exe* (NOT the temporary `_MEIPASS`
      where bundled resources are extracted), so the autosave is read and
      written next to the executable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_DIR       = _app_dir()
AUTOSAVE_PATH = APP_DIR / "autosave.events"
FILE_TYPES = [
    ("Fichier d'évènements", "*.events"),
    ("JSON",                 "*.json"),
    ("Tous fichiers",        "*.*"),
]

# ── Constants ──────────────────────────────────────────────────────────────────

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR   = 3600
SECONDS_PER_DAY    = 86_400
# Display target uses an exact 365-day calendar year so fraction=1 lands on
# "31 déc 23h59m59" rather than overflowing into a 366th day at 06h.
SECONDS_PER_YEAR   = 365 * SECONDS_PER_DAY
# Date math uses the Julian year (365.25 d) for accurate "years ago" conversions.
ASTRO_YEAR_SECONDS = 365.25 * SECONDS_PER_DAY
SECOND_DISPLAY_DECIMALS = 8

REFERENCE_PERIODS = {
    "Big Bang → aujourd'hui  (13,8 Ga)":              13_800_000_000,
    "Formation de la Terre → aujourd'hui  (4,54 Ga)":  4_540_000_000,
    "Apparition de la vie → aujourd'hui  (3,8 Ga)":    3_800_000_000,
    "Ère des dinosaures → aujourd'hui  (252 Ma)":         252_000_000,
    "Homo sapiens → aujourd'hui  (300 000 ans)":              300_000,
    "Personnalisé…": None,
}

TARGET_SCALES = {
    "1 jour  (24 h)":             SECONDS_PER_DAY,
    "1 an  (365 j)":              SECONDS_PER_YEAR,
    "1 siècle  (100 ans)":        100  * SECONDS_PER_YEAR,
    "1 millénaire  (1 000 ans)":  1000 * SECONDS_PER_YEAR,
    "1 heure":                    SECONDS_PER_HOUR,
    "Temps reel (dates reelles)": "__REALTIME__",
    "Personnalisé…":              None,
}

MONTH_NAMES = ["jan", "fév", "mar", "avr", "mai", "jun",
               "jul", "aoû", "sep", "oct", "nov", "déc"]
MONTH_NAMES_FULL = ["janvier", "février", "mars", "avril", "mai", "juin",
                    "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}" \
           f"{max(0, min(255, g)):02x}" \
           f"{max(0, min(255, b)):02x}"


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of an sRGB hex color, in [0, 1]."""
    r, g, b = hex_to_rgb(hex_color)
    def _ch(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)


def contrast_text_color(bg_hex: str) -> str:
    """Return a readable foreground (black or white) for the given background."""
    return "#0d1117" if relative_luminance(bg_hex) > 0.45 else "#f5f9ff"


def shade_color(hex_color: str, factor: float) -> str:
    """
    Lighten (factor>0) or darken (factor<0) an sRGB hex color, keeping the hue.
    factor = 0 → unchanged.  factor = +1 → white.  factor = -1 → black.
    """
    factor = max(-1.0, min(1.0, factor))
    r, g, b = hex_to_rgb(hex_color)
    if factor >= 0:
        r = round(r + (255 - r) * factor)
        g = round(g + (255 - g) * factor)
        b = round(b + (255 - b) * factor)
    else:
        r = round(r * (1 + factor))
        g = round(g * (1 + factor))
        b = round(b * (1 + factor))
    return rgb_to_hex(r, g, b)


def child_default_color(parent_hex: str, key: str) -> str:
    """Default color for a sub-group: a deterministic shade variation of
    its parent, keeping the hue but shifting lightness."""
    if not parent_hex:
        return "#58a6ff"
    import hashlib
    h = hashlib.md5(key.encode("utf-8")).digest()
    bucket = h[0] / 255.0
    factor = (bucket * 2.0 - 1.0) * 0.45     # noticeable but not extreme
    return shade_color(parent_hex, factor)


def color_variant_for(base_hex: str, key: str) -> str:
    """Deterministic shade variation for an item inside a group.

    Two items in the same group keep the same hue but get slightly different
    lightness so they remain distinguishable on the timeline.
    """
    if not key:
        return base_hex
    # Hash the name to a stable shade in [-0.25, +0.25] around the base.
    import hashlib
    h = hashlib.md5(key.encode("utf-8")).digest()
    bucket = h[0] / 255.0          # in [0, 1)
    factor = (bucket * 2.0 - 1.0) * 0.30   # in [-0.30, +0.30]
    return shade_color(base_hex, factor)


EVENT_COLORS = [
    "#58a6ff", "#f78166", "#3fb950", "#d2a8ff", "#ffa657",
    "#79c0ff", "#ff7b72", "#56d364", "#bc8cff", "#ffb347",
    "#39d353", "#e3b341", "#f0883e", "#a5d6ff", "#ffa8a8",
]

PALETTE = {
    "bg":      "#0d1117",
    "panel":   "#161b22",
    "panel2":  "#1c2128",
    "border":  "#30363d",
    "accent":  "#58a6ff",
    "accent2": "#f78166",
    "text":    "#e6edf3",
    "muted":   "#8b949e",
    "success": "#3fb950",
    "entry":   "#21262d",
    "hover":   "#2d333b",
}


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class CosmicEvent:
    name: str
    years_ago: float
    color: str
    description: str = ""
    # Single group membership — was `tag_names: list[str]` historically.
    group_name: str = "Non-classés"
    # ISO 8601 absolute date (e.g. "1979-12-05T02:39:00") when the event has a
    # known calendar moment. This is the authoritative source for stable display
    # across sessions; `years_ago` is recomputed from it on load.
    absolute_date: Optional[str] = None
    fraction: float = 0.0
    result_str: str = ""


@dataclass
class CosmicTag:
    """Group of related events / periods with a shared base color.

    `parent_name` makes groups hierarchical: when set, the group is a
    sub-group of the named parent. Items only ever reference a single
    group (`group_name`) — the tree is purely organisational and dictates
    cascading visibility / color defaults / filter expansion.
    """
    name: str
    color: str = "#58a6ff"            # base color of the group
    visible: bool = True
    locked_visible: bool = False
    parent_name: Optional[str] = None


@dataclass
class CosmicPeriod:
    name: str
    years_ago_start: float    # the older bound (further in the past)
    years_ago_end:   float    # the more recent bound
    color: str
    description: str = ""
    # Single group membership.
    group_name: str = "Non-classés"
    # ISO absolute dates for each bound, when known (calendar dates).
    absolute_date_start: Optional[str] = None
    absolute_date_end:   Optional[str] = None
    # Ongoing: end is always "now" — years_ago_end and absolute_date_end are
    # ignored (recomputed each render).
    is_ongoing: bool = False
    fraction_start:  float = 0.0
    fraction_end:    float = 0.0
    start_str:       str   = ""
    end_str:         str   = ""
    duration_str:    str   = ""


def format_duration_seconds(s: float) -> str:
    """Pretty-print a duration in seconds at an appropriate unit."""
    s = max(0.0, s)
    if s >= SECONDS_PER_YEAR:    return f"{s / SECONDS_PER_YEAR:.2f} an"
    if s >= 30 * SECONDS_PER_DAY: return f"{s / SECONDS_PER_DAY:.1f} j"
    if s >= SECONDS_PER_DAY:     return f"{s / SECONDS_PER_DAY:.2f} j"
    if s >= SECONDS_PER_HOUR:    return f"{s / SECONDS_PER_HOUR:.2f} h"
    if s >= SECONDS_PER_MINUTE:  return f"{s / SECONDS_PER_MINUTE:.2f} min"
    if s >= 1:                   return f"{s:.{SECOND_DISPLAY_DECIMALS}f} s"
    if s >= 1e-3:                return f"{s * 1000:.2f} ms"
    return f"{s * 1e6:.2f} µs"


# ── Time helpers ───────────────────────────────────────────────────────────────

# Frozen "now" for the whole session: prevents date_to_years_ago and
# years_ago_to_datetime from drifting against a moving wall clock, which used
# to change an event's time-of-day every time the target scale was recomputed.
_SESSION_NOW: datetime.datetime = datetime.datetime.now()


def session_now() -> datetime.datetime:
    return _SESSION_NOW


def now_year_decimal() -> float:
    now   = _SESSION_NOW
    start = datetime.datetime(now.year, 1, 1)
    end   = datetime.datetime(now.year + 1, 1, 1)
    return now.year + (now - start).total_seconds() / (end - start).total_seconds()


def date_to_years_ago(year: int, month: int = 1, day: int = 1,
                       hour: int = 0, minute: int = 0, second: int = 0) -> float:
    if 1 <= year <= 9999:
        try:
            delta = _SESSION_NOW - datetime.datetime(year, month, day, hour, minute, second)
            return delta.total_seconds() / ASTRO_YEAR_SECONDS
        except ValueError:
            pass
    event_decimal = year + (month - 1) / 12 + (day - 1) / 365.25
    return now_year_decimal() - event_decimal


def parse_years_ago(text: str) -> Optional[float]:
    t = text.strip().lower().replace(",", ".").replace(" ", "")
    multiplier = 1.0
    for suffix, mult in [("ga", 1e9), ("ma", 1e6), ("ka", 1e3),
                          ("milliard", 1e9), ("billion", 1e9),
                          ("million", 1e6), ("mille", 1e3)]:
        if t.endswith(suffix):
            multiplier = mult
            t = t[:-len(suffix)]
            break
    try:
        return float(t) * multiplier
    except ValueError:
        return None


def years_ago_to_datetime(years_ago: float) -> Optional[datetime.datetime]:
    try:
        dt = _SESSION_NOW - datetime.timedelta(
            seconds=years_ago * ASTRO_YEAR_SECONDS)
        return _snap_datetime_to_second(dt)
    except OverflowError:
        return None


def _snap_datetime_to_second(dt: datetime.datetime,
                             tolerance_us: int = 1000) -> datetime.datetime:
    """Remove tiny float round-trip errors around exact second boundaries."""
    if dt.microsecond <= tolerance_us:
        return dt.replace(microsecond=0)
    if 1_000_000 - dt.microsecond <= tolerance_us:
        return (dt + datetime.timedelta(
            microseconds=1_000_000 - dt.microsecond)).replace(microsecond=0)
    return dt


def years_ago_to_iso(years_ago: float) -> Optional[str]:
    """
    Render `years_ago` as an ISO 8601 calendar date — but only when it falls
    inside the representable Gregorian range (year 1..9999). Geological /
    cosmological events return None and stay anchored to `years_ago`.
    """
    dt = years_ago_to_datetime(years_ago)
    if dt is None or not (1 <= dt.year <= 9999):
        return None
    return dt.isoformat(timespec="microseconds")


def iso_to_years_ago(iso: str) -> Optional[float]:
    """Inverse of `years_ago_to_iso`, using the (frozen) session clock."""
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    delta = _SESSION_NOW - dt
    return delta.total_seconds() / ASTRO_YEAR_SECONDS


def format_calendar_year(year: int) -> str:
    return f"{year:,}" if year >= 1 else f"{1 - year:,} av. J.-C."


def approximate_calendar_year(years_ago: float) -> int:
    return math.floor(now_year_decimal() - years_ago)


def format_second_display(seconds: float,
                          decimals: int = SECOND_DISPLAY_DECIMALS) -> str:
    width = decimals + 3
    return f"{seconds:0{width}.{decimals}f}"


def format_real_date_label(years_ago: float, step_sec: Optional[float] = None) -> str:
    dt = years_ago_to_datetime(years_ago)
    if dt is None:
        year_label = format_calendar_year(approximate_calendar_year(years_ago))
        if step_sec is not None and step_sec >= ASTRO_YEAR_SECONDS:
            return year_label
        return f"vers {year_label}"

    short_date = f"{dt.day} {MONTH_NAMES[dt.month - 1]}"
    if step_sec is None:
        sec = dt.second + dt.microsecond / 1_000_000
        return (f"Le {dt.day} {MONTH_NAMES_FULL[dt.month - 1]} {dt.year}\n"
                f"a {dt.hour:02d}h {dt.minute:02d}min {format_second_display(sec)}s")
    if step_sec >= 5 * ASTRO_YEAR_SECONDS:
        return str(dt.year)
    if step_sec >= 30 * SECONDS_PER_DAY:
        return f"{MONTH_NAMES[dt.month - 1]}\n{dt.year}"
    if step_sec >= SECONDS_PER_DAY:
        return f"{short_date}\n{dt.year}"
    if step_sec >= SECONDS_PER_HOUR:
        return f"{short_date}\n{dt.hour:02d}h"
    if step_sec >= SECONDS_PER_MINUTE:
        return f"{short_date}\n{dt.hour:02d}:{dt.minute:02d}"
    if step_sec >= 1:
        return f"{short_date}\n{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    sec = dt.second + dt.microsecond / 1_000_000
    return f"{short_date}\n{dt.hour:02d}:{dt.minute:02d}:{format_second_display(sec)}"


def fraction_to_position(frac: float, target_seconds: float) -> dict:
    # Clamp just below the boundary so frac=1 reads as "23:59:59.999..." of the
    # last unit instead of wrapping into the next period.
    s             = max(0.0, min(frac * target_seconds, target_seconds - 1e-6))
    day_of_year   = int(s / SECONDS_PER_DAY)
    rem           = s - day_of_year * SECONDS_PER_DAY
    hour          = int(rem // SECONDS_PER_HOUR);   rem -= hour * SECONDS_PER_HOUR
    minute        = int(rem // SECONDS_PER_MINUTE); second = rem - minute * SECONDS_PER_MINUTE
    d = day_of_year
    month_idx = 11
    for i, dm in enumerate(MONTH_DAYS):
        if d < dm:
            month_idx = i
            break
        d -= dm
    else:
        d = MONTH_DAYS[11] - 1
    return dict(day_of_year=day_of_year + 1,
                month_name=MONTH_NAMES_FULL[month_idx],
                month_short=MONTH_NAMES[month_idx],
                month_num=month_idx + 1,
                day_of_month=d + 1,
                hour=hour, minute=minute, second=second,
                fraction=frac)


def format_result(pos: dict, target_seconds: float,
                  realtime_ref_years: Optional[float] = None,
                  realtime_years_ago: Optional[float] = None) -> str:
    pct = pos["fraction"] * 100
    if realtime_ref_years is not None:
        # Prefer the caller-provided exact `years_ago`. Recovering it via
        # `ref * (1 - fraction)` loses ~tens of seconds of precision because
        # of float64 cancellation when the event sits very close to "now"
        # but the reference is in Ga (e.g. 34 yr / 13.8 Ga).
        if realtime_years_ago is not None:
            years_ago = max(0.0, realtime_years_ago)
        else:
            years_ago = max(0.0, realtime_ref_years * (1.0 - pos["fraction"]))
        date_label = format_real_date_label(years_ago)
        precision = 2 if years_ago < 10_000 else 0
        return (f"{date_label}\n"
                f"(il y a {years_ago:,.{precision}f} ans · {pct:.4f}%)")

    # ── 1-year scale ──────────────────────────────────────────────────────────
    if abs(target_seconds - SECONDS_PER_YEAR) < 0.5:
        return (f"Le {pos['day_of_month']} {pos['month_name']}\n"
                f"à {pos['hour']:02d}h {pos['minute']:02d}min {format_second_display(pos['second'])}s\n"
                f"(jour {pos['day_of_year']} · {pct:.4f}%)")

    # ── 1-day scale ───────────────────────────────────────────────────────────
    if abs(target_seconds - SECONDS_PER_DAY) < 0.5:
        ts = pos["fraction"] * SECONDS_PER_DAY
        h  = int(ts // SECONDS_PER_HOUR);   ts -= h * SECONDS_PER_HOUR
        m  = int(ts // SECONDS_PER_MINUTE); sc = ts - m * SECONDS_PER_MINUTE
        return f"{h:02d}h {m:02d}min {format_second_display(sc)}s\n({pct:.4f}%)"

    # ── 1-hour scale ──────────────────────────────────────────────────────────
    if abs(target_seconds - SECONDS_PER_HOUR) < 0.5:
        ts = pos["fraction"] * SECONDS_PER_HOUR
        m  = int(ts // SECONDS_PER_MINUTE); sc = ts - m * SECONDS_PER_MINUTE
        return f"{m}min {format_second_display(sc)}s\n({pct:.4f}%)"

    # ── Multi-year scales (siècle, millénaire, custom) ────────────────────────
    if target_seconds >= 1.5 * SECONDS_PER_YEAR:
        s   = pos["fraction"] * target_seconds
        yr  = int(s // SECONDS_PER_YEAR)
        rem = s - yr * SECONDS_PER_YEAR
        d   = int(rem // SECONDS_PER_DAY); rem -= d * SECONDS_PER_DAY
        h   = int(rem // SECONDS_PER_HOUR); rem -= h * SECONDS_PER_HOUR
        m   = int(rem // SECONDS_PER_MINUTE); sc = rem - m * SECONDS_PER_MINUTE
        mi, dm = _month_day_from_day_of_year(min(d, 364))
        return (f"An {yr+1}, le {dm+1} {MONTH_NAMES_FULL[mi]}\n"
                f"à {h:02d}h {m:02d}min {format_second_display(sc)}s\n"
                f"(jour {d+1} de l'année · {pct:.4f}%)")

    # ── Generic fallback ──────────────────────────────────────────────────────
    ts   = pos["fraction"] * target_seconds
    days = int(ts // SECONDS_PER_DAY);  ts -= days * SECONDS_PER_DAY
    h    = int(ts // SECONDS_PER_HOUR); ts -= h * SECONDS_PER_HOUR
    m    = int(ts // SECONDS_PER_MINUTE); sc = ts - m * SECONDS_PER_MINUTE
    return f"Jour {days+1}  ·  {h:02d}h {m:02d}min {format_second_display(sc)}s\n({pct:.4f}%)"


# Tick steps in seconds, sorted ascending. Used to pick a "nice" interval at
# any zoom level, from 1 ms up to 100 years.
NICE_STEPS = [
    0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5,
    1, 2, 5, 10, 15, 30,
    60, 120, 300, 600, 900, 1800,
    3600, 7200, 10800, 21600, 43200,
    86400, 2 * 86400, 7 * 86400,
    30.4375 * 86400, 91.3125 * 86400, 182.625 * 86400,
    365.25 * 86400, 10 * 365.25 * 86400, 100 * 365.25 * 86400,
]


def pick_tick_step(span_seconds: float, target_ticks: int = 8) -> float:
    rough = span_seconds / max(1, target_ticks)
    for s in NICE_STEPS:
        if s >= rough:
            return s
    rough_years = max(1.0, rough / ASTRO_YEAR_SECONDS)
    magnitude = 10 ** math.floor(math.log10(rough_years))
    for factor in (1, 2, 5, 10):
        candidate_years = factor * magnitude
        if candidate_years >= rough_years:
            return candidate_years * ASTRO_YEAR_SECONDS
    return rough


def _month_day_from_day_of_year(day_of_year: int) -> tuple[int, int]:
    """Return (month_idx 0-11, day_in_month 0-based) from a 0-based day of year."""
    d = day_of_year
    for i, dm in enumerate(MONTH_DAYS):
        if d < dm:
            return i, d
        d -= dm
    return 11, MONTH_DAYS[11] - 1


def _format_axis_overflow_label(offset_seconds: float, step_sec: float) -> str:
    """Format ticks that sit outside the compressed reference period."""
    sign = "-" if offset_seconds < 0 else "+"
    s = abs(offset_seconds)
    if step_sec >= SECONDS_PER_YEAR:
        years = s / SECONDS_PER_YEAR
        unit = "an" if years < 2 else "ans"
        return f"{sign}{years:,.0f} {unit}"
    if step_sec >= SECONDS_PER_DAY:
        return f"{sign}{s / SECONDS_PER_DAY:,.0f} j"
    if step_sec >= SECONDS_PER_HOUR:
        return f"{sign}{s / SECONDS_PER_HOUR:,.0f} h"
    if step_sec >= SECONDS_PER_MINUTE:
        minutes = int(s // SECONDS_PER_MINUTE)
        seconds = int(s - minutes * SECONDS_PER_MINUTE)
        return f"{sign}{minutes}:{seconds:02d}"
    if step_sec >= 1:
        minutes = int(s // SECONDS_PER_MINUTE)
        seconds = int(s - minutes * SECONDS_PER_MINUTE)
        return f"{sign}{minutes}:{seconds:02d}"
    return f"{sign}{format_second_display(s)}s"


def format_axis_label(seconds: float, target_seconds: float, step_sec: float,
                      realtime_ref_years: Optional[float] = None) -> str:
    """Format a position on the timeline axis. May return a multi-line string."""
    if realtime_ref_years is not None:
        frac = 0.0 if target_seconds <= 0 else seconds / target_seconds
        years_ago = realtime_ref_years * (1.0 - frac)
        return format_real_date_label(years_ago, step_sec)
    boundary_eps = max(1e-9, step_sec * 1e-9)
    if seconds < -boundary_eps:
        return _format_axis_overflow_label(seconds, step_sec)
    if seconds > target_seconds + boundary_eps:
        return _format_axis_overflow_label(seconds - target_seconds, step_sec)
    # ── 1-year scale ──────────────────────────────────────────────────────────
    if abs(target_seconds - SECONDS_PER_YEAR) < 0.5:
        d   = int(seconds // SECONDS_PER_DAY)
        rem = seconds - d * SECONDS_PER_DAY
        mi, dm = _month_day_from_day_of_year(d)
        h   = int(rem // SECONDS_PER_HOUR);   rem -= h * SECONDS_PER_HOUR
        m   = int(rem // SECONDS_PER_MINUTE); sc  = rem - m * SECONDS_PER_MINUTE
        date = f"{dm+1} {MONTH_NAMES[mi]}"
        if step_sec >= SECONDS_PER_DAY:    return date
        if step_sec >= SECONDS_PER_HOUR:   return f"{date}\n{h:02d}h"
        if step_sec >= 60:                 return f"{date}\n{h:02d}:{m:02d}"
        if step_sec >= 1:                  return f"{date}\n{h:02d}:{m:02d}:{int(sc):02d}"
        return f"{date}\n{h:02d}:{m:02d}:{format_second_display(sc)}"

    # ── 1-day scale ───────────────────────────────────────────────────────────
    if abs(target_seconds - SECONDS_PER_DAY) < 0.5:
        h   = int(seconds // SECONDS_PER_HOUR);   rem = seconds - h * SECONDS_PER_HOUR
        m   = int(rem // SECONDS_PER_MINUTE);     sc  = rem - m * SECONDS_PER_MINUTE
        if step_sec >= SECONDS_PER_HOUR: return f"{h:02d}h"
        if step_sec >= 60:               return f"{h:02d}:{m:02d}"
        if step_sec >= 1:                return f"{h:02d}:{m:02d}:{int(sc):02d}"
        return f"{h:02d}:{m:02d}:{format_second_display(sc)}"

    # ── 1-hour scale ──────────────────────────────────────────────────────────
    if abs(target_seconds - SECONDS_PER_HOUR) < 0.5:
        m  = int(seconds // 60); sc = seconds - m * 60
        if step_sec >= 60: return f"{m}min"
        if step_sec >= 1:  return f"{m}min{int(sc):02d}s"
        return f"{m}min{format_second_display(sc)}s"

    # ── Multi-year scales (century, millennium, custom multi-year) ────────────
    if target_seconds >= 1.5 * SECONDS_PER_YEAR:
        yr  = int(seconds // SECONDS_PER_YEAR)
        rem = seconds - yr * SECONDS_PER_YEAR
        d   = int(rem // SECONDS_PER_DAY)
        mi, dm = _month_day_from_day_of_year(min(d, 364))
        rem -= d * SECONDS_PER_DAY
        h   = int(rem // SECONDS_PER_HOUR); rem -= h * SECONDS_PER_HOUR
        m   = int(rem // SECONDS_PER_MINUTE); sc = rem - m * SECONDS_PER_MINUTE
        if step_sec >= SECONDS_PER_YEAR: return f"An {yr+1}"
        if step_sec >= SECONDS_PER_DAY:  return f"An {yr+1}\n{dm+1} {MONTH_NAMES[mi]}"
        if step_sec >= 60:               return f"An {yr+1}\n{dm+1}{MONTH_NAMES[mi]} {h:02d}:{m:02d}"
        if step_sec >= 1:               return f"An {yr+1}\n{dm+1}{MONTH_NAMES[mi]} {h:02d}:{m:02d}:{int(sc):02d}"
        return f"An {yr+1}\n{dm+1}{MONTH_NAMES[mi]} {h:02d}:{m:02d}:{format_second_display(sc)}"

    # ── Generic fallback ──────────────────────────────────────────────────────
    if step_sec >= 1:    return f"{seconds:,.0f}s"
    return f"{format_second_display(seconds)}s"


# ── Zoomable Timeline ──────────────────────────────────────────────────────────
