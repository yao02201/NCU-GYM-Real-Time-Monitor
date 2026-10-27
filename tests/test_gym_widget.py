import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

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

    def test_playlist_includes_images_and_gifs_in_filename_order(self):
        def fake_load(path, **_kwargs):
            return ([], []) if path.name == "broken.gif" else ([path.name], [100])

        with TemporaryDirectory(dir=Path.cwd()) as temporary:
            directory = Path(temporary)
            for name in ("b.jpg", "a.GIF", "broken.gif", "notes.txt"):
                (directory / name).touch()
            (directory / "subfolder.gif").mkdir()
            with patch.object(gym, "load_gif", side_effect=fake_load):
                frames, delays = gym.load_gif_playlist(directory)
            self.assertEqual(frames, ["a.GIF"] * 100 + ["b.jpg"] * 100)
            self.assertEqual(sum(delays[:100]), 10_000)
            self.assertEqual(sum(delays[100:]), 10_000)

    def test_timed_clip_keeps_animation_speed_and_trims_last_frame(self):
        frames, delays = gym.repeat_gif_for_duration(["a", "b"], [3000, 2000], 6500)
        self.assertEqual(frames, ["a", "b", "a"])
        self.assertEqual(delays, [3000, 2000, 1500])

    def test_timed_clip_skips_empty_animation(self):
        self.assertEqual(gym.repeat_gif_for_duration([], []), ([], []))

    def test_missing_category_folder_does_not_use_another_levels_animation(self):
        with TemporaryDirectory(dir=Path.cwd()) as temporary:
            self.assertEqual(gym.load_gif_playlist(Path(temporary) / "missing"), ([], []))

    def test_category_playlists_are_loaded_independently(self):
        with patch.dict(gym.state), patch.object(
            gym, "load_gif_playlist", side_effect=lambda path: ([path.name], [10_000])
        ):
            gym.load_all_gifs()
            self.assertEqual(set(gym.state["gif_sets"]), {"low", "mid", "high", "close"})
            for key in gym.state["gif_sets"]:
                self.assertEqual(gym.state["gif_sets"][key], ([key], [10_000]))

    def test_playful_status_labels_and_gifs_match_occupancy_boundaries(self):
        expected = [
            (0, "Gym time!", "low"), (30, "Gym time!", "low"),
            (31, "fuwaa", "mid"), (45, "fuwaa", "mid"),
            (46, "Stay in lab", "high"),
        ]
        with patch.dict(gym.state):
            for theme in gym.THEME_PALETTES:
                gym.state["theme_key"] = theme
                for count, label, animation in expected:
                    self.assertEqual(gym.get_theme(count)["label"], label)
                    self.assertEqual(gym.select_gif_key(count), animation)
        self.assertEqual(gym.select_gif_key(None), "close")

    def test_unavailable_data_keeps_playing_and_recovers_to_count_animation(self):
        with patch.dict(gym.state, {
            "last_updated_at": None, "gif_key": "mid", "gif_index": 10,
            "theme": gym.get_theme(None), "points_date": datetime.now().date(),
        }), patch.multiple(
            gym, create=True, apply_theme=Mock(), set_status_badge=Mock(),
            count_var=Mock(), append_log=Mock(), update_trend_display=Mock(), draw_chart=Mock(),
        ):
            unavailable = gym.OccupancyReading(gym.OccupancyStatus.UNAVAILABLE)
            gym.apply_count(unavailable)
            self.assertEqual(gym.state["gif_key"], "close")
            self.assertEqual(gym.state["gif_index"], 0)
            gym.state["gif_index"] = 15
            gym.apply_count(unavailable)
            self.assertEqual(gym.state["gif_index"], 15)
            gym.apply_count(gym.OccupancyReading(gym.OccupancyStatus.VALID, 20))
            self.assertEqual(gym.state["gif_key"], "low")
            self.assertEqual(gym.state["gif_index"], 0)

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
                self.assertEqual(theme["label"], "Gym time!")
            self.assertEqual(len(cards), 4)
            self.assertEqual(len(flowers), 4)
            self.assertEqual(flower_layouts, {"violet_sprig", "botanical", "diagonal", "none"})
            self.assertIn("blush_pink", gym.THEME_PALETTES)
            self.assertNotIn("lavender_moon", gym.THEME_PALETTES)
        finally:
            gym.state["theme_key"] = original_theme

    def test_saved_dark_themes_migrate_to_midnight_monitor(self):
        with patch.object(gym, "theme_preference_path") as preference:
            for previous in ("mint_chocolate", "midnight_racer"):
                preference.return_value.read_text.return_value = '{"theme": "' + previous + '"}'
                self.assertEqual(gym.load_theme_preference(), "midnight_monitor")

    def test_flower_themes_use_distinct_balanced_layouts(self):
        self.assertEqual(gym._ornament_positions("violet_sprig", "top", 300), [243, 276])
        self.assertEqual(gym._ornament_positions("violet_sprig", "bottom", 300), [32])
        self.assertFalse(gym._ornament_positions("violet_sprig", "left", 300))
        self.assertFalse(gym._ornament_positions("violet_sprig", "right", 300))

        self.assertEqual(gym._ornament_positions("botanical", "bottom", 300), [20, 49])
        self.assertEqual(gym._ornament_positions("botanical", "top", 300), [278])
        self.assertFalse(gym._ornament_positions("botanical", "left", 300))
        self.assertFalse(gym._ornament_positions("botanical", "right", 300))

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
