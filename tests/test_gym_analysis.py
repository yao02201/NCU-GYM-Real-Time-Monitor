import unittest
from datetime import datetime, timedelta

import pandas as pd

from gym_analysis import build_daily_windows, summarize_windows


def make_hour(date: datetime, counts: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [date + timedelta(minutes=i) for i in range(len(counts))],
            "count": counts,
        }
    )


class GymAnalysisTests(unittest.TestCase):
    def test_ninety_percent_at_or_below_threshold_is_comfortable(self):
        logs = make_hour(datetime(2026, 10, 19, 9, 0), [30] * 54 + [31] * 6)
        windows = build_daily_windows(logs, step_minutes=10)

        first = windows.loc[windows["start_time"] == "09:00"].iloc[0]
        self.assertAlmostEqual(first["under_threshold_share"], 0.9)
        self.assertTrue(bool(first["comfortable"]))
        self.assertFalse(bool(first["entire_hour_under_threshold"]))

    def test_less_than_ninety_percent_is_not_comfortable(self):
        logs = make_hour(datetime(2026, 10, 19, 9, 0), [30] * 53 + [31] * 7)
        windows = build_daily_windows(logs, step_minutes=10)

        first = windows.loc[windows["start_time"] == "09:00"].iloc[0]
        self.assertFalse(bool(first["comfortable"]))

    def test_incomplete_window_is_excluded(self):
        logs = make_hour(datetime(2026, 10, 19, 9, 0), [10] * 20)
        windows = build_daily_windows(logs, step_minutes=10)
        self.assertTrue(windows.empty)

    def test_summary_prefers_reliable_window_over_lower_average(self):
        windows = pd.DataFrame(
            [
                {
                    "date": datetime(2026, 10, 19).date(),
                    "weekday": 0,
                    "start_minute": 540,
                    "start_time": "09:00",
                    "mean_count": 10,
                    "p90_count": 35,
                    "comfortable": False,
                    "entire_hour_under_threshold": False,
                },
                {
                    "date": datetime(2026, 10, 26).date(),
                    "weekday": 0,
                    "start_minute": 540,
                    "start_time": "09:00",
                    "mean_count": 10,
                    "p90_count": 35,
                    "comfortable": False,
                    "entire_hour_under_threshold": False,
                },
                {
                    "date": datetime(2026, 10, 19).date(),
                    "weekday": 0,
                    "start_minute": 600,
                    "start_time": "10:00",
                    "mean_count": 20,
                    "p90_count": 25,
                    "comfortable": True,
                    "entire_hour_under_threshold": True,
                },
                {
                    "date": datetime(2026, 10, 26).date(),
                    "weekday": 0,
                    "start_minute": 600,
                    "start_time": "10:00",
                    "mean_count": 20,
                    "p90_count": 25,
                    "comfortable": True,
                    "entire_hour_under_threshold": True,
                },
            ]
        )

        summary = summarize_windows(windows, minimum_days=2)
        best = summary.loc[summary["rank"] == 1].iloc[0]
        self.assertEqual(best["start_time"], "10:00")


if __name__ == "__main__":
    unittest.main()
