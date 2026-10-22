"""Move, resize, multi-monitor, and persisted window behavior."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Protocol, Sequence


MIN_WIDTH = 150
MIN_HEIGHT = 84
RESIZE_BORDER = 7


@dataclass(frozen=True)
class Geometry:
    width: int
    height: int
    x: int
    y: int


DEFAULT_GEOMETRY = Geometry(420, 310, 100, 100)


class ResizeEdge(Enum):
    NORTH = auto()
    EAST = auto()
    SOUTH = auto()
    WEST = auto()


@dataclass(frozen=True)
class ScreenArea:
    x: int
    y: int
    width: int
    height: int

    def intersects(self, geometry: Geometry) -> bool:
        return (
            geometry.x < self.x + self.width
            and geometry.x + geometry.width > self.x
            and geometry.y < self.y + self.height
            and geometry.y + geometry.height > self.y
        )


class WindowPort(Protocol):
    def geometry(self) -> Geometry: ...
    def set_geometry(self, geometry: Geometry) -> None: ...
    def set_cursor(self, cursor: str) -> None: ...


class WindowState(Protocol):
    def load(self) -> Geometry | None: ...
    def save(self, geometry: Geometry) -> None: ...


class JsonWindowState:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Geometry | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            values = (data["width"], data["height"], data["x"], data["y"])
            if any(type(value) is not int for value in values):
                return None
            return Geometry(*values)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, geometry: Geometry) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "width": geometry.width,
                    "height": geometry.height,
                    "x": geometry.x,
                    "y": geometry.y,
                }
            ),
            encoding="utf-8",
        )
        temporary.replace(self._path)


def window_state_path() -> Path:
    local_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
    return base / "NCUGymMonitor" / "window-state.json"


def connected_screen_areas(root) -> list[ScreenArea]:
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

    def collect(monitor, _dc, _rect, _data):
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
        ctypes.windll.user32.EnumDisplayMonitors(0, 0, callback_type(collect), 0)
    except (AttributeError, OSError):
        return []
    return areas


def enable_per_monitor_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except (AttributeError, OSError):
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


class WidgetWindowBehavior:
    def __init__(
        self,
        window: WindowPort,
        state: WindowState,
        screens: Sequence[ScreenArea],
    ) -> None:
        self._window = window
        self._state = state
        self._screens = tuple(screens)
        self._pointer_origin = (0, 0)
        self._geometry_origin = DEFAULT_GEOMETRY
        self._resize_edges: frozenset[ResizeEdge] = frozenset()

    def start(self) -> None:
        self._apply_geometry(self._load_geometry())

    def begin_pointer(self, screen_x: int, screen_y: int, local_x: int, local_y: int) -> None:
        self._pointer_origin = (screen_x, screen_y)
        self._geometry_origin = self._window.geometry()
        self._resize_edges = self._edges_at(local_x, local_y, self._geometry_origin)

    def hover_pointer(self, local_x: int, local_y: int) -> None:
        edges = self._edges_at(local_x, local_y, self._window.geometry())
        cursors = {
            frozenset((ResizeEdge.WEST,)): "size_we",
            frozenset((ResizeEdge.EAST,)): "size_we",
            frozenset((ResizeEdge.NORTH,)): "size_ns",
            frozenset((ResizeEdge.SOUTH,)): "size_ns",
            frozenset((ResizeEdge.NORTH, ResizeEdge.WEST)): "size_nw_se",
            frozenset((ResizeEdge.SOUTH, ResizeEdge.EAST)): "size_nw_se",
            frozenset((ResizeEdge.NORTH, ResizeEdge.EAST)): "size_ne_sw",
            frozenset((ResizeEdge.SOUTH, ResizeEdge.WEST)): "size_ne_sw",
        }
        self._window.set_cursor(cursors.get(edges, "arrow"))

    def drag_pointer(self, screen_x: int, screen_y: int) -> None:
        delta_x = screen_x - self._pointer_origin[0]
        delta_y = screen_y - self._pointer_origin[1]
        origin = self._geometry_origin
        if self._resize_edges:
            self._apply_geometry(self._resized_geometry(origin, delta_x, delta_y))
        else:
            self._apply_geometry(
                Geometry(
                    origin.width,
                    origin.height,
                    origin.x + delta_x,
                    origin.y + delta_y,
                )
            )

    def end_pointer(self) -> None:
        try:
            self._state.save(self._window.geometry())
        except OSError:
            pass

    def _load_geometry(self) -> Geometry:
        geometry = self._state.load()
        if geometry is None or not self._is_usable(geometry):
            return DEFAULT_GEOMETRY
        return geometry

    def _is_usable(self, geometry: Geometry) -> bool:
        if geometry.width < MIN_WIDTH or geometry.height < MIN_HEIGHT:
            return False
        return any(screen.intersects(geometry) for screen in self._screens)

    def _apply_geometry(self, geometry: Geometry) -> None:
        self._window.set_geometry(geometry)

    def _edges_at(self, local_x: int, local_y: int, geometry: Geometry) -> frozenset[ResizeEdge]:
        edges: set[ResizeEdge] = set()
        if local_x < RESIZE_BORDER:
            edges.add(ResizeEdge.WEST)
        elif local_x >= geometry.width - RESIZE_BORDER:
            edges.add(ResizeEdge.EAST)
        if local_y < RESIZE_BORDER:
            edges.add(ResizeEdge.NORTH)
        elif local_y >= geometry.height - RESIZE_BORDER:
            edges.add(ResizeEdge.SOUTH)
        return frozenset(edges)

    def _resized_geometry(self, origin: Geometry, delta_x: int, delta_y: int) -> Geometry:
        width, height, x, y = origin.width, origin.height, origin.x, origin.y
        if ResizeEdge.WEST in self._resize_edges:
            width = max(MIN_WIDTH, origin.width - delta_x)
            x = origin.x + origin.width - width
        elif ResizeEdge.EAST in self._resize_edges:
            width = max(MIN_WIDTH, origin.width + delta_x)
        if ResizeEdge.NORTH in self._resize_edges:
            height = max(MIN_HEIGHT, origin.height - delta_y)
            y = origin.y + origin.height - height
        elif ResizeEdge.SOUTH in self._resize_edges:
            height = max(MIN_HEIGHT, origin.height + delta_y)
        return Geometry(width, height, x, y)
