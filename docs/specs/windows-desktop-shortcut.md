# Windows Desktop Shortcut

## Problem Statement

目前使用者無法從 Windows 桌面直接可靠地啟動 NCU Gym Monitor。目標電腦沒有一般可用的 `python`、`pythonw` 或 Python Launcher，`.pyw` 也沒有檔案關聯；即使專案已有 Widget 程式，雙擊原始檔或普通捷徑仍可能沒有反應。使用者希望桌面上有清楚可辨識的捷徑，雙擊後靜默開啟 Monitor，並在環境缺失或啟動失敗時得到明確回饋。

## Solution

提供一次性的 Windows `Setup`，在目前使用者範圍準備官方 Python runtime、專案專屬 `Project environment`、必要依賴及桌面捷徑。捷徑名稱為 `NCU Gym Monitor`，使用綠色啞鈴圖示，透過 `Launcher` 靜默啟動 Widget。

正常啟動不顯示命令列；失敗時顯示清楚的 Windows 錯誤對話框和修復提示。同一時間只允許一個 `Monitor instance`。捷徑綁定目前 checkout 的固定位置，專案移動後重新執行 Setup 修復。不加入 Windows 登入自動啟動。

## User Stories

1. As a monitor user, I want an `NCU Gym Monitor` shortcut on my Windows desktop, so that I can start the monitor by double-clicking it.
2. As a monitor user, I want the shortcut to use a green dumbbell icon, so that I can recognize it quickly.
3. As a monitor user, I want a successful launch to show only the Widget, so that no command prompt remains open.
4. As a monitor user, I want the Launcher to use the current checkout, so that it runs my latest local code.
5. As a monitor user, I want Setup to detect a suitable Python installation, so that Python is not reinstalled unnecessarily.
6. As a monitor user without Python, I want Setup to obtain Python from an official source, so that I do not configure it manually.
7. As a security-conscious user, I want downloaded installation media validated before execution, so that Setup does not run an untrusted file.
8. As a monitor user, I want Python installed only for my Windows account, so that Setup does not require a system-wide deployment.
9. As a monitor user, I want a dedicated Project environment, so that other Python projects cannot change the Monitor's dependencies.
10. As a monitor user, I want Setup to install only Widget runtime dependencies, so that Notebook packages are not required for startup.
11. As a monitor user, I want Setup to be safe to rerun, so that I can repair the environment or shortcut.
12. As a monitor user, I want Setup to recreate a missing or outdated shortcut, so that recovery needs no manual shortcut editing.
13. As a monitor user, I want Setup to identify the failed step, so that Python, dependency, and shortcut failures are distinguishable.
14. As a monitor user, I want the Launcher to detect a moved or deleted checkout, so that failure is not silent.
15. As a monitor user, I want the Launcher to detect a missing Project environment, so that I know to rerun Setup.
16. As a monitor user, I want startup errors shown in a native Windows dialog, so that errors remain visible without a console.
17. As a monitor user, I want error messages to recommend an actionable repair, so that I know what to do next.
18. As a monitor user, I want only one Monitor instance at a time, so that repeated double-clicks do not create overlapping Widgets.
19. As a monitor user, I want a repeated launch to exit quietly, so that accidental double-clicks do not interrupt me.
20. As a data collector, I want repeated launches to avoid duplicate polling and CSV writers, so that the source and collected data remain well behaved.
21. As a monitor user, I want closing the Widget to release the single-instance guard, so that I can launch it again later.
22. As a monitor user, I want the shortcut tied to this checkout, so that no hidden source copy becomes stale.
23. As a monitor user, I want rerunning Setup after moving the project to update the shortcut target, so that relocation has a simple recovery path.
24. As a monitor user, I do not want automatic Windows login startup, so that the Monitor runs only when requested.
25. As a project maintainer, I want runtime requirements declared in the repository, so that Setup and development share one dependency contract.
26. As a project maintainer, I want Launcher and Setup behavior documented, so that later changes preserve the agreed experience.
27. As a project maintainer, I want tests to verify user-visible behavior rather than private helpers, so that refactoring stays inexpensive.
28. As a project maintainer, I want real desktop integration covered by a bounded Windows smoke test, so that automated tests do not modify the actual desktop or install Python.
29. As a project maintainer, I want the shortcut icon stored as a repository-owned asset, so that Setup can recreate it consistently.

## Implementation Decisions

