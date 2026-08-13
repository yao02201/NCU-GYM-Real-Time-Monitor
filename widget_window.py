"""User-visible window behavior for the NCU Gym Monitor Widget."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence


DEFAULT_GEOMETRY = None
MIN_WIDTH = 240
MIN_HEIGHT = 120
RESIZE_BORDER = 6


@dataclass(frozen=True)
class Geometry:
    width: int
    height: int
    x: int
    y: int


DEFAULT_GEOMETRY = Geometry(340, 165, 100, 100)


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

    def minimize(self) -> None: ...

    def set_topmost(self, enabled: bool) -> None: ...


class WindowState(Protocol):
    def load(self) -> Geometry | None: ...

    def save(self, geometry: Geometry) -> None: ...


class JsonWindowState:
    """Persist normal Widget geometry in a per-user JSON file."""

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
        self._path.write_text(
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


class WidgetWindowBehavior:
    """Coordinate move, resize, minimize, and persisted Widget state."""

    def __init__(
        self,
        window: WindowPort,
        state: WindowState,
        screens: Sequence[ScreenArea],
        on_compact_changed: Callable[[bool], None] | None = None,
    ) -> None:
        self._window = window
        self._state = state
        self._screens = tuple(screens)
        self._on_compact_changed = on_compact_changed or (lambda compact: None)
        self._is_compact: bool | None = None
        self._pointer_origin = (0, 0)
        self._geometry_origin = DEFAULT_GEOMETRY
        self._resize_edges: frozenset[str] = frozenset()

    def start(self) -> None:
        geometry = self._load_geometry()
        self._apply_geometry(geometry)

    def begin_pointer(
        self,
        screen_x: int,
        screen_y: int,
        local_x: int,
        local_y: int,
    ) -> None:
        self._pointer_origin = (screen_x, screen_y)
        self._geometry_origin = self._window.geometry()
        self._resize_edges = self._edges_at(
            local_x,
            local_y,
            self._geometry_origin,
        )

    def hover_pointer(self, local_x: int, local_y: int) -> None:
        edges = self._edges_at(local_x, local_y, self._window.geometry())
        cursors = {
            frozenset(("west",)): "size_we",
            frozenset(("east",)): "size_we",
            frozenset(("north",)): "size_ns",
            frozenset(("south",)): "size_ns",
            frozenset(("north", "west")): "size_nw_se",
            frozenset(("south", "east")): "size_nw_se",
            frozenset(("north", "east")): "size_ne_sw",
            frozenset(("south", "west")): "size_ne_sw",
        }
        self._window.set_cursor(cursors.get(edges, "arrow"))

    def drag_pointer(self, screen_x: int, screen_y: int) -> None:
        delta_x = screen_x - self._pointer_origin[0]
        delta_y = screen_y - self._pointer_origin[1]
        origin = self._geometry_origin
        if self._resize_edges:
            self._apply_geometry(self._resized_geometry(origin, delta_x, delta_y))
            return
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
        except Exception:
            return

    def minimize(self) -> None:
        self._window.minimize()

    def restore(self) -> None:
        self._window.set_topmost(True)

    def _load_geometry(self) -> Geometry:
        try:
            geometry = self._state.load()
        except Exception:
            return DEFAULT_GEOMETRY
        if geometry is None or not self._is_usable(geometry):
            return DEFAULT_GEOMETRY
        return geometry

    def _is_usable(self, geometry: Geometry) -> bool:
        if geometry.width < MIN_WIDTH or geometry.height < MIN_HEIGHT:
            return False
        return any(screen.intersects(geometry) for screen in self._screens)

    def _apply_geometry(self, geometry: Geometry) -> None:
        self._window.set_geometry(geometry)
        compact = geometry.width < 300
        if compact != self._is_compact:
            self._is_compact = compact
            self._on_compact_changed(compact)

    def _edges_at(
        self,
        local_x: int,
        local_y: int,
        geometry: Geometry,
    ) -> frozenset[str]:
        edges: set[str] = set()
        if local_x < RESIZE_BORDER:
            edges.add("west")
        elif local_x >= geometry.width - RESIZE_BORDER:
            edges.add("east")
        if local_y < RESIZE_BORDER:
            edges.add("north")
        elif local_y >= geometry.height - RESIZE_BORDER:
            edges.add("south")
        return frozenset(edges)

    def _resized_geometry(
        self,
        origin: Geometry,
        delta_x: int,
        delta_y: int,
    ) -> Geometry:
        width = origin.width
        height = origin.height
        x = origin.x
        y = origin.y

        if "west" in self._resize_edges:
            width = max(MIN_WIDTH, origin.width - delta_x)
            x = origin.x + origin.width - width
        elif "east" in self._resize_edges:
            width = max(MIN_WIDTH, origin.width + delta_x)

        if "north" in self._resize_edges:
            height = max(MIN_HEIGHT, origin.height - delta_y)
            y = origin.y + origin.height - height
        elif "south" in self._resize_edges:
            height = max(MIN_HEIGHT, origin.height + delta_y)

        return Geometry(width, height, x, y)
