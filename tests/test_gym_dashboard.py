import unittest

import pandas as pd

from gym_dashboard import filter_date_range, filter_open_hours


class GymDashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.logs = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [
                        "2026-10-20 08:59:00",
                        "2026-10-20 09:00:00",
                        "2026-10-20 20:49:00",
                        "2026-10-20 20:50:00",
                        "2026-10-21 10:00:00",
                    ]
                ),
                "count": [1, 2, 3, 4, 5],
            }
        )

    def test_date_range_is_inclusive_of_end_date(self):
        selected = filter_date_range(self.logs, "2026-10-21", "2026-10-21")
        self.assertEqual(selected["count"].tolist(), [5])

    def test_open_hours_exclude_closing_time(self):
        selected = filter_open_hours(self.logs)
        self.assertEqual(selected["count"].tolist(), [2, 3, 5])

    def test_invalid_date_range_is_rejected(self):
        with self.assertRaises(ValueError):
            filter_date_range(self.logs, "2026-10-22", "2026-10-20")


if __name__ == "__main__":
    unittest.main()
