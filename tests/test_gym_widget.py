import unittest
from datetime import datetime, timedelta

import gym
from widget_window import Geometry


class FakeTkWindow:
    def __init__(self):
        self.geometry_calls = []

    def winfo_width(self):
        return 380

    def winfo_height(self):
        return 270

    def winfo_x(self):
        return -500

    def winfo_y(self):
        return -120

    def geometry(self, value):
        self.geometry_calls.append(value)

    def configure(self, **_kwargs):
        pass


class GymWidgetTests(unittest.TestCase):
    def setUp(self):
        self.original_last_logged_at = gym.state["last_logged_at"]
        gym.state["last_logged_at"] = None

    def tearDown(self):
        gym.state["last_logged_at"] = self.original_last_logged_at

    def test_logging_only_during_opening_hours(self):
        self.assertFalse(gym.should_log_now(datetime(2026, 10, 22, 8, 59)))
        self.assertTrue(gym.should_log_now(datetime(2026, 10, 22, 9, 0)))
        self.assertFalse(gym.should_log_now(datetime(2026, 10, 22, 20, 50)))

    def test_logging_interval(self):
        start = datetime(2026, 10, 22, 10, 0)
        gym.state["last_logged_at"] = start
        self.assertFalse(gym.should_log_now(start + timedelta(seconds=59)))
        self.assertTrue(gym.should_log_now(start + timedelta(seconds=60)))

    def test_autostart_command_points_to_windowless_launcher(self):
        command = gym.get_autostart_command()
        self.assertIn("gym.pyw", command)
        self.assertTrue(command.startswith('"'))

    def test_responsive_layout_reveals_information_progressively(self):
        compact = gym.layout_visibility(180, 100)
        normal = gym.layout_visibility(420, 310)
        expanded = gym.layout_visibility(460, 480)

        self.assertTrue(compact["compact"])
        self.assertFalse(compact["chart"])
        self.assertTrue(normal["gif"])
        self.assertFalse(normal["chart"])
        self.assertTrue(expanded["chart"])

    def test_native_window_move_preserves_negative_monitor_coordinates(self):
        window = FakeTkWindow()
        moved = []
        target = Geometry(380, 270, -1200, -400)
        port = gym.TkWindowPort(
            window,
            native_setter=lambda selected_window, geometry: (
                moved.append((selected_window, geometry)) or True
            ),
        )

        port.set_geometry(target)

        self.assertEqual(moved, [(window, target)])
        self.assertEqual(window.geometry_calls, [])

    def test_tk_geometry_is_only_a_fallback(self):
        window = FakeTkWindow()
        port = gym.TkWindowPort(window, native_setter=lambda *_args: False)

        port.set_geometry(Geometry(380, 270, 100, 120))

        self.assertEqual(window.geometry_calls, ["380x270+100+120"])

    def test_all_theme_palettes_are_distinct_and_readable(self):
        original_theme = gym.state["theme_key"]
        try:
            cards = set()
            flowers = set()
            flower_layouts = set()
            for theme_key in gym.THEME_PALETTES:
                gym.state["theme_key"] = theme_key
                theme = gym.get_theme(24)
                cards.add(theme["card"])
                flowers.add(theme["flower"])
                flower_layouts.add(theme["flower_layout"])
                self.assertNotEqual(theme["card"], theme["text"])
                self.assertEqual(theme["label"], "Comfortable")
            self.assertEqual(len(cards), 3)
            self.assertEqual(len(flowers), 3)
            self.assertEqual(flower_layouts, {"staggered", "bottom", "diagonal"})
            self.assertIn("blush_pink", gym.THEME_PALETTES)
            self.assertNotIn("lavender_moon", gym.THEME_PALETTES)
        finally:
            gym.state["theme_key"] = original_theme

    def test_flower_themes_use_distinct_balanced_layouts(self):
        staggered_top = gym._ornament_positions("staggered", "top", 300)
        staggered_bottom = gym._ornament_positions("staggered", "bottom", 300)
        self.assertTrue(staggered_top)
        self.assertTrue(staggered_bottom)
        self.assertFalse(gym._ornament_positions("staggered", "left", 300))

        self.assertTrue(gym._ornament_positions("bottom", "bottom", 300))
        self.assertFalse(gym._ornament_positions("bottom", "top", 300))

        diagonal_top = gym._ornament_positions("diagonal", "top", 300)
        diagonal_bottom = gym._ornament_positions("diagonal", "bottom", 300)
        self.assertTrue(all(position > 150 for position in diagonal_top))
        self.assertTrue(all(position < 150 for position in diagonal_bottom))
        self.assertFalse(gym._ornament_positions("diagonal", "left", 300))
        self.assertFalse(gym._ornament_positions("diagonal", "right", 300))

    def test_chart_shadow_starts_at_first_observation(self):
        line_coordinates = [120, 70, 180, 55, 240, 80]

        area = gym.build_chart_area_coordinates(line_coordinates, bottom=140)

        self.assertEqual(area[:2], [120, 140])
        self.assertEqual(area[-2:], [240, 140])
        self.assertEqual(area[2:-2], line_coordinates)

    def test_chart_shadow_does_not_bridge_missing_data(self):
        start = datetime(2026, 10, 22, 11, 0)
        points = [
            (start, 20),
            (start + timedelta(minutes=1), 21),
            (start + timedelta(minutes=20), 25),
            (start + timedelta(minutes=21), 24),
        ]

        segments = gym.split_chart_segments(points)

        self.assertEqual([len(segment) for segment in segments], [2, 2])

    def test_chart_axis_prioritizes_latest_observation_time(self):
        latest = datetime(2026, 10, 22, 12, 34)

        labels = gym.chart_time_labels(32, 410, 210, latest)

        self.assertEqual(labels[0], (210, "12:34", "center", True))
        self.assertIn((32, "09:00", "w", False), labels)
        self.assertIn((410, "20:50", "e", False), labels)

    def test_chart_axis_hides_endpoint_when_latest_time_would_overlap(self):
        latest = datetime(2026, 10, 22, 9, 2)

        labels = gym.chart_time_labels(32, 410, 38, latest)

        self.assertEqual(labels[0], (38, "09:02", "w", True))
        self.assertNotIn((32, "09:00", "w", False), labels)


if __name__ == "__main__":
    unittest.main()
