"""Find reliable one-hour gym windows from the collected CSV logs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from gym_core import CLOSE_TIME, COMFORT_THRESHOLD, OPEN_TIME


WEEKDAY_NAMES = {
    0: "星期一",
    1: "星期二",
    2: "星期三",
    3: "星期四",
    4: "星期五",
    5: "星期六",
    6: "星期日",
}


def load_logs(data_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    """Load valid rows from all daily logs and report skipped files."""

    frames: list[pd.DataFrame] = []
    warnings: list[str] = []

    for path in sorted(data_dir.glob("gym_count_*.csv")):
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            warnings.append(f"{path.name}: 無法讀取 ({exc})")
            continue

        if not {"timestamp", "count"}.issubset(frame.columns):
            warnings.append(f"{path.name}: 缺少 timestamp 或 count 欄位")
            continue

        frame = frame[["timestamp", "count"]].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        frame["count"] = pd.to_numeric(frame["count"], errors="coerce")
        invalid_rows = int(frame[["timestamp", "count"]].isna().any(axis=1).sum())
        if invalid_rows:
            warnings.append(f"{path.name}: 略過 {invalid_rows} 筆無效資料")
        frame = frame.dropna().drop_duplicates("timestamp").sort_values("timestamp")
        frames.append(frame)

    if not frames:
        raise ValueError(f"{data_dir} 中沒有可用的 gym_count_*.csv")

    logs = pd.concat(frames, ignore_index=True)
    logs["count"] = logs["count"].astype(int)
    logs = logs[(logs["count"] >= 0) & (logs["count"] <= 500)]
    logs = logs.drop_duplicates("timestamp").sort_values("timestamp")
    return logs, warnings


def _minutes(value: object) -> int:
    return value.hour * 60 + value.minute


def build_daily_windows(
    logs: pd.DataFrame,
    threshold: int = COMFORT_THRESHOLD,
    step_minutes: int = 10,
    minimum_samples: int = 45,
    maximum_gap_minutes: float = 5.0,
) -> pd.DataFrame:
    """Build quality-checked 60-minute observations for every possible start."""

    required = {"timestamp", "count"}
    if not required.issubset(logs.columns):
        raise ValueError("資料必須包含 timestamp 與 count 欄位")
    if not 1 <= step_minutes <= 60:
        raise ValueError("step_minutes 必須介於 1 到 60")

    data = logs.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    data["count"] = pd.to_numeric(data["count"], errors="coerce")
    data = data.dropna().drop_duplicates("timestamp").sort_values("timestamp")
    data["date"] = data["timestamp"].dt.date

    open_minute = _minutes(OPEN_TIME)
    last_start_minute = _minutes(CLOSE_TIME) - 60
    results: list[dict[str, object]] = []

    for date, day in data.groupby("date"):
        midnight = pd.Timestamp(date)
        weekday = int(day["timestamp"].dt.dayofweek.iloc[0])

        for start_minute in range(open_minute, last_start_minute + 1, step_minutes):
            start = midnight + pd.Timedelta(minutes=start_minute)
            end = start + pd.Timedelta(hours=1)
            window = day[
                (day["timestamp"] >= start) & (day["timestamp"] < end)
            ].copy()

            if len(window) < minimum_samples:
                continue

            gaps = window["timestamp"].diff().dt.total_seconds().div(60)
            starts_on_time = window["timestamp"].iloc[0] <= start + pd.Timedelta(minutes=2.5)
            ends_on_time = window["timestamp"].iloc[-1] >= end - pd.Timedelta(minutes=2.5)
            has_large_gap = bool((gaps > maximum_gap_minutes).any())
            if not starts_on_time or not ends_on_time or has_large_gap:
                continue

            under_threshold_share = float((window["count"] <= threshold).mean())
            results.append(
                {
                    "date": date,
                    "weekday": weekday,
                    "start_minute": start_minute,
                    "start_time": f"{start_minute // 60:02d}:{start_minute % 60:02d}",
                    "samples": len(window),
                    "mean_count": float(window["count"].mean()),
                    "p90_count": float(window["count"].quantile(0.9)),
                    "max_count": int(window["count"].max()),
                    "under_threshold_share": under_threshold_share,
                    "comfortable": under_threshold_share >= 0.9,
                    "entire_hour_under_threshold": bool((window["count"] <= threshold).all()),
                }
            )

    return pd.DataFrame(results)


def summarize_windows(windows: pd.DataFrame, minimum_days: int = 3) -> pd.DataFrame:
    """Aggregate daily one-hour observations and rank recommendations."""

    if windows.empty:
        return pd.DataFrame()

    summary = (
        windows.groupby(["weekday", "start_minute", "start_time"], as_index=False)
        .agg(
            sample_days=("date", "nunique"),
            average_count=("mean_count", "mean"),
            p90_count=("p90_count", "mean"),
            comfort_probability=("comfortable", "mean"),
            entire_hour_probability=("entire_hour_under_threshold", "mean"),
        )
    )
    summary = summary[summary["sample_days"] >= minimum_days].copy()
    if summary.empty:
        return summary

    summary["weekday_name"] = summary["weekday"].map(WEEKDAY_NAMES)
    summary = summary.sort_values(
        ["weekday", "comfort_probability", "p90_count", "average_count"],
        ascending=[True, False, True, True],
    )
    summary["rank"] = summary.groupby("weekday").cumcount() + 1
    return summary.reset_index(drop=True)


def format_recommendations(summary: pd.DataFrame, threshold: int) -> str:
    if summary.empty:
        return "沒有足夠的完整一小時資料可供分析。"

    best = summary[summary["rank"] == 1].copy()
    lines = [
        f"舒適定義：60 分鐘內至少 90% 的觀測值 <= {threshold} 人",
        "",
        "星期    建議開始  平均人數  P90人數  舒適機率  全程達標  樣本天數",
    ]
    for row in best.itertuples(index=False):
        lines.append(
            f"{row.weekday_name:<5}  {row.start_time:<8}  "
            f"{row.average_count:>6.1f}  {row.p90_count:>7.1f}  "
            f"{row.comfort_probability:>7.0%}  "
            f"{row.entire_hour_probability:>7.0%}  {row.sample_days:>8}"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分析中大健身房最舒適的一小時")
    parser.add_argument("--data-dir", type=Path, default=Path("gym_count"))
    parser.add_argument("--threshold", type=int, default=COMFORT_THRESHOLD)
    parser.add_argument("--step-minutes", type=int, default=10)
    parser.add_argument("--minimum-days", type=int, default=5)
    parser.add_argument("--since", type=str, help="只分析此日期起的資料，格式 YYYY-MM-DD")
    parser.add_argument("--until", type=str, help="只分析到此日期，格式 YYYY-MM-DD")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logs, warnings = load_logs(args.data_dir)
    if args.since:
        logs = logs[logs["timestamp"] >= pd.Timestamp(args.since)]
    if args.until:
        logs = logs[logs["timestamp"] < pd.Timestamp(args.until) + pd.Timedelta(days=1)]
    if logs.empty:
        raise ValueError("指定日期範圍內沒有可用資料")
    windows = build_daily_windows(
        logs,
        threshold=args.threshold,
        step_minutes=args.step_minutes,
    )
    summary = summarize_windows(windows, minimum_days=args.minimum_days)

    for warning in warnings:
        print(f"警告：{warning}")
    print(format_recommendations(summary, args.threshold))


if __name__ == "__main__":
    main()