- Target the current user's Windows machine only; this is not a portable or public application installer.
- Setup is a one-time, per-user, idempotent workflow. Rerunning it repairs the Project environment and desktop shortcut.
- Setup first discovers a suitable regular Python installation. If none exists, it downloads a supported CPython installer over HTTPS from an official Python source, validates it, and performs a current-user installation without administrator-wide deployment.
- Setup creates a Project environment dedicated to the current checkout. The Launcher must not depend on a Codex-managed runtime or arbitrary system packages.
- Runtime dependencies are declared separately from analytics and Notebook dependencies.
- The shortcut is named `NCU Gym Monitor`, uses a repository-owned green dumbbell `.ico`, and resolves the actual Windows desktop location.
- The shortcut targets a stable Launcher associated with the checkout, not the raw `.pyw` file association.
- The Launcher uses the Project environment's windowed Python executable so successful startup creates no console.
- Before launch, the Launcher validates the checkout, Project environment, windowed Python executable, Widget entry point, and runtime imports.
- Startup failures use a native Windows dialog with a concise cause and repair instruction. Successful launch is silent apart from the Widget.
- The Monitor enforces one Monitor instance with a Windows-appropriate process-wide lock. A second launch exits before polling or CSV logging starts, and the lock is released on normal exit or startup failure.
- The shortcut is intentionally bound to the current checkout. Moving or renaming it is repaired by rerunning Setup; no filesystem search or hidden source copy is introduced.
- Setup may display progress and errors; the no-console requirement applies to normal shortcut launches.
- Existing Widget layout, thresholds, GIF behavior, polling cadence, CSV schema, and analytics remain unchanged except for the minimal single-instance integration.
- Setup creates no Windows startup entry, scheduled task, service, or tray process.
- Use the glossary terms `Desktop shortcut`, `Launcher`, `Project environment`, `Monitor instance`, and `Setup` consistently.

## Testing Decisions

- Use one high-level seam: invoke the user-facing Setup and Launcher entry points and assert external behavior. Do not bind tests to private PowerShell functions, exact command construction, or private Python helpers.
- Automated Setup tests use temporary directories and a redirected or fake desktop. They must not install real Python, alter the real desktop, or start the live Widget.
- Setup coverage includes existing-Python detection, the missing-Python branch through a controlled installer substitute, environment orchestration, dependency failure, shortcut creation, rerun and idempotency, and relocation repair.
- Launcher coverage includes valid launch, missing checkout, missing Project environment, missing windowed Python, missing Widget entry point, missing dependency, and user-visible error behavior.
- Single-instance behavior is tested at the application boundary: start one controlled Monitor process, attempt a second launch, verify only one reaches polling or logging initialization, then verify a new instance can start after the first exits.
- Shortcut tests assert name, target, arguments, working directory, and icon through the created shortcut representation, not helper internals.
- The repository has no existing test prior art, so introduce only the minimum harness needed for this high-level seam.
- Completion requires one bounded manual Windows smoke test: run Setup on the target account, verify the real shortcut and icon, launch without a console, repeat-launch without a second Widget, close and relaunch, and exercise one controlled error dialog.
- The smoke test confirms that normal launch uses the Project environment rather than Codex runtime and that no login auto-start entry was created.

## Out of Scope

- Packaging as a standalone `.exe`, MSI, MSIX, or public installer.
- Supporting macOS, Linux, other Windows accounts, or enterprise deployment.
- Bundling a portable Python runtime inside the repository.
- Windows login auto-start, scheduled tasks, services, or tray processes.
- Automatically finding a moved checkout or copying source outside it.
- Bringing an existing Widget to the foreground; repeated launch only exits quietly.
- Changing Widget UI, colors, thresholds, GIF behavior, polling frequency, data source, CSV schema, or Notebook analysis.
- Solving the existing blocking-network and UI responsiveness concern.
- Uninstalling Python or providing a general application uninstaller.
- Publishing a release artifact for other users.
- Real installer execution or real desktop mutation in automated CI.

## Further Notes

- Inspection found no system `python`, `pythonw`, or `py` command and no `.pyw` association on the target machine.
- A Codex-bundled Python exists but is excluded because its cache path is not a stable dependency and it lacks at least one required runtime package.
- The current application has no single-instance guard; separate launches create independent Tk roots, polling loops, and CSV writers.
- The repository currently has no automated test framework or CI.
- The agreed checkout is currently fixed on the target machine, but the spec records the binding concept rather than treating an absolute path as portable configuration.
- No ADR is required: these choices are local, easy to revise, and do not create meaningful architectural lock-in.
