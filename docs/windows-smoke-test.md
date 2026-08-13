# Windows Desktop shortcut smoke test

Run this bounded test on the target Windows account after automated tests pass.

## Procedure

- [ ] Run Setup from the intended checkout and confirm it completes.
- [ ] Confirm the desktop contains exactly one **NCU Gym Monitor** shortcut with
      the green dumbbell icon.
- [ ] Inspect the shortcut and confirm it targets the checkout's Launcher and
      uses the checkout as its working directory.
- [ ] Double-click the shortcut and confirm the Widget opens without a command
      prompt flashing or remaining visible.
- [ ] Double-click again and confirm no second Widget, polling loop, or CSV writer
      starts.
- [ ] Close the Widget, launch it again, and confirm it opens normally.
- [ ] Temporarily rename `.venv`, launch the shortcut, and confirm a native error
      dialog recommends rerunning Setup. Restore `.venv` afterward.
- [ ] Confirm the running Widget uses the checkout's `.venv` and not a
      Codex-managed runtime.
- [ ] Confirm Setup created no login startup entry, scheduled task, Windows
      service, or tray process.

### Widget window controls

- [ ] Confirm the borderless Widget has a minimize control to the left of close
      and that both controls provide hover feedback.
- [ ] Minimize the Widget and confirm it remains available from the Windows
      taskbar with the NCU Gym icon.
- [ ] Restore it from the taskbar and confirm it is borderless and topmost
      without an additional focus-forcing action.
- [ ] Resize from all four edges and all four corners, confirming the pointer
      shows the matching resize cursor and drag-to-move still works elsewhere.
- [ ] Confirm the Widget stops shrinking at `240×120`.
- [ ] Confirm the occupancy GIF hides below `300px` wide, returns at or above
      `300px`, and does not scale when the Widget grows.
- [ ] Move and resize the Widget, close it, and confirm the next launch restores
      the last normal geometry.
- [ ] Change the connected-display layout or provide an off-screen saved
      position and confirm startup falls back to the safe `340×165` geometry.

## Result

Status: **Passed on 2026-08-07** on the target Windows account.

- Setup installed official per-user CPython 3.13.15, created the checkout's
  `.venv`, installed the declared runtime dependencies, and created exactly one
  Desktop shortcut.
- The shortcut target, arguments, working directory, and icon all referenced the
  intended checkout.
- The repaired shortcut targets GUI-subsystem `wscript.exe`, which invokes the
  repository-owned VBS wrapper. A five-second high-frequency launch check found
  zero visible PowerShell windows while the Widget opened normally.
- Launching opened a responsive Tk Widget through the Project environment with
  no command prompt flashing or left visible.
- Windows represented the one logical Monitor instance as a normal venv
  redirector/CPython parent-child pair. A repeated shortcut launch left the PID
  set unchanged, confirming that no second Monitor instance started.
- A normal `WM_CLOSE` removed the complete process pair; launching afterward
  created a new pair, confirming that the single-instance guard was released.
- Temporarily moving `.venv` produced a native **NCU Gym Monitor** error dialog;
  `.venv` was restored immediately afterward.
- No matching login Run entry, Startup-folder shortcut, scheduled task, Windows
  service, or tray process was created.

## Widget window control result

Status: **Targeted native checks passed on 2026-08-13** on the target Windows
account.

- An isolated real Tk/Win32 Widget passed control hover, edge cursor,
  taskbar minimization, restoration, borderless restoration, topmost
  restoration, taskbar application-window style, compact-layout detection,
  and responsive GIF hiding checks.
- The connected-display boundary enumerated both current Windows work areas.
- The normal Launcher correctly declined to create a second Monitor instance
  because a Monitor instance dating from 2026-08-11 was already active. That
  existing user process was left running and was not used to judge the newly
  loaded Widget code.
- The remaining checkbox procedure is retained for a hands-on pass after the
  existing Monitor instance is closed normally.
