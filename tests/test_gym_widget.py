from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gym_widget


class TkWindowPortTests(unittest.TestCase):
    def test_negative_virtual_desktop_coordinates_are_absolute(self) -> None:
        root = Mock()
        window = gym_widget.TkWindowPort(root)

        window.set_geometry(gym_widget.Geometry(480, 220, -300, -40))

        root.geometry.assert_called_once_with("480x220+-300+-40")


class GymWidgetStartupTests(unittest.TestCase):
    def test_enables_per_monitor_v2_when_windows_supports_it(self) -> None:
        set_context = Mock(return_value=True)
        windll = SimpleNamespace(
            user32=SimpleNamespace(SetProcessDpiAwarenessContext=set_context),
        )

        with (
            patch.object(gym_widget.sys, "platform", "win32"),
            patch.object(gym_widget.ctypes, "windll", windll),
        ):
            gym_widget.enable_per_monitor_dpi_awareness()

        context = set_context.call_args.args[0]
        self.assertEqual(
            context.value,
            gym_widget.ctypes.c_void_p(
                gym_widget.PER_MONITOR_AWARE_V2
            ).value,
        )

    def test_falls_back_to_shcore_when_per_monitor_v2_is_unavailable(self) -> None:
        set_awareness = Mock(return_value=0)
        set_legacy_awareness = Mock()
        windll = SimpleNamespace(
            user32=SimpleNamespace(SetProcessDPIAware=set_legacy_awareness),
            shcore=SimpleNamespace(SetProcessDpiAwareness=set_awareness),
        )

        with (
            patch.object(gym_widget.sys, "platform", "win32"),
            patch.object(gym_widget.ctypes, "windll", windll),
        ):
            gym_widget.enable_per_monitor_dpi_awareness()

        set_awareness.assert_called_once_with(
            gym_widget.PROCESS_PER_MONITOR_DPI_AWARE
        )
        set_legacy_awareness.assert_not_called()

    def test_main_enables_per_monitor_dpi_before_creating_tk_root(self) -> None:
        events: list[str] = []
        root = Mock()
        view = Mock()
        monitor = Mock()

        with (
            patch.object(
                gym_widget,
                "enable_per_monitor_dpi_awareness",
                side_effect=lambda: events.append("dpi"),
                create=True,
            ),
            patch.object(
                gym_widget.tk,
                "Tk",
                side_effect=lambda: events.append("tk") or root,
            ),
            patch.object(gym_widget, "TkWidgetView", return_value=view),
            patch.object(gym_widget, "RequestsHttpClient"),
            patch.object(gym_widget, "NcuOccupancySource"),
            patch.object(gym_widget, "CsvOccupancyLogger"),
            patch.object(gym_widget, "TkScheduler"),
            patch.object(gym_widget, "OccupancyMonitor", return_value=monitor),
        ):
            gym_widget.main()

        self.assertEqual(events, ["dpi", "tk"])


if __name__ == "__main__":
    unittest.main()
