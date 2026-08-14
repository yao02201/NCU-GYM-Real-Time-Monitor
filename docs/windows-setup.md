# Windows Setup and recovery

## Install the Desktop shortcut

Open PowerShell in the checkout and run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\Setup-NCUGymMonitor.ps1
```

Setup operates only for the current Windows account. It performs these steps:

1. Find a suitable regular Python 3.10 or newer installation.
2. If Python is missing, download the pinned official CPython installer from
   `python.org`, verify its SHA-256 and Python Software Foundation signature, and
   install it for the current user.
3. Create the checkout's `.venv` Project environment.
4. Install only the dependencies declared in `requirements-runtime.txt`.
5. Create or repair the **NCU Gym Monitor** Desktop shortcut.

Normal launches first use the GUI-based Windows Script Host wrapper, which starts
the PowerShell Launcher with its window hidden. The Launcher then uses the Project
environment's windowed Python executable and the single-instance
`monitor_entry.pyw` entry point. Only the Widget appears; no command prompt flashes
or remains open.

## Repair

Rerun Setup whenever:

- the checkout has moved or been renamed;
- `.venv` is missing or damaged;
- the Desktop shortcut is missing or points to an old checkout;
- the Launcher reports missing runtime dependencies.

Setup is idempotent: rerunning it repairs the same Project environment and
Desktop shortcut instead of creating duplicates.

## Launcher diagnostics

The Desktop shortcut targets `wscript.exe` and the repository-owned
`Launch-NCUGymMonitor.vbs` wrapper so no console process is shown. The PowerShell
Launcher validates the checkout, Project environment, windowed Python executable,
Widget entry point, and runtime imports. When startup cannot proceed, it displays
a native **NCU Gym Monitor** error dialog with a repair instruction.

A repeated launch exits quietly while another Monitor instance is active. After
the Widget closes, its process-wide guard is released and it can be launched
again.

## Intentional limitations

- The Desktop shortcut is bound to this checkout; Setup does not search for a
  moved checkout or keep a hidden source copy.
- Setup does not create a Windows login startup entry, scheduled task, service,
  or tray process.
- This workflow is not an MSI, MSIX, standalone executable, or public installer.
