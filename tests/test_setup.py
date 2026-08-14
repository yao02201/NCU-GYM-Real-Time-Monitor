import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETUP = PROJECT_ROOT / "windows" / "Setup-NCUGymMonitor.ps1"


class SetupTests(unittest.TestCase):
    def test_existing_python_creates_repairable_environment_and_shortcut(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            self._create_checkout(project)
            desktop.mkdir()

            first = self._run_setup(project, desktop)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self._run_setup(project, desktop)
            self.assertEqual(second.returncode, 0, second.stderr)

            self.assertTrue((project / ".venv" / "Scripts" / "pythonw.exe").is_file())
            shortcut_path = desktop / "NCU Gym Monitor.lnk"
            self.assertTrue(shortcut_path.is_file())
            self.assertEqual(list(desktop.glob("NCU Gym Monitor*.lnk")), [shortcut_path])

            shortcut = self._read_shortcut(shortcut_path)
            self.assertTrue(shortcut["TargetPath"].lower().endswith("wscript.exe"))
            self.assertEqual(self._pe_subsystem(Path(shortcut["TargetPath"])), 2)
            self.assertIn("Launch-NCUGymMonitor.vbs", shortcut["Arguments"])
            self.assertEqual(Path(shortcut["WorkingDirectory"]), project)
            self.assertIn("ncu-gym-monitor.ico", shortcut["IconLocation"])

    def test_missing_python_uses_validated_controlled_installer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            marker = test_root / "installer-ran.txt"
            installer = test_root / "python-installer.cmd"
            self._create_checkout(project)
            desktop.mkdir()
            installer.write_text(
                "@echo off\r\necho installed>\"%NCU_GYM_INSTALL_MARKER%\"\r\nexit /b 0\r\n",
                encoding="utf-8",
            )
            installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()
            environment = os.environ.copy()
            environment["NCU_GYM_INSTALL_MARKER"] = str(marker)

            result = self._run_setup(
                project,
                desktop,
                python_path=None,
                extra_args=(
                    "-TestMode",
                    "-SkipPythonDiscovery",
                    "-PythonInstallerPath",
                    str(installer),
                    "-PythonInstallerSha256",
                    installer_hash,
                    "-InstalledPythonPath",
                    sys.executable,
                ),
                env=environment,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "installed")
            self.assertTrue((project / ".venv" / "Scripts" / "pythonw.exe").is_file())
            self.assertTrue((desktop / "NCU Gym Monitor.lnk").is_file())

    def test_invalid_python_installer_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            marker = test_root / "installer-ran.txt"
            installer = test_root / "python-installer.cmd"
            self._create_checkout(project)
            desktop.mkdir()
            installer.write_text(
                "@echo off\r\necho installed>\"%NCU_GYM_INSTALL_MARKER%\"\r\nexit /b 0\r\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["NCU_GYM_INSTALL_MARKER"] = str(marker)

            result = self._run_setup(
                project,
                desktop,
                python_path=None,
                extra_args=(
                    "-TestMode",
                    "-SkipPythonDiscovery",
                    "-PythonInstallerPath",
                    str(installer),
                    "-PythonInstallerSha256",
                    "0" * 64,
                    "-InstalledPythonPath",
                    sys.executable,
                ),
                env=environment,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertIn("Python installer validation", result.stderr)
            self.assertIn("SHA-256", result.stderr)

    def test_controlled_installer_options_are_rejected_outside_test_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            installer = test_root / "python-installer.cmd"
            self._create_checkout(project)
            desktop.mkdir()
            installer.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
            installer_hash = hashlib.sha256(installer.read_bytes()).hexdigest()

            result = self._run_setup(
                project,
                desktop,
                python_path=None,
                extra_args=(
                    "-SkipPythonDiscovery",
                    "-PythonInstallerPath",
                    str(installer),
                    "-PythonInstallerSha256",
                    installer_hash,
                    "-InstalledPythonPath",
                    sys.executable,
                ),
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("test-only", result.stderr)
            self.assertFalse((desktop / "NCU Gym Monitor.lnk").exists())

    def test_dependency_failure_does_not_create_shortcut(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            self._create_checkout(project)
            desktop.mkdir()
            (project / "requirements-runtime.txt").write_text(
                "--definitely-not-a-pip-option\n",
                encoding="utf-8",
            )

            result = self._run_setup(project, desktop)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("runtime dependency installation", result.stderr)
            self.assertFalse((desktop / "NCU Gym Monitor.lnk").exists())

    def test_rerunning_setup_after_relocation_updates_shortcut_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            original_project = test_root / "original-checkout"
            moved_project = test_root / "moved-checkout"
            desktop = test_root / "Desktop"
            self._create_checkout(original_project)
            self._create_checkout(moved_project)
            desktop.mkdir()

            first = self._run_setup(original_project, desktop)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self._run_setup(moved_project, desktop)
            self.assertEqual(second.returncode, 0, second.stderr)

            shortcut = self._read_shortcut(desktop / "NCU Gym Monitor.lnk")
            self.assertEqual(Path(shortcut["WorkingDirectory"]), moved_project)
            self.assertIn(str(moved_project), shortcut["Arguments"])
            self.assertNotIn(str(original_project), shortcut["Arguments"])

    def test_unsuitable_python_is_rejected_before_environment_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            unsuitable_python = test_root / "old-python.cmd"
            self._create_checkout(project)
            desktop.mkdir()
            unsuitable_python.write_text("@echo off\r\nexit /b 1\r\n", encoding="utf-8")

            result = self._run_setup(project, desktop, python_path=str(unsuitable_python))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Python discovery", result.stderr)
            self.assertIn("Python 3.10", result.stderr)
            self.assertFalse((project / ".venv").exists())

    def test_setup_defaults_to_checkout_containing_the_script(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            self._create_checkout(project)
            shutil.copy2(SETUP, project / "windows" / SETUP.name)
            desktop.mkdir()

            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(project / "windows" / SETUP.name),
                    "-DesktopDirectory",
                    str(desktop),
                    "-PythonPath",
                    sys.executable,
                    "-TestMode",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            shortcut = self._read_shortcut(desktop / "NCU Gym Monitor.lnk")
            self.assertEqual(Path(shortcut["WorkingDirectory"]), project)

    def test_damaged_project_environment_is_recreated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            self._create_checkout(project)
            desktop.mkdir()
            damaged_python = project / ".venv" / "Scripts" / "python.exe"
            damaged_python.parent.mkdir(parents=True)
            damaged_python.write_text("damaged", encoding="utf-8")

            result = self._run_setup(project, desktop)

            self.assertEqual(result.returncode, 0, result.stderr)
            version_check = subprocess.run(
                [str(damaged_python), "-c", "import sys; print(sys.version_info[:2])"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(version_check.returncode, 0, version_check.stderr)
            self.assertTrue((desktop / "NCU Gym Monitor.lnk").is_file())

    def test_environment_health_check_rejects_a_base_interpreter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            fake_scripts = project / ".venv" / "Scripts"
            base_python = Path(sys.base_prefix) / "python.exe"
            base_dll = Path(sys.base_prefix) / (
                f"python{sys.version_info.major}{sys.version_info.minor}.dll"
            )
            self._create_checkout(project)
            desktop.mkdir()
            fake_scripts.mkdir(parents=True)
            shutil.copy2(base_python, fake_scripts / "python.exe")
            shutil.copy2(base_dll, fake_scripts / base_dll.name)

            result = self._run_setup(project, desktop)

            self.assertEqual(result.returncode, 0, result.stderr)
            health_check = subprocess.run(
                [
                    str(fake_scripts / "python.exe"),
                    "-c",
                    "import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(health_check.returncode, 0, health_check.stderr)
            self.assertTrue((fake_scripts / "pythonw.exe").is_file())

    def test_codex_python_is_rejected_for_normal_setup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_root = Path(temp_dir)
            project = test_root / "checkout"
            desktop = test_root / "Desktop"
            codex_python = test_root / ".codex" / "python.exe"
            self._create_checkout(project)
            desktop.mkdir()
            codex_python.parent.mkdir()
            os.link(sys.executable, codex_python)

            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SETUP),
                    "-ProjectRoot",
                    str(project),
                    "-DesktopDirectory",
                    str(desktop),
                    "-PythonPath",
                    str(codex_python),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Codex-managed runtime", result.stderr)

    def _create_checkout(self, project: Path) -> None:
        (project / "windows").mkdir(parents=True)
        (project / "assets").mkdir()
        shutil.copy2(
            PROJECT_ROOT / "windows" / "Launch-NCUGymMonitor.ps1",
            project / "windows" / "Launch-NCUGymMonitor.ps1",
        )
        shutil.copy2(
            PROJECT_ROOT / "windows" / "Launch-NCUGymMonitor.vbs",
            project / "windows" / "Launch-NCUGymMonitor.vbs",
        )
        shutil.copy2(
            PROJECT_ROOT / "assets" / "ncu-gym-monitor.ico",
            project / "assets" / "ncu-gym-monitor.ico",
        )
        (project / "monitor_entry.pyw").write_text("pass\n", encoding="utf-8")
        (project / "monitor_instance.py").write_text("pass\n", encoding="utf-8")
        (project / "gym.pyw").write_text("pass\n", encoding="utf-8")
        (project / "requirements-runtime.txt").write_text("", encoding="utf-8")

    def _run_setup(
        self,
        project: Path,
        desktop: Path,
        *,
        python_path: str | None = sys.executable,
        extra_args: tuple[str, ...] = (),
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SETUP),
                "-ProjectRoot",
                str(project),
                "-DesktopDirectory",
                str(desktop),
            ]
        if python_path is not None:
            arguments.extend(("-PythonPath", python_path, "-TestMode"))
        arguments.extend(extra_args)
        return subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=env,
        )

    def _read_shortcut(self, shortcut_path: Path) -> dict[str, str]:
        escaped_path = str(shortcut_path).replace("'", "''")
        command = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('"
            + escaped_path
            + "'); [pscustomobject]@{TargetPath=$s.TargetPath;Arguments=$s.Arguments;"
            "WorkingDirectory=$s.WorkingDirectory;IconLocation=$s.IconLocation}|ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return json.loads(result.stdout)

    def _pe_subsystem(self, executable: Path) -> int:
        image = executable.read_bytes()
        pe_offset = int.from_bytes(image[0x3C:0x40], "little")
        optional_header = pe_offset + 24
        return int.from_bytes(
            image[optional_header + 68 : optional_header + 70],
            "little",
        )


if __name__ == "__main__":
    unittest.main()
