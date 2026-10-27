"""Rebuild the README's historical charts with readable typography."""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from gym_analysis import build_daily_windows, load_logs, summarize_windows
from gym_core import CLOSE_TIME, COMFORT_THRESHOLD, OPEN_TIME


WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
COLORS = ["#C56B86", "#D98B62", "#C7A64B", "#6E9B82", "#668BB7", "#8A74B8", "#B278A3"]


def style_axes(axis, title, xlabel, ylabel):
    axis.set_title(title, loc="left", fontsize=19, weight="bold", pad=16)
    axis.set_xlabel(xlabel, fontsize=16, labelpad=10)
    axis.set_ylabel(ylabel, fontsize=16, labelpad=10)
    axis.tick_params(axis="both", labelsize=14, pad=6)
    axis.spines[["top", "right"]].set_visible(False)


def time_labels(minutes):
    return [f"{minute // 60:02d}:{minute % 60:02d}" for minute in minutes]


def save_figure(figure, path, period):
    figure.text(0.015, 0.012, period, fontsize=11, color="#756B70")
    figure.tight_layout(rect=(0, 0.05, 1, 1))
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def draw_weekday_average(logs, output, period):
    data = logs.copy()
    minute = data["timestamp"].dt.hour * 60 + data["timestamp"].dt.minute
    start = OPEN_TIME.hour * 60 + OPEN_TIME.minute
    end = CLOSE_TIME.hour * 60 + CLOSE_TIME.minute
    data = data[(minute >= start) & (minute < end)].copy()
    data["date"] = data["timestamp"].dt.date
    data["weekday"] = data["timestamp"].dt.dayofweek
    data["minute"] = (data["timestamp"].dt.hour * 60 + data["timestamp"].dt.minute) // 10 * 10
    daily = data.groupby(["date", "weekday", "minute"], as_index=False)["count"].mean()
    weekly = daily.groupby(["weekday", "minute"], as_index=False)["count"].mean()

    figure, axis = plt.subplots(figsize=(11, 6.4))
    for weekday, color in enumerate(COLORS):
        curve = weekly[weekly["weekday"] == weekday]
        if not curve.empty:
            axis.plot(curve["minute"], curve["count"], color=color, linewidth=2.3, label=WEEKDAYS[weekday])
    axis.axhline(COMFORT_THRESHOLD, color="#5D8A73", linewidth=1.7, linestyle="--", label="Comfort: 30")
    ticks = list(range(start, end, 60))
    axis.set_xlim(start, end)
    axis.set_xticks(ticks, time_labels(ticks), rotation=35, ha="right")
    style_axes(axis, "Average gym occupancy by weekday", "Time of day", "People")
    axis.grid(alpha=0.16)
    axis.legend(ncol=4, frameon=False, fontsize=13, columnspacing=1.0, handlelength=1.8)
    save_figure(figure, output / "weekday_average.png", period)


def draw_comfort_heatmap(logs, output, period):
    windows = build_daily_windows(logs, threshold=COMFORT_THRESHOLD)
    summary = summarize_windows(windows, minimum_days=1)
    if summary.empty:
        raise ValueError("No complete one-hour windows are available for the heatmap.")
    pivot = summary.pivot(index="weekday", columns="start_minute", values="comfort_probability").reindex(range(7))
    figure, axis = plt.subplots(figsize=(11, 6.1))
    image = axis.imshow(pivot, aspect="auto", vmin=0, vmax=1, cmap="RdYlGn")
    starts = list(pivot.columns)
    indexes = list(range(0, len(starts), 6))
    axis.set_xticks(indexes, time_labels([starts[index] for index in indexes]), rotation=35, ha="right")
    axis.set_yticks(range(7), WEEKDAYS)
    style_axes(axis, "Chance of a comfortable 60-minute workout", "Workout start time", "Weekday")
    for row in summary[summary["rank"] == 1].itertuples(index=False):
        axis.scatter(starts.index(row.start_minute), row.weekday, marker="*", s=135, color="white", edgecolor="#704556", linewidth=1.1)
    colorbar = figure.colorbar(image, ax=axis, fraction=0.035, pad=0.025)
    colorbar.set_label("Comfortable hours", fontsize=16, labelpad=12)
    colorbar.ax.tick_params(labelsize=13)
    colorbar.ax.yaxis.set_major_formatter(PercentFormatter(1))
    star = Line2D([], [], marker="*", color="none", markerfacecolor="white", markeredgecolor="#704556", markersize=13)
    figure.legend([star], ["Best observed start time"], loc="lower right", bbox_to_anchor=(0.985, 0.0), frameon=False, fontsize=12)
    save_figure(figure, output / "comfort_heatmap.png", period)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_DIR / "gym_count")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "for_git_intro")
    args = parser.parse_args()
    logs, warnings = load_logs(args.data_dir)
    period = f"{logs['timestamp'].min():%Y-%m-%d} to {logs['timestamp'].max():%Y-%m-%d}"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    draw_weekday_average(logs, args.output_dir, period)
    draw_comfort_heatmap(logs, args.output_dir, period)
    print(f"Rendered two charts from {len(logs):,} readings ({period}); {len(warnings)} load warnings.")


if __name__ == "__main__":
    main()
