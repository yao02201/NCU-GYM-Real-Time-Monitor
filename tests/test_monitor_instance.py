import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from monitor_instance import MonitorInstance


class MonitorInstanceTests(unittest.TestCase):
    def setUp(self):
        # Do not compete with an actual monitor running on the developer's PC.
        temporary = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(temporary.cleanup)
        lock_directory = patch("monitor_instance.tempfile.gettempdir", return_value=temporary.name)
        lock_directory.start()
        self.addCleanup(lock_directory.stop)

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
