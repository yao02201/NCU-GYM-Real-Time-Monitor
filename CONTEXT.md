# NCU Gym Monitor

This context describes the user-facing concepts of the NCU gym occupancy monitor.

## Language

**Desktop shortcut**:
A Windows shortcut on the current user's desktop that starts the monitor from this local project checkout. It is not a portable installer or a distribution package for other users.
_Avoid_: Installer, release package

**Launcher**:
The silent Windows entry point used by the desktop shortcut. It starts the monitor without a console window and shows a clear error dialog when startup cannot proceed.
_Avoid_: Console script

**Project environment**:
The Python virtual environment dedicated to this local checkout and used by the launcher. It is based on a regular Python installation rather than a Codex-managed runtime.
_Avoid_: System Python, Codex runtime

**Monitor instance**:
One running copy of the desktop monitor. Only one monitor instance may exist at a time; a repeated launch exits without opening another widget or collector.
_Avoid_: Widget copy, duplicate process

**Setup**:
The one-time, per-user Windows process that installs an official Python runtime when needed, creates the project environment, installs dependencies, and creates the desktop shortcut.
_Avoid_: Application installer, system-wide installation
