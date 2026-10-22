import unittest

from monitor_instance import MonitorInstance


class MonitorInstanceTests(unittest.TestCase):
    def test_only_one_instance_can_hold_lock(self):
        first = MonitorInstance.try_acquire()
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(MonitorInstance.try_acquire())
        finally:
            first.release()

        replacement = MonitorInstance.try_acquire()
        self.assertIsNotNone(replacement)
        replacement.release()


if __name__ == "__main__":
    unittest.main()
