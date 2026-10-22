"""NCU gym desktop widget with live count, daily chart, and trend estimate."""

import csv
import ctypes
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageSequence

from gym_core import (
    CLOSE_TIME,
    COMFORT_THRESHOLD,
    GymCountUnavailable,
    OPEN_TIME,
    OccupancyReading,
    OccupancyStatus,
    PAGE_URL,
    build_csv_url,
    estimate_trend,
    is_regular_open_time,
    parse_gym_count,
)
from monitor_instance import MonitorInstance
from widget_window import (
    MIN_HEIGHT,
    MIN_WIDTH,
    Geometry,
    JsonWindowState,
    WidgetWindowBehavior,
    connected_screen_areas,
    enable_per_monitor_dpi_awareness,
    window_state_path,
)


# ===== Paths =====
# Use the folder where this .py/.pyw file is located as the base directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GIF_DIR = os.path.join(BASE_DIR, "gif")
LOG_DIR = os.path.join(BASE_DIR, "gym_count")


# ===== Settings =====
REFRESH_MS = 10_000          # UI refresh every 10 sec
LOG_INTERVAL_MS = 60_000     # save one point every 60 sec
GIF_SIZE = (150, 150)
CHART_MIN_SIZE = (360, 390)
COMPACT_BREAKPOINT = (350, 180)
AUTOSTART_VALUE_NAME = "NCUGymRealTimeMonitor"

THEME_PALETTES = {
    "morandi_lace": {
        "name": "莫蘭迪玫瑰",
        "window": "#DED1E5",
        "card": "#F4EAF1",
        "text": "#3F2D41",
        "muted": "#7D687E",
        "line": "#D8C4D5",
        "track": "#E4D2E0",
        "series": "#9B72CF",
        "series_soft": "#E7D9F0",
        "threshold": "#62A083",
        "hover": "#E8D8E5",
        "ornament": "flowers",
        "ornament_color": "#B997B4",
        "flower": "rose",
        "flower_layout": "staggered",
        "flower_center": "#886885",
        "swatch": "#B997B4",
        "states": {
            "loading": ("#A487A7", "#604B63", "#E6D7E7", "讀取中"),
            "comfortable": ("#5E9A7E", "#315E4A", "#D7EADF", "舒適"),
            "moderate": ("#D58B62", "#75442E", "#F2DDD0", "稍多人"),
            "busy": ("#CC6680", "#7A3448", "#F0D5DE", "較擁擠"),
        },
    },
    "peach_cream": {
        "name": "奶油小花",
        "window": "#E6D5CE",
        "card": "#F5EAE4",
        "text": "#493532",
        "muted": "#846B65",
        "line": "#DDC6BC",
        "track": "#E8D5CC",
        "series": "#C77C71",
        "series_soft": "#EED8D1",
        "threshold": "#6E9A7D",
        "hover": "#ECDCD5",
        "ornament": "flowers",
        "ornament_color": "#F0CDBB",
        "flower": "buttercup",
        "flower_layout": "bottom",
        "flower_center": "#D99A69",
        "swatch": "#D49A8B",
        "states": {
            "loading": ("#B18A82", "#684D48", "#E9D7D1", "讀取中"),
            "comfortable": ("#639477", "#365B48", "#D9E7DD", "舒適"),
            "moderate": ("#CC875B", "#75462E", "#F0D9C9", "稍多人"),
            "busy": ("#C66076", "#793748", "#EED3DA", "較擁擠"),
        },
    },
    "blush_pink": {
        "name": "櫻花粉霧",
        "window": "#F1DDE2",
        "card": "#F9EAED",
        "text": "#51383D",
        "muted": "#8A6D74",
        "line": "#E8CAD1",
        "track": "#F0D9DE",
        "series": "#D58A9D",
        "series_soft": "#F5DDE3",
        "threshold": "#779984",
        "hover": "#F3E0E4",
        "ornament": "flowers",
        "ornament_color": "#E27891",
        "flower": "sakura",
        "flower_layout": "diagonal",
        "flower_center": "#AF5066",
        "swatch": "#EDACBA",
        "states": {
            "loading": ("#C18B97", "#704D55", "#EFD8DD", "讀取中"),
            "comfortable": ("#66917A", "#385B4A", "#D8E6DE", "舒適"),
            "moderate": ("#C88A61", "#71472F", "#EFDBC9", "稍多人"),
            "busy": ("#D0647D", "#7A3A49", "#F2D4DB", "較擁擠"),
        },
    },
}
DEFAULT_THEME_KEY = "morandi_lace"

GIF_FILES = {
    "low": os.path.join(GIF_DIR, "gymtime.gif"),
    "mid": os.path.join(GIF_DIR, "blueguy.gif"),
    "high": os.path.join(GIF_DIR, "usingcomputer.gif")
}

state = {
    "csv_url": None,
    "count": None,
    "gif_key": "mid",
    "gif_index": 0,
    "drag_x": 0,
    "drag_y": 0,
    "gif_sets": {},
    "fg": "#111827",
    "bg_card": "#ffffff",
    "last_logged_at": None,
    "last_updated_at": None,
    "fetch_future": None,
    "points_date": None,
    "today_points": [],
    "chart_visible": False,
    "minimized": False,
    "theme": None,
    "theme_key": DEFAULT_THEME_KEY,
}


