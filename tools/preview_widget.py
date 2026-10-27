"""Render the real widget with demo data for screenshots, without live writes."""

import argparse
import math
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import gym


class PreviewInstance:
    def release(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=gym.THEME_PALETTES, default="midnight_monitor")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="gym-preview-") as temporary:
        gym.MonitorInstance.try_acquire = lambda: PreviewInstance()
        gym.window_state_path = lambda: Path(temporary) / "window-state.json"
        gym.load_theme_preference = lambda: args.theme
        gym.save_theme_preference = lambda _key: None
        gym.init_log_dir = lambda: None
        gym.load_today_points = lambda *_args: None
        gym.append_log = lambda *_args, **_kwargs: False
        gym.is_autostart_enabled = lambda: False
        gym.set_autostart = lambda _enabled: None

        def show_demo():
            gym.root.title("NCU Gym Preview")
            gym.root.geometry("480x490+120+120")
            day = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
            gym.state["points_date"] = day.date()
            gym.state["today_points"] = [
                (day + timedelta(minutes=minute), round(23 + 7 * math.sin(minute / 43) + 3 * math.sin(minute / 17)))
                for minute in range(0, 321, 5)
            ]
            gym.state["today_points"][-1] = (day + timedelta(minutes=320), 24)
            gym.state["count"] = 24
            gym.state["last_updated_at"] = day + timedelta(minutes=320)
            gym.count_var.set("24")
            gym.apply_theme(24)
            gym.update_trend_display()
            gym.set_gif_key("low")
            gym.root.update_idletasks()
            gym.update_responsive_layout()
            for index, theme in enumerate(gym.THEME_PALETTES, start=1):
                gym.root.bind(f"<F{index}>", lambda _event, key=theme: gym.select_theme(key))
            for key, geometry in (("F5", "220x110"), ("F6", "420x310"), ("F7", "480x490")):
                gym.root.bind(f"<{key}>", lambda _event, size=geometry: gym.root.geometry(size))
            gym.root.after(15 * 60 * 1000, gym.close_app)

        gym.refresh_data = show_demo
        gym.main()


if __name__ == "__main__":
    main()
