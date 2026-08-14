import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MONITOR_ENTRY = PROJECT_ROOT / "monitor_entry.pyw"


class MonitorInstanceTests(unittest.TestCase):
    def test_lock_initialization_failure_stops_before_widget_initialization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            marker = project / "initialized.txt"
            shutil.copy2(MONITOR_ENTRY, project / "monitor_entry.pyw")
            (project / "monitor_instance.py").write_text(
                "class MonitorInstance:\n"
                "    @classmethod\n"
                "    def try_acquire(cls):\n"
                "        raise OSError('lock storage unavailable')\n",
                encoding="utf-8",
            )
            (project / "gym.pyw").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('initialized', encoding='utf-8')\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(project / "monitor_entry.pyw"), "--no-dialog"],
                cwd=project,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 14)
            self.assertFalse(marker.exists())

    def test_repeated_launch_exits_until_active_monitor_stops(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            marker = project / "started.txt"
            shutil.copy2(MONITOR_ENTRY, project / "monitor_entry.pyw")
            shutil.copy2(PROJECT_ROOT / "monitor_instance.py", project / "monitor_instance.py")
            (project / "gym.pyw").write_text(
                "import os\nimport time\nfrom pathlib import Path\n"
                "marker = Path(os.environ['NCU_GYM_TEST_MARKER'])\n"
                "with marker.open('a', encoding='utf-8') as output:\n"
                "    output.write('initialized\\n')\n"
                "time.sleep(float(os.environ['NCU_GYM_TEST_HOLD_SECONDS']))\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["NCU_GYM_TEST_MARKER"] = str(marker)
            environment["NCU_GYM_TEST_HOLD_SECONDS"] = "1.5"
            first = subprocess.Popen(
                [sys.executable, str(project / "monitor_entry.pyw"), "--no-dialog"],
                cwd=project,
                env=environment,
            )

            try:
                self._wait_for_lines(marker, 1)

                repeated = subprocess.run(
                    [sys.executable, str(project / "monitor_entry.pyw"), "--no-dialog"],
                    cwd=project,
                    timeout=2,
                    check=False,
                    env=environment,
                )
                self.assertEqual(repeated.returncode, 0)
                self.assertEqual(marker.read_text(encoding="utf-8").splitlines(), ["initialized"])
            finally:
                first.wait(timeout=3)

            environment["NCU_GYM_TEST_HOLD_SECONDS"] = "0.1"
            relaunched = subprocess.run(
                [sys.executable, str(project / "monitor_entry.pyw"), "--no-dialog"],
                cwd=project,
                timeout=2,
                check=False,
                env=environment,
            )
            self.assertEqual(relaunched.returncode, 0)
            self.assertEqual(
                marker.read_text(encoding="utf-8").splitlines(),
                ["initialized", "initialized"],
            )

    def _wait_for_lines(self, marker: Path, expected: int) -> None:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if marker.exists() and len(marker.read_text(encoding="utf-8").splitlines()) >= expected:
                return
            time.sleep(0.05)
        self.fail(f"Monitor did not record {expected} start(s) before timeout")


if __name__ == "__main__":
    unittest.main()
