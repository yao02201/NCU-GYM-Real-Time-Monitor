from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from widget_window import (
    Geometry,
    JsonWindowState,
    ScreenArea,
    WidgetWindowBehavior,
)


class RecordingWindow:
    def __init__(self, geometry: Geometry) -> None:
        self.current_geometry = geometry
        self.events: list[object] = []

    def geometry(self) -> Geometry:
        return self.current_geometry

    def set_geometry(self, geometry: Geometry) -> None:
        self.current_geometry = geometry
        self.events.append(("geometry", geometry))

    def set_cursor(self, cursor: str) -> None:
        self.events.append(("cursor", cursor))

    def minimize(self) -> None:
        self.events.append("minimize")

    def set_topmost(self, enabled: bool) -> None:
        self.events.append(("topmost", enabled))


class MemoryWindowState:
    def __init__(self, geometry: Geometry | None = None) -> None:
        self.geometry = geometry
        self.saved: list[Geometry] = []

    def load(self) -> Geometry | None:
        return self.geometry

    def save(self, geometry: Geometry) -> None:
        self.geometry = geometry
        self.saved.append(geometry)


class FailingWindowState:
    def load(self) -> Geometry | None:
        raise OSError("settings are unavailable")

    def save(self, geometry: Geometry) -> None:
        raise OSError("settings are unavailable")


class WidgetWindowBehaviorTests(unittest.TestCase):
    def test_unusable_saved_geometry_falls_back_to_safe_default(self) -> None:
        unusable = [
            None,
            Geometry(239, 165, 100, 100),
            Geometry(340, 119, 100, 100),
            Geometry(340, 165, 3000, 3000),
            Geometry(240, 120, 500, 200),
        ]
        separated_screens = [
            ScreenArea(0, 0, 400, 1080),
            ScreenArea(800, 0, 400, 1080),
        ]

        for saved in unusable:
            with self.subTest(saved=saved):
                window = RecordingWindow(Geometry(500, 300, 400, 400))
                WidgetWindowBehavior(
                    window,
                    MemoryWindowState(saved),
                    separated_screens,
                ).start()

                self.assertEqual(window.current_geometry, Geometry(340, 165, 100, 100))

    def test_settings_failure_does_not_block_window_use(self) -> None:
        window = RecordingWindow(Geometry(340, 165, 100, 100))
        behavior = WidgetWindowBehavior(
            window,
            FailingWindowState(),
            [ScreenArea(0, 0, 1920, 1080)],
        )

        behavior.start()
        behavior.begin_pointer(120, 120, 20, 20)
        behavior.drag_pointer(220, 220)
        behavior.end_pointer()

        self.assertEqual(window.current_geometry, Geometry(340, 165, 200, 200))

    def test_minimize_and_restore_preserve_normal_geometry_without_forcing_focus(self) -> None:
        state = MemoryWindowState(Geometry(420, 180, 300, 200))
        window = RecordingWindow(Geometry(340, 165, 100, 100))
        behavior = WidgetWindowBehavior(
            window,
            state,
            [ScreenArea(0, 0, 1920, 1080)],
        )
        behavior.start()
        window.events.clear()

        behavior.minimize()
        behavior.restore()

        self.assertEqual(window.events, ["minimize", ("topmost", True)])
        self.assertEqual(state.saved, [])
        self.assertEqual(window.current_geometry, Geometry(420, 180, 300, 200))

    def test_crossing_responsive_breakpoint_reports_compact_layout(self) -> None:
        compact_changes: list[bool] = []
        window = RecordingWindow(Geometry(340, 165, 100, 100))
        behavior = WidgetWindowBehavior(
            window,
            MemoryWindowState(),
            [ScreenArea(0, 0, 1920, 1080)],
            on_compact_changed=compact_changes.append,
        )
        behavior.start()

        behavior.begin_pointer(439, 180, 339, 80)
        behavior.drag_pointer(389, 180)
        behavior.end_pointer()
        behavior.begin_pointer(389, 180, 289, 80)
        behavior.drag_pointer(409, 180)
        behavior.end_pointer()

        self.assertEqual(compact_changes, [False, True, False])

    def test_resize_zones_show_directional_cursors_and_enforce_minimum_size(self) -> None:
        window = RecordingWindow(Geometry(340, 165, 100, 100))
        behavior = WidgetWindowBehavior(
            window,
            MemoryWindowState(),
            [ScreenArea(0, 0, 1920, 1080)],
        )
        behavior.start()

        cursor_cases = [
            ((0, 80), "size_we"),
            ((339, 80), "size_we"),
            ((170, 0), "size_ns"),
            ((170, 164), "size_ns"),
            ((0, 0), "size_nw_se"),
            ((339, 0), "size_ne_sw"),
            ((0, 164), "size_ne_sw"),
            ((339, 164), "size_nw_se"),
            ((170, 80), "arrow"),
        ]
        for pointer, expected_cursor in cursor_cases:
            behavior.hover_pointer(*pointer)
            self.assertEqual(window.events[-1], ("cursor", expected_cursor))

        behavior.begin_pointer(200, 200, 0, 0)
        behavior.drag_pointer(1000, 1000)

        self.assertEqual(window.current_geometry, Geometry(240, 120, 200, 145))

    def test_user_can_resize_from_every_edge_and_corner(self) -> None:
        cases = [
            ((0, 80), Geometry(320, 165, 120, 100)),
            ((339, 80), Geometry(360, 165, 100, 100)),
            ((170, 0), Geometry(340, 155, 100, 110)),
            ((170, 164), Geometry(340, 175, 100, 100)),
            ((0, 0), Geometry(320, 155, 120, 110)),
            ((339, 0), Geometry(360, 155, 100, 110)),
            ((0, 164), Geometry(320, 175, 120, 100)),
            ((339, 164), Geometry(360, 175, 100, 100)),
        ]

        for local_pointer, expected in cases:
            with self.subTest(local_pointer=local_pointer):
                window = RecordingWindow(Geometry(340, 165, 100, 100))
                behavior = WidgetWindowBehavior(
                    window,
                    MemoryWindowState(),
                    [ScreenArea(0, 0, 1920, 1080)],
                )
                behavior.start()

                behavior.begin_pointer(200, 200, *local_pointer)
                behavior.drag_pointer(220, 210)
                behavior.end_pointer()

                self.assertEqual(window.current_geometry, expected)

    def test_saved_geometry_survives_a_new_state_store_instance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "window-state.json"
            JsonWindowState(path).save(Geometry(480, 220, -300, 40))

            loaded = JsonWindowState(path).load()

        self.assertEqual(loaded, Geometry(480, 220, -300, 40))

    def test_user_move_is_saved_and_restored_on_next_launch(self) -> None:
        state = MemoryWindowState()
        first_window = RecordingWindow(Geometry(340, 165, 100, 100))
        behavior = WidgetWindowBehavior(
            first_window,
            state,
            [ScreenArea(0, 0, 1920, 1080)],
        )

        behavior.start()
        behavior.begin_pointer(120, 120, 20, 20)
        behavior.drag_pointer(320, 270)
        behavior.end_pointer()

        moved = Geometry(340, 165, 300, 250)
        self.assertEqual(first_window.current_geometry, moved)
        self.assertEqual(state.saved, [moved])

        restored_window = RecordingWindow(Geometry(340, 165, 100, 100))
        restored = WidgetWindowBehavior(
            restored_window,
            state,
            [ScreenArea(0, 0, 1920, 1080)],
        )
        restored.start()

        self.assertEqual(restored_window.current_geometry, moved)


if __name__ == "__main__":
    unittest.main()