def _geometry_offset(value):
    return f"+{value}" if value >= 0 else str(value)


def _set_windows_geometry_absolute(window, geometry):
    """Position a Tk window using absolute virtual-screen coordinates.

    Tk interprets a negative geometry offset as a distance from the right or
    bottom edge, not as a coordinate on a monitor left/above the primary one.
    SetWindowPos preserves real negative coordinates across Windows monitors.
    """

    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        widget_handle = window.winfo_id()
        window_handle = user32.GetParent(widget_handle) or widget_handle
        return bool(
            user32.SetWindowPos(
                window_handle,
                0,
                geometry.x,
                geometry.y,
                geometry.width,
                geometry.height,
                0x0004 | 0x0010,
            )
        )
    except (AttributeError, OSError, tk.TclError):
        return False


class TkWindowPort:
    def __init__(self, window, native_setter=None):
        self._window = window
        self._native_setter = native_setter or _set_windows_geometry_absolute

    def geometry(self):
        return Geometry(
            self._window.winfo_width(),
            self._window.winfo_height(),
            self._window.winfo_x(),
            self._window.winfo_y(),
        )

    def set_geometry(self, geometry):
        if self._native_setter(self._window, geometry):
            return
        self._window.geometry(
            f"{geometry.width}x{geometry.height}"
            f"{_geometry_offset(geometry.x)}{_geometry_offset(geometry.y)}"
        )

    def set_cursor(self, cursor):
        self._window.configure(cursor=cursor)


# ===== Logging =====
def init_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def get_today_log_file():
    today_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"gym_count_{today_str}.csv")


def ensure_log_file():
    log_file = get_today_log_file()

    if not os.path.exists(log_file):
        with open(log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "count"])

    return log_file


def should_log_now(now=None):
    now = now or datetime.now()

    if not is_regular_open_time(now):
        return False

    if state["last_logged_at"] is None:
        return True

    elapsed = (now - state["last_logged_at"]).total_seconds()

    if elapsed >= LOG_INTERVAL_MS / 1000:
        return True

    return False


def append_log(count, now=None):
    if count is None:
        return False

    now = now or datetime.now()

    if not should_log_now(now):
        return False

    log_file = ensure_log_file()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, count])

    # Only advance the logging clock after the row was written successfully.
    state["last_logged_at"] = now
    if state["points_date"] != now.date():
        state["points_date"] = now.date()
        state["today_points"] = []
    state["today_points"].append((now, int(count)))
    return True


