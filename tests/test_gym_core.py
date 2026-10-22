import unittest
from datetime import datetime, timedelta

from gym_core import (
    build_csv_url,
    estimate_trend,
    GymCountUnavailable,
    is_regular_open_time,
    parse_gym_count,
)


class GymCoreTests(unittest.TestCase):
    def test_parse_exact_gym_row(self):
        csv_text = "SPA池,N/A\n重訓室,30\n其他場館,99\n"
        self.assertEqual(parse_gym_count(csv_text), 30)

    def test_parse_rejects_unrecognised_count(self):
        with self.assertRaises(ValueError):
            parse_gym_count("重訓室,unknown\n")

    def test_parse_recognises_official_unavailable_state(self):
        with self.assertRaises(GymCountUnavailable):
            parse_gym_count("重訓室,N/A\n")

    def test_build_csv_url_uses_spreadsheet_iframe_not_first_iframe(self):
        html = """
        <iframe src="https://example.com/video"></iframe>
        <iframe src="https://docs.google.com/spreadsheets/d/e/key/pubhtml?gid=7&range=A1:B10"></iframe>
        """
        url = build_csv_url(html)
        self.assertEqual(
            url,
            "https://docs.google.com/spreadsheets/d/e/key/pub?output=csv&gid=7&range=A1%3AB10",
        )

    def test_regular_open_time_excludes_closing_time(self):
        self.assertFalse(is_regular_open_time(datetime(2026, 10, 22, 8, 59)))
        self.assertTrue(is_regular_open_time(datetime(2026, 10, 22, 9, 0)))
        self.assertTrue(is_regular_open_time(datetime(2026, 10, 22, 20, 49)))
        self.assertFalse(is_regular_open_time(datetime(2026, 10, 22, 20, 50)))

    def test_trend_uses_recent_linear_slope(self):
        start = datetime(2026, 10, 22, 10, 0)
        rising = [(start + timedelta(minutes=i), 20 + i) for i in range(10)]
        falling = [(start + timedelta(minutes=i), 40 - i) for i in range(10)]
        steady = [(start + timedelta(minutes=i), 30 + (i % 2)) for i in range(10)]

        rising_result = estimate_trend(rising)
        falling_result = estimate_trend(falling)
        steady_result = estimate_trend(steady)

        self.assertEqual(rising_result[0], "rising")
        self.assertAlmostEqual(rising_result[1], 10.0)
        self.assertEqual(falling_result[0], "falling")
        self.assertAlmostEqual(falling_result[1], -10.0)
        self.assertEqual(steady_result[0], "steady")

    def test_trend_needs_enough_history(self):
        start = datetime(2026, 10, 22, 10, 0)
        points = [(start + timedelta(minutes=i), 20 + i) for i in range(4)]
        self.assertIsNone(estimate_trend(points))


if __name__ == "__main__":
    unittest.main()
