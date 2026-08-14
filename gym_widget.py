"""Tk adapter for the NCU Gym Monitor Widget."""

from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
from PIL import Image, ImageSequence, ImageTk

from occupancy_monitor import (
    CsvOccupancyLogger,
    GifKey,
    NcuOccupancySource,
    OccupancyMonitor,
    SourceOfflineError,
    WidgetPresentation,
    WidgetTheme,
)
from widget_window import (
    DEFAULT_GEOMETRY,
    MIN_HEIGHT,
    MIN_WIDTH,
    Geometry,
    JsonWindowState,
    ScreenArea,
    WidgetWindowBehavior,
)


BASE_DIR = Path(__file__).resolve().parent
GIF_DIR = BASE_DIR / "gif"
LOG_DIR = BASE_DIR / "gym_count"
ICON_PATH = BASE_DIR / "assets" / "ncu-gym-monitor.ico"
BLINK_MS = 450
GIF_SIZE = (110, 110)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_REFRESH_FRAME = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020
PER_MONITOR_AWARE_V2 = -4
PROCESS_PER_MONITOR_DPI_AWARE = 2

GIF_FILES = {
    GifKey.LOW: GIF_DIR / "gymtime.gif",
    GifKey.MID: GIF_DIR / "blueguy.gif",
    GifKey.HIGH: GIF_DIR / "usingcomputer.gif",
}


@dataclass(frozen=True)
class ThemePalette:
    background: str
    card_background: str
    foreground: str
    muted: str
    border: str


THEMES = {
    WidgetTheme.NEUTRAL: ThemePalette(
        "#f3f4f6", "#ffffff", "#111827", "#6b7280", "#d1d5db"
    ),
    WidgetTheme.OFFLINE: ThemePalette(
        "#e0f2fe", "#f0f9ff", "#0c4a6e", "#0369a1", "#7dd3fc"
    ),
    WidgetTheme.DATA_ERROR: ThemePalette(
        "#f3e8ff", "#faf5ff", "#581c87", "#7e22ce", "#c084fc"
    ),
    WidgetTheme.LOW: ThemePalette(
        "#dcfce7", "#bbf7d0", "#14532d", "#166534", "#16a34a"
    ),
    WidgetTheme.MEDIUM: ThemePalette(
        "#ffedd5", "#fed7aa", "#7c2d12", "#9a3412", "#f59e0b"
    ),
    WidgetTheme.HIGH: ThemePalette(
        "#fee2e2", "#fecaca", "#7f1d1d", "#991b1b", "#dc2626"
    ),
}


class RequestsResponse:
    def __init__(self, response: requests.Response) -> None:
        self._response = response

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def content(self) -> bytes:
        return self._response.content

    def raise_for_status(self) -> None:
        try:
            self._response.raise_for_status()
        except requests.RequestException as error:
            raise SourceOfflineError from error


class RequestsHttpClient:
    def get(self, url: str, **kwargs: object) -> RequestsResponse:
        try:
            return RequestsResponse(requests.get(url, **kwargs))
        except requests.RequestException as error:
            raise SourceOfflineError from error


class TkScheduler:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root

    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> None:
        if delay_ms == 0:
            self._root.after_idle(lambda: self._root.after(0, callback))
            return
        self._root.after(delay_ms, callback)


