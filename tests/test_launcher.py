import ctypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJECT_ROOT / "windows" / "Launch-NCUGymMonitor.ps1"


class LauncherTests(unittest.TestCase):
    def test_missing_project_environment_recommends_rerunning_setup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            result = self._launch(project)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Project environment", result.stderr)
        self.assertIn("Setup", result.stderr)

    def test_missing_checkout_is_reported(self):
        missing_checkout = Path(tempfile.gettempdir()) / "ncu-gym-missing-checkout"
        result = self._launch(missing_checkout)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checkout is missing", result.stderr)
        self.assertIn("Setup", result.stderr)

    def test_missing_windowed_python_is_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / ".venv" / "Scripts").mkdir(parents=True)

            result = self._launch(project)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("windowed Python", result.stderr)
        self.assertIn("Setup", result.stderr)

    def test_unexecutable_windowed_python_recommends_rerunning_setup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            pythonw = project / ".venv" / "Scripts" / "pythonw.exe"
            pythonw.parent.mkdir(parents=True)
            pythonw.write_text("not an executable", encoding="utf-8")
            self._write_launcher_entry_points(project)
            (project / "gym.pyw").write_text("pass\n", encoding="utf-8")
            self._write_runtime_contract(project)

            result = self._launch(project)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("windowed Python could not start", result.stderr)
        self.assertIn("Setup", result.stderr)

    def test_missing_widget_entry_point_is_reported_before_launch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            pythonw = project / ".venv" / "Scripts" / "pythonw.exe"
            pythonw.parent.mkdir(parents=True)
            pythonw.touch()
            (project / "monitor_entry.pyw").write_text("pass\n", encoding="utf-8")
            (project / "monitor_instance.py").write_text("pass\n", encoding="utf-8")

            result = self._launch(project)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Widget entry point", result.stderr)
        self.assertIn("checkout", result.stderr)

    def test_missing_instance_module_is_reported_before_launch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            self._create_project_environment(project)
            (project / "monitor_entry.pyw").write_text("pass\n", encoding="utf-8")
            (project / "gym.pyw").write_text("pass\n", encoding="utf-8")

            result = self._launch(project)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("instance module", result.stderr)
        self.assertIn("checkout", result.stderr)

    @unittest.skipUnless(sys.platform == "win32", "native dialog test requires Windows")
    def test_missing_checkout_shows_native_error_dialog(self):
        missing_checkout = Path(tempfile.gettempdir()) / "ncu-gym-native-dialog-missing"
        process = subprocess.Popen(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(LAUNCHER), "-ProjectRoot", str(missing_checkout),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            window = self._wait_for_process_window(process.pid, "NCU Gym Monitor")
            self.assertTrue(window, "native startup error dialog did not appear")
            ctypes.windll.user32.SendMessageW(window, 0x0010, 0, 0)
            self.assertNotEqual(process.wait(timeout=5), 0)
            process.communicate(timeout=1)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def test_missing_runtime_dependency_recommends_rerunning_setup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            self._create_project_environment(project)
            self._write_launcher_entry_points(project)
            (project / "gym.pyw").write_text("pass\n", encoding="utf-8")
            self._write_runtime_contract(project)

            result = self._launch(project)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runtime dependencies", result.stderr)
        self.assertIn("Setup", result.stderr)

    def test_valid_launch_starts_widget_silently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            self._create_project_environment(project)
            self._write_launcher_entry_points(project)
            self._add_runtime_import_stubs(project)
            marker = project / "launched.txt"
            (project / "gym.pyw").write_text(
                "import os\nfrom pathlib import Path\n"
                "Path(os.environ['NCU_GYM_TEST_MARKER']).write_text('launched', encoding='utf-8')\n",
                encoding="utf-8",
            )

            launch_environment = os.environ.copy()
            launch_environment["NCU_GYM_TEST_MARKER"] = str(marker)
            result = self._launch(project, "-Wait", env=launch_environment)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(marker.read_text(encoding="utf-8"), "launched")

    def test_launcher_defaults_to_checkout_containing_the_script(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "windows").mkdir()
            copied_launcher = project / "windows" / LAUNCHER.name
            shutil.copy2(LAUNCHER, copied_launcher)
            self._create_project_environment(project)
            self._write_launcher_entry_points(project)
            self._add_runtime_import_stubs(project)
            marker = project / "launched.txt"
            (project / "gym.pyw").write_text(
                "import os\nfrom pathlib import Path\n"
                "Path(os.environ['NCU_GYM_TEST_MARKER']).write_text('launched', encoding='utf-8')\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["NCU_GYM_TEST_MARKER"] = str(marker)

            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(copied_launcher),
                    "-NoDialog",
                    "-Wait",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "launched")

    def _launch(
        self,
        project: Path,
        *extra_args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(LAUNCHER),
                "-ProjectRoot",
                str(project),
                "-NoDialog",
                *extra_args,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=env,
        )

    def _create_project_environment(self, project: Path) -> None:
        subprocess.run(
            [sys.executable, "-m", "venv", str(project / ".venv")],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

    def _add_runtime_import_stubs(self, project: Path) -> None:
        self._write_runtime_contract(project)
        contract = (project / "requirements-runtime.txt").read_text(encoding="utf-8")
        for module_name in re.findall(r"#\s*import=([A-Za-z_][A-Za-z0-9_.]*)", contract):
            (project / f"{module_name}.py").write_text("", encoding="utf-8")

    def _write_runtime_contract(self, project: Path) -> None:
        shutil.copy2(
            PROJECT_ROOT / "requirements-runtime.txt",
            project / "requirements-runtime.txt",
        )

    def _write_launcher_entry_points(self, project: Path) -> None:
        (project / "monitor_entry.pyw").write_text(
            "import os\nfrom pathlib import Path\n"
            "marker = os.environ.get('NCU_GYM_TEST_MARKER')\n"
            "if marker: Path(marker).write_text('launched', encoding='utf-8')\n",
            encoding="utf-8",
        )
        (project / "monitor_instance.py").write_text("pass\n", encoding="utf-8")

    def _wait_for_process_window(self, process_id: int, title: str) -> int:
        deadline = __import__("time").monotonic() + 8
        while __import__("time").monotonic() < deadline:
            matches: list[int] = []
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

            def inspect_window(window: int, _parameter: int) -> bool:
                owner = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
                if owner.value != process_id:
                    return True
                length = ctypes.windll.user32.GetWindowTextLengthW(window)
                buffer = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(window, buffer, length + 1)
                if buffer.value == title:
                    matches.append(window)
                return True

            ctypes.windll.user32.EnumWindows(callback_type(inspect_window), 0)
            if matches:
                return matches[0]
            __import__("time").sleep(0.1)
        return 0


if __name__ == "__main__":
    unittest.main()
