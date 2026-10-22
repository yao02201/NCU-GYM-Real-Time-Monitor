import tempfile
import unittest
from pathlib import Path

from widget_window import (
    DEFAULT_GEOMETRY,
    Geometry,
    JsonWindowState,
    ScreenArea,
    WidgetWindowBehavior,
)


class FakeWindow:
    def __init__(self, geometry=DEFAULT_GEOMETRY):
        self.current = geometry
        self.cursor = "arrow"

    def geometry(self):
        return self.current

    def set_geometry(self, geometry):
        self.current = geometry

    def set_cursor(self, cursor):
        self.cursor = cursor


class MemoryState:
    def __init__(self, geometry=None):
        self.geometry = geometry

    def load(self):
        return self.geometry

    def save(self, geometry):
        self.geometry = geometry


class WidgetWindowTests(unittest.TestCase):
    def test_move_preserves_negative_monitor_coordinates(self):
        window = FakeWindow(Geometry(320, 195, 100, 100))
        state = MemoryState(window.current)
        behavior = WidgetWindowBehavior(
            window,
            state,
            [ScreenArea(-1920, 0, 1920, 1080), ScreenArea(0, 0, 1920, 1080)],
        )
        behavior.start()
        behavior.begin_pointer(200, 200, 100, 100)
        behavior.drag_pointer(-300, 160)
        behavior.end_pointer()
        self.assertEqual(window.current.x, -400)
        self.assertEqual(window.current.y, 60)
        self.assertEqual(state.geometry, window.current)

    def test_resize_from_northwest_keeps_opposite_corner(self):
        window = FakeWindow(Geometry(320, 195, 100, 100))
        behavior = WidgetWindowBehavior(window, MemoryState(window.current), [ScreenArea(0, 0, 1920, 1080)])
        behavior.start()
        behavior.begin_pointer(100, 100, 0, 0)
        behavior.drag_pointer(140, 130)
        self.assertEqual(window.current, Geometry(280, 165, 140, 130))

    def test_offscreen_saved_geometry_falls_back_to_default(self):
        window = FakeWindow()
        behavior = WidgetWindowBehavior(
            window,
            MemoryState(Geometry(320, 195, 5000, 5000)),
            [ScreenArea(0, 0, 1920, 1080)],
        )
        behavior.start()
        self.assertEqual(window.current, DEFAULT_GEOMETRY)

    def test_json_state_round_trip(self):
        # Keep the test inside the writable project workspace.  Some Windows
        # sandbox profiles expose %TEMP% as readable but not writable.
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "window.json"
            state = JsonWindowState(path)
            expected = Geometry(400, 350, -250, 75)
            state.save(expected)
            self.assertEqual(state.load(), expected)


if __name__ == "__main__":
    unittest.main()