class TkWindowPort:
    """Map tested Widget window behavior onto Tk and Windows."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._geometry = DEFAULT_GEOMETRY
        self._minimized = False

    def geometry(self) -> Geometry:
        return self._geometry

    def set_geometry(self, geometry: Geometry) -> None:
        self._geometry = geometry
        self._root.geometry(
            f"{geometry.width}x{geometry.height}+{geometry.x}+{geometry.y}"
        )

    def set_cursor(self, cursor: str) -> None:
        self._root.configure(cursor=cursor)

    def minimize(self) -> None:
        self._minimized = True
        self._root.overrideredirect(False)
        self._root.iconify()

    def finish_restore(self) -> bool:
        if not self._minimized or self._root.state() != "normal":
            return False
        self._minimized = False
        self._root.overrideredirect(True)
        self._root.after_idle(self.show_in_taskbar)
        return True

    def set_topmost(self, enabled: bool) -> None:
        self._root.attributes("-topmost", enabled)

    def show_in_taskbar(self) -> None:
        if sys.platform != "win32":
            return
        try:
            self._root.update_idletasks()
            user32 = ctypes.windll.user32
            widget_handle = self._root.winfo_id()
            window_handle = user32.GetParent(widget_handle) or widget_handle
            extended_style = user32.GetWindowLongW(window_handle, GWL_EXSTYLE)
            extended_style = (
                extended_style & ~WS_EX_TOOLWINDOW
            ) | WS_EX_APPWINDOW
            user32.SetWindowLongW(window_handle, GWL_EXSTYLE, extended_style)
            user32.SetWindowPos(
                window_handle,
                0,
                0,
                0,
                0,
                0,
                SWP_REFRESH_FRAME,
            )
        except (AttributeError, OSError, tk.TclError):
            return


def window_state_path() -> Path:
    local_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
    return base / "NCUGymMonitor" / "window-state.json"


def connected_screen_areas(root: tk.Tk) -> list[ScreenArea]:
    if sys.platform == "win32":
        areas = _windows_screen_areas()
        if areas:
            return areas
    return [
        ScreenArea(
            root.winfo_vrootx(),
            root.winfo_vrooty(),
            root.winfo_vrootwidth(),
            root.winfo_vrootheight(),
        )
    ]


def _windows_screen_areas() -> list[ScreenArea]:
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("monitor", wintypes.RECT),
            ("work", wintypes.RECT),
            ("flags", wintypes.DWORD),
        ]

    areas: list[ScreenArea] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def collect(monitor: int, _dc: int, _rect: object, _data: int) -> bool:
        info = MonitorInfo()
        info.size = ctypes.sizeof(MonitorInfo)
        if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.work
            areas.append(
                ScreenArea(
                    rect.left,
                    rect.top,
                    rect.right - rect.left,
                    rect.bottom - rect.top,
                )
            )
        return True

    try:
        ctypes.windll.user32.EnumDisplayMonitors(
            0,
            0,
            callback_type(collect),
            0,
        )
    except (AttributeError, OSError):
        return []
    return areas


def enable_per_monitor_dpi_awareness() -> None:
    """Keep pointer and window coordinates continuous across mixed-DPI screens."""
    if sys.platform != "win32":
        return

    try:
        set_awareness_context = (
            ctypes.windll.user32.SetProcessDpiAwarenessContext
        )
        set_awareness_context.argtypes = (ctypes.c_void_p,)
        set_awareness_context.restype = ctypes.c_bool
        if set_awareness_context(ctypes.c_void_p(PER_MONITOR_AWARE_V2)):
            return
    except (AttributeError, OSError):
        pass

    try:
        if (
            ctypes.windll.shcore.SetProcessDpiAwareness(
                PROCESS_PER_MONITOR_DPI_AWARE
            )
            == 0
        ):
            return
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        return


class TkWidgetView:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._presentation = WidgetPresentation(
            primary_text="Loading...",
            secondary_text=None,
            theme=WidgetTheme.NEUTRAL,
            gif_key=None,
            blink=False,
        )
        self._gif_sets: dict[
            GifKey, tuple[list[ImageTk.PhotoImage], list[int]]
        ] = {}
        self._gif_index = 0
        self._blink_on = True
        self._foreground = "#111827"
        self._card_background = "#ffffff"
        self._compact = False

        root.title("NCU Gym Monitor")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.minsize(MIN_WIDTH, MIN_HEIGHT)
        if ICON_PATH.exists():
            try:
                root.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass

        self._outer = tk.Frame(root)
        self._outer.pack(fill="both", expand=True, padx=8, pady=8)

        self._card = tk.Frame(self._outer, highlightthickness=1)
        self._card.pack(fill="both", expand=True)

        self._top = tk.Frame(self._card)
        self._top.pack(fill="x", padx=12, pady=(10, 0))

        self._title = tk.Label(
            self._top,
            text="NCU GYM Real-Time Monitor",
            font=("Segoe UI", 12, "bold"),
        )
        self._title.pack(side="left")

        self._minimize_button = tk.Label(
            self._top,
            text="—",
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
            padx=5,
        )

        self._close_button = tk.Label(
            self._top,
            text="✕",
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
        )
        self._close_button.pack(side="right")
        self._minimize_button.pack(side="right", padx=(0, 2))

        self._content = tk.Frame(self._card)
        self._content.pack(fill="both", expand=True, padx=14, pady=(8, 12))

        self._gif_label = tk.Label(self._content)
        self._text_panel = tk.Frame(self._content)
        self._text_panel.pack(side="left", fill="both", expand=True)

        self._primary_var = tk.StringVar(value="Loading...")
        self._primary_label = tk.Label(
            self._text_panel,
            textvariable=self._primary_var,
            anchor="w",
            font=("Segoe UI", 32, "bold"),
        )
        self._primary_label.pack(fill="x")

        self._secondary_var = tk.StringVar(value="")
        self._secondary_label = tk.Label(
            self._text_panel,
            textvariable=self._secondary_var,
            anchor="w",
            font=("Segoe UI", 9),
        )

        self._window = TkWindowPort(root)
        self._window_behavior = WidgetWindowBehavior(
            self._window,
            JsonWindowState(window_state_path()),
            connected_screen_areas(root),
            on_compact_changed=self._set_compact,
        )
        self._window_behavior.start()

        self._minimize_button.bind("<Button-1>", self.minimize)
        self._close_button.bind("<Button-1>", self.close)
        for control in (self._minimize_button, self._close_button):
            control.bind("<Enter>", self._control_enter)
            control.bind("<Leave>", self._control_leave)

        root.bind("<Motion>", self._hover_pointer)
        root.bind("<Button-1>", self._begin_pointer)
        root.bind("<B1-Motion>", self._drag_pointer)
        root.bind("<ButtonRelease-1>", self._end_pointer)
        root.bind("<Map>", self._restore_from_taskbar)
        root.bind("<Escape>", self.close)

        self._load_all_gifs()
        root.after_idle(self._window.show_in_taskbar)

    def render(self, presentation: WidgetPresentation) -> None:
        previous_gif = self._presentation.gif_key
        self._presentation = presentation
        self._blink_on = True

        if presentation.gif_key != previous_gif:
            self._gif_index = 0

        self._primary_var.set(presentation.primary_text)
        self._secondary_var.set(presentation.secondary_text or "")
        if presentation.secondary_text:
            self._secondary_label.pack(fill="x", pady=(0, 2))
        else:
            self._secondary_label.pack_forget()

        self._sync_gif_visibility()

        self._apply_theme(presentation.theme)

    def start_animation(self) -> None:
        self._animate_gif()
        self._blink()

    def minimize(self, event: object | None = None) -> str:
        self._window_behavior.minimize()
        return "break"

    def close(self, event: object | None = None) -> str:
        self._root.destroy()
        return "break"

    def _load_all_gifs(self) -> None:
        self._gif_sets = {
            key: self._load_gif(path) for key, path in GIF_FILES.items()
        }

    def _load_gif(self, path: Path) -> tuple[list[ImageTk.PhotoImage], list[int]]:
        if not path.exists():
            return [], []

        frames: list[ImageTk.PhotoImage] = []
        delays: list[int] = []
        try:
            with Image.open(path) as image:
                for source_frame in ImageSequence.Iterator(image):
                    delay = source_frame.info.get("duration", 100) or 100
                    frame = source_frame.convert("RGBA")
                    frame.thumbnail(GIF_SIZE)
                    frames.append(ImageTk.PhotoImage(frame))
                    delays.append(delay)
        except Exception:
            return [], []
        return frames, delays

    def _animate_gif(self) -> None:
        gif_key = self._presentation.gif_key
        if gif_key is None:
            self._root.after(300, self._animate_gif)
            return

        frames, delays = self._gif_sets.get(gif_key, ([], []))
        if not frames:
            self._root.after(300, self._animate_gif)
            return

        frame_index = self._gif_index % len(frames)
        self._gif_label.config(image=frames[frame_index])
        self._gif_index = (frame_index + 1) % len(frames)
        self._root.after(delays[frame_index], self._animate_gif)

    def _blink(self) -> None:
        if self._presentation.blink:
            self._blink_on = not self._blink_on
            foreground = self._foreground if self._blink_on else self._card_background
            self._primary_label.config(fg=foreground)
        else:
            self._primary_label.config(fg=self._foreground)
        self._root.after(BLINK_MS, self._blink)

    def _apply_theme(self, theme_name: WidgetTheme) -> None:
        palette = THEMES[theme_name]
        self._root.configure(bg=palette.background)
        self._outer.config(bg=palette.background)

        for widget in (
            self._card,
            self._top,
            self._content,
            self._gif_label,
            self._text_panel,
            self._primary_label,
            self._secondary_label,
        ):
            widget.config(bg=palette.card_background)

        self._card.config(
            highlightbackground=palette.border,
            highlightcolor=palette.border,
        )
        self._title.config(bg=palette.card_background, fg=palette.muted)
        self._minimize_button.config(
            bg=palette.card_background,
            fg=palette.muted,
        )
        self._close_button.config(bg=palette.card_background, fg=palette.muted)
        self._primary_label.config(
            bg=palette.card_background,
            fg=palette.foreground,
        )
        self._secondary_label.config(
            bg=palette.card_background,
            fg=palette.muted,
        )
        self._foreground = palette.foreground
        self._card_background = palette.card_background

    def _set_compact(self, compact: bool) -> None:
        self._compact = compact
        if hasattr(self, "_gif_label"):
            self._sync_gif_visibility()

    def _sync_gif_visibility(self) -> None:
        if self._presentation.gif_key is None:
            self._gif_label.config(image="")
            self._gif_label.pack_forget()
            return
        if self._compact:
            self._gif_label.pack_forget()
            return
        self._gif_label.pack(
            side="left",
            padx=(0, 12),
            before=self._text_panel,
        )

    def _is_control(self, widget: object) -> bool:
        return widget in (self._minimize_button, self._close_button)

    def _local_pointer(self, event: tk.Event) -> tuple[int, int]:
        return (
            event.x_root - self._root.winfo_rootx(),
            event.y_root - self._root.winfo_rooty(),
        )

    def _hover_pointer(self, event: tk.Event) -> None:
        if self._is_control(event.widget):
            return
        self._window_behavior.hover_pointer(*self._local_pointer(event))

    def _begin_pointer(self, event: tk.Event) -> None:
        if self._is_control(event.widget):
            return
        local_x, local_y = self._local_pointer(event)
        self._window_behavior.begin_pointer(
            event.x_root,
            event.y_root,
            local_x,
            local_y,
        )

    def _drag_pointer(self, event: tk.Event) -> None:
        if self._is_control(event.widget):
            return
        self._window_behavior.drag_pointer(event.x_root, event.y_root)

    def _end_pointer(self, event: tk.Event) -> None:
        if self._is_control(event.widget):
            return
        self._window_behavior.end_pointer()

    def _restore_from_taskbar(self, event: tk.Event) -> None:
        if event.widget is not self._root:
            return
        if self._window.finish_restore():
            self._window_behavior.restore()

    def _control_enter(self, event: tk.Event) -> None:
        palette = THEMES[self._presentation.theme]
        event.widget.config(bg=palette.border, fg=palette.foreground)

    def _control_leave(self, event: tk.Event) -> None:
        palette = THEMES[self._presentation.theme]
        event.widget.config(bg=palette.card_background, fg=palette.muted)


def main() -> None:
    enable_per_monitor_dpi_awareness()
    root = tk.Tk()
    view = TkWidgetView(root)
    monitor = OccupancyMonitor(
        source=NcuOccupancySource(http_client=RequestsHttpClient()),
        view=view,
        logger=CsvOccupancyLogger(LOG_DIR),
        scheduler=TkScheduler(root),
    )
    view.start_animation()
    monitor.start()
    root.mainloop()


if __name__ == "__main__":
    main()
