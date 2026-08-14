"""User-facing entry point for one NCU Gym Monitor instance."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
WIDGET_ENTRY = PROJECT_ROOT / "gym.pyw"


def show_startup_error(message: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, message, "NCU Gym Monitor", 0x10)


def main(arguments: list[str]) -> int:
    no_dialog = "--no-dialog" in arguments
    try:
        import runpy

        from monitor_instance import MonitorInstance
    except Exception as error:
        if not no_dialog:
            show_startup_error(
                "The Monitor startup files are missing or damaged. Restore the "
                f"checkout, then rerun Setup.\n\nDetails: {error}"
            )
        return 14

    try:
        monitor_instance = MonitorInstance.try_acquire()
    except Exception as error:
        if not no_dialog:
            show_startup_error(
                "The Monitor instance guard could not start. Rerun Setup; if "
                f"the problem continues, restore the checkout.\n\nDetails: {error}"
            )
        return 14

    if monitor_instance is None:
        return 0

    try:
        try:
            runpy.run_path(str(WIDGET_ENTRY), run_name="__main__")
            return 0
        except Exception as error:
            if not no_dialog:
                show_startup_error(
                    "The Widget failed during startup. Rerun Setup; if the problem "
                    f"continues, restore the checkout.\n\nDetails: {error}"
                )
            return 14
    finally:
        monitor_instance.release()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