def load_today_points(now=None):
    """Load today's valid opening-hour samples for the chart and trend."""

    now = now or datetime.now()
    state["points_date"] = now.date()
    state["today_points"] = []
    log_file = get_today_log_file()
    if not os.path.exists(log_file):
        return

    with open(log_file, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                timestamp = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                count = int(row["count"])
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp.date() == now.date() and is_regular_open_time(timestamp):
                state["today_points"].append((timestamp, count))

    state["today_points"].sort(key=lambda point: point[0])
    if state["today_points"]:
        state["last_logged_at"] = state["today_points"][-1][0]


# ===== Data Fetching =====
def get_csv_url(force_refresh=False):
    if state["csv_url"] and not force_refresh:
        return state["csv_url"]

    response = requests.get(
        PAGE_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    state["csv_url"] = build_csv_url(response.text, PAGE_URL)
    return state["csv_url"]


def fetch_count():
    last_error = None
    last_status = OccupancyStatus.DATA_ERROR

    # A cached Google Sheets URL can become stale. Retry once after resolving
    # the iframe again from the official page.
    for attempt in range(2):
        try:
            csv_url = get_csv_url(force_refresh=attempt > 0)
            response = requests.get(
                csv_url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            response.raise_for_status()
            count = parse_gym_count(response.content.decode("utf-8-sig"))
            return OccupancyReading(OccupancyStatus.VALID, count)
        except GymCountUnavailable as exc:
            return OccupancyReading(OccupancyStatus.UNAVAILABLE, detail=str(exc))
        except requests.RequestException as exc:
            last_error = exc
            last_status = OccupancyStatus.OFFLINE
            state["csv_url"] = None
        except Exception as exc:
            last_error = exc
            last_status = OccupancyStatus.DATA_ERROR
            state["csv_url"] = None

    print("fetch_count 錯誤:", last_error)
    return OccupancyReading(last_status, detail=str(last_error))


# ===== GIF =====
def load_gif(path):
    if not os.path.exists(path):
        print("缺少 GIF:", path)
        return [], []

    frames, delays = [], []

    try:
        img = Image.open(path)

        for frame in ImageSequence.Iterator(img):
            delay = frame.info.get("duration", 100) or 100

            frame = frame.convert("RGBA")
            frame.thumbnail(GIF_SIZE)

            frames.append(ImageTk.PhotoImage(frame))
            delays.append(delay)

    except Exception as e:
        print(f"載入 GIF 失敗 {path}:", e)

    return frames, delays


def load_all_gifs():
    state["gif_sets"] = {
        key: load_gif(path)
        for key, path in GIF_FILES.items()
    }


def select_gif_key(count):
    if count is None:
        return "mid"

    if count <= COMFORT_THRESHOLD:
        return "low"

    if count <= 45:
        return "mid"

    return "high"


def animate_gif():
    frames, delays = state["gif_sets"].get(state["gif_key"], ([], []))

    if not frames:
        root.after(300, animate_gif)
        return

    i = state["gif_index"]

    gif_label.config(image=frames[i])
    state["gif_index"] = (i + 1) % len(frames)

    root.after(delays[i], animate_gif)


# ===== Theme =====
def get_theme(n):
    """Return a restrained neutral palette with one semantic accent."""

    palette = THEME_PALETTES.get(
        state.get("theme_key", DEFAULT_THEME_KEY),
        THEME_PALETTES[DEFAULT_THEME_KEY],
    )
    if n is None:
        state_name = "loading"
    elif n <= COMFORT_THRESHOLD:
        state_name = "comfortable"
    elif n <= 45:
        state_name = "moderate"
    else:
        state_name = "busy"

    accent, accent_text, accent_soft, label = palette["states"][state_name]
    base = {key: value for key, value in palette.items() if key != "states"}
    return base | {
        "accent": accent,
        "accent_text": accent_text,
        "accent_soft": accent_soft,
        "label": label,
        "trend_up": palette["states"]["busy"][0],
        "trend_down": palette["states"]["comfortable"][0],
    }


def theme_preference_path():
    return window_state_path().with_name("preferences.json")


def load_theme_preference():
    try:
        data = json.loads(theme_preference_path().read_text(encoding="utf-8"))
        theme_key = data.get("theme")
        if theme_key in THEME_PALETTES:
            return theme_key
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return DEFAULT_THEME_KEY


def save_theme_preference(theme_key):
    path = theme_preference_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"theme": theme_key}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        pass


def draw_ornament():
    if "ornament_top" not in globals():
        return
    theme = state.get("theme") or get_theme(state.get("count"))
    canvases = (
        (ornament_top, True, "top"),
        (ornament_bottom, True, "bottom"),
        (ornament_left, False, "left"),
        (ornament_right, False, "right"),
    )
    for canvas, horizontal, edge in canvases:
        canvas.delete("all")
        canvas.config(bg=theme["card"])
        length = canvas.winfo_width() if horizontal else canvas.winfo_height()
        length = max(length, 40)
        positions = _ornament_positions(theme["flower_layout"], edge, length)
        for position in positions:
            center_x, center_y = (position, 7) if horizontal else (7, position)
            _draw_theme_flower(
                canvas,
                center_x,
                center_y,
                theme,
                horizontal,
            )


def _ornament_positions(layout, edge, length):
    """Place each flower species where its silhouette reads most naturally."""

    if layout == "staggered":
        # Float the roses through the horizontal borders with uneven rhythm and
        # generous margins. This keeps them decorative without boxing the card
        # into four heavy corner clusters.
        fractions = {
            "top": (0.25, 0.52, 0.79),
            "bottom": (0.14, 0.39, 0.66, 0.88),
        }.get(edge, ())
        values = (round(length * fraction) for fraction in fractions)
    elif layout == "bottom":
        values = range(14, length - 7, 30) if edge == "bottom" else ()
    elif layout == "sides":
        values = range(14, length - 7, 30) if edge in ("left", "right") else ()
    elif layout == "diagonal":
        if edge == "top":
            values = (length - 80, length - 46, length - 12)
        elif edge == "bottom":
            values = (12, 46, 80)
        else:
            values = ()
    else:
        values = range(12, length - 7, 34)

    return sorted({int(value) for value in values if 8 <= value <= length - 8})


def _draw_petals(canvas, center_x, center_y, offsets, petal_color, radius):
    for offset_x, offset_y in offsets:
        x = center_x + offset_x
        y = center_y + offset_y
        canvas.create_oval(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            fill=petal_color,
            outline="",
        )


def _draw_theme_flower(canvas, center_x, center_y, theme, horizontal):
    """Draw the flower species assigned to the active color theme."""

    petal = theme["ornament_color"]
    center = theme["flower_center"]
    flower = theme["flower"]

    if flower == "buttercup":
        # Five softly overlapping petals read more clearly at this tiny scale
        # than the previous thin daisy spokes.
        offsets = (
            (0, -3.2),
            (3.1, -1.0),
            (1.9, 2.7),
            (-1.9, 2.7),
            (-3.1, -1.0),
        )
        _draw_petals(canvas, center_x, center_y, offsets, petal, 2.35)
        canvas.create_oval(
            center_x - 2.3,
            center_y - 2.3,
            center_x + 2.3,
            center_y + 2.3,
            fill="#F8E8D8",
            outline="",
        )
    elif flower == "rose":
        offsets = ((0, -3), (3, -2), (3, 2), (0, 3), (-3, 2), (-3, -2))
        _draw_petals(canvas, center_x, center_y, offsets, petal, 2.0)
        canvas.create_arc(
            center_x - 3,
            center_y - 3,
            center_x + 3,
            center_y + 3,
            start=25,
            extent=245,
            style=tk.ARC,
            outline=center,
            width=1,
        )
    else:  # sakura
        offsets = ((0, -4), (4, -1), (2, 4), (-2, 4), (-4, -1))
        _draw_petals(canvas, center_x, center_y, offsets, petal, 2.1)

    canvas.create_oval(
        center_x - 1.5,
        center_y - 1.5,
        center_x + 1.5,
        center_y + 1.5,
        fill=center,
        outline="",
    )


def select_theme(theme_key):
    if theme_key not in THEME_PALETTES:
        return
    state["theme_key"] = theme_key
    save_theme_preference(theme_key)
    apply_theme(state.get("count"))
    update_trend_display()
    draw_chart()


def draw_theme_picker():
    if "theme_picker_canvas" not in globals():
        return
    theme = state.get("theme") or get_theme(state.get("count"))
    theme_picker_canvas.delete("all")
    theme_picker_canvas.config(bg=theme["card"])

    for index, (theme_key, palette) in enumerate(THEME_PALETTES.items()):
        center_x = 10 + index * 18
        radius = 7 if theme_key == state["theme_key"] else 5
        tag = f"theme-{theme_key}"
        theme_picker_canvas.create_oval(
            center_x - radius,
            11 - radius,
            center_x + radius,
            11 + radius,
            fill=palette["swatch"],
            outline="",
            tags=(tag,),
        )
        theme_picker_canvas.tag_bind(
            tag,
            "<Button-1>",
            lambda _event, selected=theme_key: select_theme(selected),
        )


def set_status_badge(text, accent, soft, foreground):
    status_badge.config(text=f"●  {text}", bg=soft, fg=foreground)
    compact_dot.config(fg=accent)


def apply_theme(n):
    theme = get_theme(n)
    state["theme"] = theme

    root.configure(bg=theme["window"])
    outer.config(bg=theme["window"])
    for widget in (
        card,
        full_body,
        compact_body,
        compact_count_row,
        compact_count_label,
        compact_unit_label,
        ornament_top,
        ornament_bottom,
        ornament_left,
        ornament_right,
        top,
        title,
        theme_picker_canvas,
        minimize_btn,
        close_btn,
        content,
        gif_label,
        metrics,
        eyebrow_label,
        count_row,
        count_label,
        unit_label,
        trend_label,
        meter_section,
        meter_header,
        meter_label,
        meter_value_label,
        occupancy_canvas,
        chart_section,
        chart_header,
        chart_title,
        resize_grip,
    ):
        widget.config(bg=theme["card"])

    card.config(
        highlightbackground=theme["line"],
        highlightcolor=theme["line"],
    )
    title.config(fg=theme["text"])
    eyebrow_label.config(fg=theme["muted"])
    minimize_btn.config(fg=theme["muted"])
    close_btn.config(fg=theme["muted"])
    count_label.config(fg=theme["text"])
    unit_label.config(fg=theme["muted"])
    compact_count_label.config(fg=theme["text"])
    compact_unit_label.config(fg=theme["muted"])
    compact_dot.config(bg=theme["card"], fg=theme["accent"])
    meter_label.config(fg=theme["muted"])
    meter_value_label.config(fg=theme["accent_text"])
    chart_title.config(fg=theme["text"])
    resize_grip.config(fg=theme["muted"])
    chart_canvas.config(
        bg=theme["card"],
        highlightbackground=theme["line"],
    )
    set_status_badge(
        theme["label"],
        theme["accent"],
        theme["accent_soft"],
        theme["accent_text"],
    )

    state["fg"] = theme["text"]
    state["bg_card"] = theme["card"]
    draw_theme_picker()
    draw_ornament()
    draw_occupancy_meter()


# ===== UI Update =====
def refresh_data():
    if state["fetch_future"] is None:
        state["fetch_future"] = executor.submit(fetch_count)
        poll_fetch()

    # Keep a stable refresh cadence. If the previous request is still running,
    # the next tick simply waits instead of starting an overlapping request.
    root.after(REFRESH_MS, refresh_data)


def poll_fetch():
    future = state["fetch_future"]
    if future is None:
        return

    if not future.done():
        root.after(100, poll_fetch)
        return

    state["fetch_future"] = None
    try:
        reading = future.result()
    except Exception as exc:
        print("背景更新錯誤:", exc)
        reading = OccupancyReading(OccupancyStatus.DATA_ERROR, detail=str(exc))

    apply_count(reading)


def apply_count(reading):
    if reading.status is not OccupancyStatus.VALID or reading.count is None:
        if state["last_updated_at"] is None:
            apply_theme(None)
            if reading.status is OccupancyStatus.UNAVAILABLE:
                count_var.set("—")
                badge_text = "暫無資料"
            elif reading.status is OccupancyStatus.OFFLINE:
                count_var.set("—")
                badge_text = "離線"
            else:
                count_var.set("—")
                badge_text = "資料異常"
            theme = state["theme"]
            set_status_badge(
                badge_text,
                theme["accent"],
                theme["accent_soft"],
                theme["accent_text"],
            )
        else:
            paused = get_theme(None)
            set_status_badge(
                "暫停更新",
                paused["accent"],
                paused["accent_soft"],
                paused["accent_text"],
            )
        return

    n = reading.count
    state["count"] = n
    state["last_updated_at"] = datetime.now()

    if state["points_date"] != state["last_updated_at"].date():
        load_today_points(state["last_updated_at"])

    apply_theme(n)
    count_var.set(str(n))
    append_log(n, state["last_updated_at"])
    update_trend_display()
    draw_occupancy_meter()
    draw_chart()

    new_key = select_gif_key(n)
    if new_key != state["gif_key"]:
        state["gif_key"] = new_key
        state["gif_index"] = 0


def update_trend_display():
    theme = state.get("theme") or get_theme(state.get("count"))
    trend = estimate_trend(state["today_points"])
    if trend is None:
        trend_var.set("趨勢資料累積中")
        trend_label.config(fg=theme["muted"])
        return

    direction, rate = trend
    if direction == "rising":
        trend_var.set(f"↗ {rate:+.1f} 人 / 10 min")
        trend_label.config(fg=theme["trend_up"])
    elif direction == "falling":
        trend_var.set(f"↘ {rate:+.1f} 人 / 10 min")
        trend_label.config(fg=theme["trend_down"])
    else:
        trend_var.set(f"→ {rate:+.1f} 人 / 10 min · 持平")
        trend_label.config(fg=theme["muted"])


def draw_occupancy_meter():
    """Draw a compact occupancy scale with an explicit comfort threshold."""

    if "occupancy_canvas" not in globals():
        return
    theme = state.get("theme") or get_theme(state.get("count"))
    occupancy_canvas.delete("all")
    width = max(occupancy_canvas.winfo_width(), 220)
    left, right, y = 6, width - 6, 8
    display_max = 60
    threshold_x = left + COMFORT_THRESHOLD / display_max * (right - left)

    occupancy_canvas.create_line(
        left,
        y,
        right,
        y,
        fill=theme["track"],
        width=8,
        capstyle=tk.ROUND,
    )
    count = state.get("count")
    if count is not None:
        value_x = left + min(count, display_max) / display_max * (right - left)
        occupancy_canvas.create_line(
            left,
            y,
            max(left + 2, value_x),
            y,
            fill=theme["accent"],
            width=8,
            capstyle=tk.ROUND,
        )
        occupancy_canvas.create_oval(
            value_x - 4,
            y - 4,
            value_x + 4,
            y + 4,
            fill=theme["accent"],
            outline=theme["card"],
            width=2,
        )
    occupancy_canvas.create_line(
        threshold_x,
        y - 7,
        threshold_x,
        y + 8,
        fill=theme["threshold"],
        width=1,
    )
    occupancy_canvas.create_text(
        threshold_x,
        24,
        text="30",
        fill=theme["muted"],
        font=("Segoe UI", 9),
    )


def build_chart_area_coordinates(coordinates, bottom):
    """Close a chart area beneath the first and last observed x positions."""

    if len(coordinates) < 4:
        return []
    return [
        coordinates[0],
        bottom,
        *coordinates,
        coordinates[-2],
        bottom,
    ]


def split_chart_segments(points, maximum_gap_minutes=5):
    """Split chart samples so lines and shadows never bridge missing data."""

    if not points:
        return []
    ordered = sorted(points, key=lambda point: point[0])
    segments = [[ordered[0]]]
    maximum_gap_seconds = maximum_gap_minutes * 60
    for point in ordered[1:]:
        gap_seconds = (point[0] - segments[-1][-1][0]).total_seconds()
        if gap_seconds > maximum_gap_seconds:
            segments.append([point])
        else:
            segments[-1].append(point)
    return segments


def chart_time_labels(left, right, last_x, latest_timestamp, minimum_spacing=48):
    """Build x-axis labels while giving the latest observation priority."""

    if last_x < left + 28:
        latest_anchor = "w"
    elif last_x > right - 28:
        latest_anchor = "e"
    else:
        latest_anchor = "center"

    labels = [(last_x, latest_timestamp.strftime("%H:%M"), latest_anchor, True)]
    if last_x - left >= minimum_spacing:
        labels.append((left, "09:00", "w", False))
    if right - last_x >= minimum_spacing:
        labels.append((right, "20:50", "e", False))
    return labels


def draw_chart():
    if not state["chart_visible"]:
        return

    theme = state.get("theme") or get_theme(state.get("count"))
    chart_canvas.delete("all")
    width = max(chart_canvas.winfo_width(), 320)
    height = max(chart_canvas.winfo_height(), 145)
    left, right, top_y, bottom = 32, width - 10, 10, height - 24
    points = sorted(state["today_points"], key=lambda point: point[0])

    if not points:
        chart_canvas.create_text(
            width / 2,
            height / 2,
            text="今天尚無營業時間內的資料",
            fill=theme["muted"],
            font=("Segoe UI", 9),
        )
        return

    max_count = max(count for _, count in points)
    y_max = max(40, int(math.ceil(max_count / 10)) * 10)
    open_minute = OPEN_TIME.hour * 60 + OPEN_TIME.minute
    close_minute = CLOSE_TIME.hour * 60 + CLOSE_TIME.minute

    def to_xy(point):
        timestamp, count = point
        minute = timestamp.hour * 60 + timestamp.minute + timestamp.second / 60
        x = left + (minute - open_minute) / (close_minute - open_minute) * (right - left)
        y = bottom - count / y_max * (bottom - top_y)
        return x, y

    for value in sorted({0, COMFORT_THRESHOLD, y_max}):
        grid_y = bottom - value / y_max * (bottom - top_y)
        chart_canvas.create_line(
            left,
            grid_y,
            right,
            grid_y,
            fill=theme["line"],
            width=1,
        )
        chart_canvas.create_text(
            left - 6,
            grid_y,
            text=str(value),
            anchor="e",
            fill=theme["muted"],
            font=("Segoe UI", 9),
        )

    threshold_y = bottom - COMFORT_THRESHOLD / y_max * (bottom - top_y)
    chart_canvas.create_line(
        left,
        threshold_y,
        right,
        threshold_y,
        fill=theme["threshold"],
        dash=(4, 3),
    )

    for segment in split_chart_segments(points):
        coordinates = [
            coordinate for point in segment for coordinate in to_xy(point)
        ]
        if len(coordinates) < 4:
            continue
        area_coordinates = build_chart_area_coordinates(coordinates, bottom)
        chart_canvas.create_polygon(
            *area_coordinates,
            fill=theme["series_soft"],
            outline="",
            tags=("area",),
        )
        chart_canvas.tag_lower("area")
        chart_canvas.create_line(
            *coordinates,
            fill=theme["series"],
            width=2,
        )
    last_x, last_y = to_xy(points[-1])
    chart_canvas.create_line(
        last_x,
        last_y + 5,
        last_x,
        bottom,
        fill=theme["line"],
        dash=(2, 3),
    )
    chart_canvas.create_oval(
        last_x - 3,
        last_y - 3,
        last_x + 3,
        last_y + 3,
        fill=theme["accent"],
        outline=theme["card"],
        width=2,
    )

    for label_x, text, anchor, is_latest in chart_time_labels(
        left,
        right,
        last_x,
        points[-1][0],
    ):
        chart_canvas.create_text(
            label_x,
            bottom + 14,
            text=text,
            anchor=anchor,
            fill=theme["series"] if is_latest else theme["muted"],
            font=("Segoe UI", 9, "bold" if is_latest else "normal"),
        )


def layout_visibility(width, height):
    """Return the information layers that fit at a given window size."""

    compact = width < COMPACT_BREAKPOINT[0] or height < COMPACT_BREAKPOINT[1]
    return {
        "compact": compact,
        "chart": not compact and width >= CHART_MIN_SIZE[0] and height >= CHART_MIN_SIZE[1],
        "gif": not compact and width >= 380 and height >= 220,
        "meter": not compact and width >= 270 and height >= 205,
    }


def update_responsive_layout(e=None):
    """Reveal information progressively without shrinking essential text."""

    if e is not None and e.widget is not root:
        return

    width = root.winfo_width()
    height = root.winfo_height()
    visibility = layout_visibility(width, height)
    compact = visibility["compact"]
    show_chart = visibility["chart"]
    show_gif = visibility["gif"]
    show_meter = visibility["meter"]

    if compact:
        full_body.pack_forget()
        if not compact_body.winfo_manager():
            compact_body.pack(fill="both", expand=True, padx=14, pady=14)
        compact_count_label.config(
            font=("Segoe UI", max(32, min(46, height // 2)), "bold")
        )
    else:
        compact_body.pack_forget()
        if not full_body.winfo_manager():
            full_body.pack(fill="both", expand=True, padx=14, pady=14)

        if show_gif and not gif_label.winfo_manager():
            gif_label.pack(side="right", padx=(16, 0), after=metrics)
        elif not show_gif:
            gif_label.pack_forget()

        if show_meter and not meter_section.winfo_manager():
            meter_section.pack(fill="x", padx=16, pady=(0, 4), after=content)
        elif not show_meter:
            meter_section.pack_forget()

        if show_chart and not chart_section.winfo_manager():
            chart_section.pack(
                fill="both",
                expand=True,
                padx=16,
                pady=(4, 12),
                after=meter_section if meter_section.winfo_manager() else trend_label,
            )
        elif not show_chart:
            chart_section.pack_forget()

    state["chart_visible"] = show_chart
    if show_meter:
        draw_occupancy_meter()
    if show_chart:
        draw_chart()


def get_autostart_command():
    """Return the Windows per-user startup command for this widget."""

    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'

    python_executable = Path(sys.executable).resolve()
    pythonw = python_executable.with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = python_executable
    launcher = Path(__file__).resolve().with_name("gym.pyw")
    return f'"{pythonw}" "{launcher}"'


def open_dashboard():
    if getattr(sys, "frozen", False):
        messagebox.showinfo(
            "NCU Gym Monitor",
            "封裝版本尚未包含歷史分析程式。",
        )
        return

    python_executable = Path(sys.executable).resolve()
    pythonw = python_executable.with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = python_executable
    dashboard = Path(__file__).resolve().with_name("gym_dashboard.py")
    subprocess.Popen([str(pythonw), str(dashboard)], cwd=BASE_DIR)


def is_autostart_enabled():
    if os.name != "nt":
        return False

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return value == get_autostart_command()
    except OSError:
        return False


def set_autostart(enabled):
    if os.name != "nt":
        raise OSError("開機自啟目前只支援 Windows")

    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                AUTOSTART_VALUE_NAME,
                0,
                winreg.REG_SZ,
                get_autostart_command(),
            )
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
            except FileNotFoundError:
                pass


def toggle_autostart():
    try:
        set_autostart(bool(autostart_var.get()))
    except OSError as exc:
        autostart_var.set(False)
        messagebox.showerror("無法更新開機自啟", str(exc))


def show_context_menu(e):
    autostart_var.set(is_autostart_enabled())
    try:
        context_menu.tk_popup(e.x_root, e.y_root)
    finally:
        context_menu.grab_release()


# ===== Window behavior =====
def _is_window_control(widget):
    return widget in (theme_picker_canvas, minimize_btn, close_btn)


def highlight_window_control(e):
    theme = state.get("theme") or get_theme(state.get("count"))
    e.widget.config(bg=theme["hover"])


def reset_window_control(e):
    theme = state.get("theme") or get_theme(state.get("count"))
    e.widget.config(bg=theme["card"])


def _local_pointer(e):
    return e.x_root - root.winfo_rootx(), e.y_root - root.winfo_rooty()


def hover_pointer(e):
    if _is_window_control(e.widget):
        return
    window_behavior.hover_pointer(*_local_pointer(e))


def begin_pointer(e):
    if _is_window_control(e.widget):
        return
    local_x, local_y = _local_pointer(e)
    window_behavior.begin_pointer(e.x_root, e.y_root, local_x, local_y)


def drag_pointer(e):
    if _is_window_control(e.widget):
        return
    window_behavior.drag_pointer(e.x_root, e.y_root)


def end_pointer(e):
    if _is_window_control(e.widget):
        return
    window_behavior.end_pointer()


def show_in_taskbar():
    if sys.platform != "win32":
        return
    try:
        root.update_idletasks()
        user32 = ctypes.windll.user32
        widget_handle = root.winfo_id()
        window_handle = user32.GetParent(widget_handle) or widget_handle
        extended_style = user32.GetWindowLongW(window_handle, -20)
        extended_style = (extended_style & ~0x00000080) | 0x00040000
        user32.SetWindowLongW(window_handle, -20, extended_style)
        user32.SetWindowPos(
            window_handle,
            0,
            0,
            0,
            0,
            0,
            0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020,
        )
    except (AttributeError, OSError, tk.TclError):
        pass


def minimize_app(e=None):
    state["minimized"] = True
    root.overrideredirect(False)
    root.iconify()
    return "break"


def restore_from_taskbar(e):
    if e.widget is not root or not state["minimized"] or root.state() != "normal":
        return
    state["minimized"] = False
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.after_idle(show_in_taskbar)


def close_app(e=None):
    executor.shutdown(wait=False, cancel_futures=True)
    root.destroy()
    return "break"


# ===== UI =====
def main():
    global root, outer, card, full_body, compact_body, compact_count_row
    global compact_dot, compact_count_label, compact_unit_label
    global ornament_top, ornament_bottom, ornament_left, ornament_right
    global top, title, status_badge, theme_picker_canvas
    global minimize_btn, close_btn, content
    global gif_label, metrics, eyebrow_label, count_row, count_var, count_label
    global unit_label, trend_var, trend_label, meter_section, meter_header
    global meter_label, meter_value_label, occupancy_canvas, chart_section
    global chart_header, chart_title, chart_canvas, resize_grip
    global autostart_var, context_menu
    global executor, window_behavior

    monitor_instance = MonitorInstance.try_acquire()
    if monitor_instance is None:
        return

    state["theme_key"] = load_theme_preference()
    enable_per_monitor_dpi_awareness()
    root = tk.Tk()
    root.title("NCU Gym Monitor")
    root.overrideredirect(os.environ.get("GYM_WINDOWED_DEBUG") != "1")
    root.attributes("-topmost", True)
    root.minsize(MIN_WIDTH, MIN_HEIGHT)

    outer = tk.Frame(root)
    outer.pack(fill="both", expand=True, padx=8, pady=8)

    card = tk.Frame(outer, highlightthickness=1)
    card.pack(fill="both", expand=True)

    ornament_top = tk.Canvas(card, height=14, highlightthickness=0)
    ornament_bottom = tk.Canvas(card, height=14, highlightthickness=0)
    ornament_left = tk.Canvas(card, width=14, highlightthickness=0)
    ornament_right = tk.Canvas(card, width=14, highlightthickness=0)
    ornament_top.place(x=14, y=0, relwidth=1.0, width=-28, height=14)
    ornament_bottom.place(
        x=14,
        rely=1.0,
        y=-14,
        relwidth=1.0,
        width=-28,
        height=14,
    )
    ornament_left.place(x=0, y=14, width=14, relheight=1.0, height=-28)
    ornament_right.place(
        relx=1.0,
        x=-14,
        y=14,
        width=14,
        relheight=1.0,
        height=-28,
    )

    compact_body = tk.Frame(card)
    compact_count_row = tk.Frame(compact_body)
    compact_count_row.pack(expand=True)
    compact_dot = tk.Label(
        compact_count_row,
        text="●",
        font=("Segoe UI", 10),
        padx=4,
    )
    compact_dot.pack(side="left", pady=(8, 0))

    count_var = tk.StringVar(value="—")
    compact_count_label = tk.Label(
        compact_count_row,
        textvariable=count_var,
        font=("Segoe UI", 42, "bold"),
    )
    compact_count_label.pack(side="left")
    compact_unit_label = tk.Label(
        compact_count_row,
        text="人",
        font=("Segoe UI", 12),
    )
    compact_unit_label.pack(side="left", anchor="s", pady=(0, 10))

    full_body = tk.Frame(card)
    full_body.pack(fill="both", expand=True, padx=14, pady=14)

    top = tk.Frame(full_body)
    top.pack(fill="x", padx=16, pady=(8, 0))

    title = tk.Label(
        top,
        text="NCU GYM",
        font=("Segoe UI", 11, "bold"),
    )
    title.pack(side="left")

    status_badge = tk.Label(
        top,
        text="●  讀取中",
        font=("Segoe UI", 9, "bold"),
        padx=8,
        pady=3,
    )
    status_badge.pack(side="left", padx=(10, 0))

    theme_picker_canvas = tk.Canvas(
        top,
        cursor="hand2",
        width=20 + (len(THEME_PALETTES) - 1) * 18,
        height=22,
        highlightthickness=0,
    )

    minimize_btn = tk.Label(
        top,
        text="—",
        cursor="hand2",
        font=("Segoe UI", 10, "bold"),
        padx=6,
        pady=2,
    )

    close_btn = tk.Label(
        top,
        text="×",
        cursor="hand2",
        font=("Segoe UI", 12),
        padx=4,
        pady=1,
    )
    close_btn.pack(side="right")
    minimize_btn.pack(side="right", padx=(0, 2))
    theme_picker_canvas.pack(side="right", padx=(0, 5))

    content = tk.Frame(full_body)
    content.pack(fill="x", padx=16, pady=(10, 6))

    metrics = tk.Frame(content)
    metrics.pack(side="left", fill="both", expand=True)

    eyebrow_label = tk.Label(
        metrics,
        text="目前人數",
        font=("Segoe UI", 10, "bold"),
        anchor="w",
    )
    eyebrow_label.pack(fill="x")

    count_row = tk.Frame(metrics)
    count_row.pack(fill="x")
    count_label = tk.Label(
        count_row,
        textvariable=count_var,
        font=("Segoe UI", 52, "bold"),
        anchor="w",
    )
    count_label.pack(side="left")
    unit_label = tk.Label(
        count_row,
        text="人",
        font=("Segoe UI", 13),
        anchor="w",
    )
    unit_label.pack(side="left", anchor="s", pady=(0, 10), padx=(4, 0))

    trend_var = tk.StringVar(value="趨勢資料累積中")
    trend_label = tk.Label(
        full_body,
        textvariable=trend_var,
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    )

    gif_label = tk.Label(content)
    gif_label.pack(side="right", padx=(16, 0))

    trend_label.pack(fill="x", padx=16, pady=(0, 7))

    meter_section = tk.Frame(full_body)
    meter_section.pack(fill="x", padx=16, pady=(0, 4))
    meter_header = tk.Frame(meter_section)
    meter_header.pack(fill="x")
    meter_label = tk.Label(
        meter_header,
        text="人數區間",
        font=("Segoe UI", 9),
        anchor="w",
    )
    meter_label.pack(side="left")
    meter_value_label = tk.Label(
        meter_header,
        text="舒適線 30 人",
        font=("Segoe UI", 9, "bold"),
        anchor="e",
    )
    meter_value_label.pack(side="right")
    occupancy_canvas = tk.Canvas(
        meter_section,
        height=30,
        highlightthickness=0,
    )
    occupancy_canvas.pack(fill="x")

    chart_section = tk.Frame(full_body)
    chart_header = tk.Frame(chart_section)
    chart_header.pack(fill="x", pady=(0, 6))
    chart_title = tk.Label(
        chart_header,
        text="今日人數走勢",
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    )
    chart_title.pack(side="left")

    chart_canvas = tk.Canvas(
        chart_section,
        width=320,
        height=150,
        highlightthickness=0,
    )
    chart_canvas.pack(fill="both", expand=True)

    minimize_btn.bind("<Button-1>", minimize_app)
    close_btn.bind("<Button-1>", close_app)
    for ornament in (
        ornament_top,
        ornament_bottom,
        ornament_left,
        ornament_right,
    ):
        ornament.bind("<Configure>", lambda _event: draw_ornament())
    for control in (minimize_btn, close_btn):
        control.bind("<Enter>", highlight_window_control)
        control.bind("<Leave>", reset_window_control)
    root.bind("<Escape>", close_app)
    root.bind("<Configure>", update_responsive_layout)
    root.bind("<Button-3>", show_context_menu)
    root.bind("<Motion>", hover_pointer)
    root.bind("<Button-1>", begin_pointer)
    root.bind("<B1-Motion>", drag_pointer)
    root.bind("<ButtonRelease-1>", end_pointer)
    root.bind("<Map>", restore_from_taskbar)
    root.protocol("WM_DELETE_WINDOW", close_app)

    resize_grip = tk.Label(
        root,
        text="◢",
        cursor="size_nw_se",
        font=("Segoe UI", 10),
    )
    resize_grip.place(relx=1.0, rely=1.0, anchor="se")

    autostart_var = tk.BooleanVar(value=is_autostart_enabled())
    context_menu = tk.Menu(root, tearoff=0)
    context_menu.add_command(label="開啟歷史分析", command=open_dashboard)
    context_menu.add_separator()
    context_menu.add_checkbutton(
        label="開機時自動啟動",
        variable=autostart_var,
        command=toggle_autostart,
    )
    context_menu.add_separator()
    context_menu.add_command(label="結束", command=close_app)

    window_behavior = WidgetWindowBehavior(
        TkWindowPort(root),
        JsonWindowState(window_state_path()),
        connected_screen_areas(root),
    )
    root.update_idletasks()
    window_behavior.start()

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gym-fetch")
    init_log_dir()
    load_today_points()
    load_all_gifs()
    apply_theme(None)
    update_trend_display()
    root.after_idle(update_responsive_layout)
    root.after_idle(show_in_taskbar)
    animate_gif()
    refresh_data()
    try:
        root.mainloop()
    finally:
        monitor_instance.release()


if __name__ == "__main__":
    main()
