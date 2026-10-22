"""Interactive historical dashboard for NCU gym occupancy logs."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from gym_analysis import WEEKDAY_NAMES, build_daily_windows, load_logs, summarize_windows
from gym_core import CLOSE_TIME, COMFORT_THRESHOLD, OPEN_TIME


matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei",
    "Noto Sans CJK TC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "gym_count"

CHART_TYPES = (
    "日期走勢（最近 7 天）",
    "星期平均走勢",
    "舒適機率熱圖",
    "每日平均與尖峰",
)


def filter_date_range(logs: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start_time = pd.Timestamp(start)
    end_time = pd.Timestamp(end) + pd.Timedelta(days=1)
    if start_time >= end_time:
        raise ValueError("開始日期不可晚於結束日期")
    return logs[(logs["timestamp"] >= start_time) & (logs["timestamp"] < end_time)].copy()


def filter_open_hours(logs: pd.DataFrame) -> pd.DataFrame:
    minute = logs["timestamp"].dt.hour * 60 + logs["timestamp"].dt.minute
    open_minute = OPEN_TIME.hour * 60 + OPEN_TIME.minute
    close_minute = CLOSE_TIME.hour * 60 + CLOSE_TIME.minute
    return logs[(minute >= open_minute) & (minute < close_minute)].copy()


class GymDashboard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("NCU Gym 歷史分析")
        self.root.geometry("1100x760")
        self.root.minsize(850, 620)

        self.logs, self.load_warnings = load_logs(DATA_DIR)
        self.logs = self.logs.sort_values("timestamp")
        self.available_dates = sorted(self.logs["timestamp"].dt.strftime("%Y-%m-%d").unique())
        if not self.available_dates:
            raise ValueError("沒有可選擇的歷史日期")

        self._refresh_job = None
        self.colorbar = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        controls = ttk.Frame(self.root, padding=(12, 10))
        controls.pack(fill="x")

        ttk.Label(controls, text="開始日期").grid(row=0, column=0, padx=(0, 5))
        self.start_var = tk.StringVar(value=self.available_dates[0])
        self.start_box = ttk.Combobox(
            controls,
            textvariable=self.start_var,
            values=self.available_dates,
            state="readonly",
            width=12,
        )
        self.start_box.grid(row=0, column=1, padx=(0, 12))

        ttk.Label(controls, text="結束日期").grid(row=0, column=2, padx=(0, 5))
        self.end_var = tk.StringVar(value=self.available_dates[-1])
        self.end_box = ttk.Combobox(
            controls,
            textvariable=self.end_var,
            values=self.available_dates,
            state="readonly",
            width=12,
        )
        self.end_box.grid(row=0, column=3, padx=(0, 12))

        ttk.Label(controls, text="圖表").grid(row=0, column=4, padx=(0, 5))
        self.chart_var = tk.StringVar(value=CHART_TYPES[0])
        self.chart_box = ttk.Combobox(
            controls,
            textvariable=self.chart_var,
            values=CHART_TYPES,
            state="readonly",
            width=22,
        )
        self.chart_box.grid(row=0, column=5, padx=(0, 12))

        ttk.Button(controls, text="重新整理", command=self.reload).grid(row=0, column=6, padx=4)
        ttk.Button(controls, text="匯出 PNG", command=self.export_png).grid(row=0, column=7, padx=4)
        controls.columnconfigure(8, weight=1)

        for box in (self.start_box, self.end_box, self.chart_box):
            box.bind("<<ComboboxSelected>>", self.schedule_refresh)

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        chart_frame = ttk.Frame(body)
        side_frame = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(chart_frame, weight=4)
        body.add(side_frame, weight=1)

        self.figure = Figure(figsize=(8, 6), dpi=100, constrained_layout=True)
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        toolbar = NavigationToolbar2Tk(self.canvas, chart_frame, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(fill="x")

        ttk.Label(side_frame, text="區間摘要", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.summary_var = tk.StringVar()
        ttk.Label(
            side_frame,
            textvariable=self.summary_var,
            justify="left",
            wraplength=240,
        ).pack(fill="x", pady=(6, 14))

        ttk.Label(side_frame, text="每週推薦", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.recommendation = tk.Text(
            side_frame,
            width=32,
            height=24,
            wrap="word",
            borderwidth=0,
            background=self.root.cget("background"),
            font=("Segoe UI", 9),
        )
        self.recommendation.pack(fill="both", expand=True, pady=(6, 0))
        self.recommendation.config(state="disabled")

        self.status_var = tk.StringVar(value="準備完成")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w").pack(
            fill="x", padx=12, pady=(0, 8)
        )

    def schedule_refresh(self, e=None):
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(200, self.refresh)

    def reload(self):
        self.logs, self.load_warnings = load_logs(DATA_DIR)
        self.logs = self.logs.sort_values("timestamp")
        self.available_dates = sorted(
            self.logs["timestamp"].dt.strftime("%Y-%m-%d").unique()
        )
        self.start_box.configure(values=self.available_dates)
        self.end_box.configure(values=self.available_dates)
        if self.start_var.get() not in self.available_dates:
            self.start_var.set(self.available_dates[0])
        if self.end_var.get() not in self.available_dates:
            self.end_var.set(self.available_dates[-1])
        self.refresh()

    def refresh(self):
        self._refresh_job = None
        try:
            selected = filter_date_range(self.logs, self.start_var.get(), self.end_var.get())
        except ValueError as exc:
            messagebox.showerror("日期範圍錯誤", str(exc), parent=self.root)
            return

        opening = filter_open_hours(selected)
        windows = build_daily_windows(selected, threshold=COMFORT_THRESHOLD)
        summary = summarize_windows(windows, minimum_days=1)
        self._update_summary(selected, opening, windows, summary)
        self._update_recommendations(summary)
        self._draw(opening, windows, summary)
        self.canvas.draw_idle()

    def _update_summary(self, selected, opening, windows, summary):
        dates = selected["timestamp"].dt.date.nunique()
        comfortable = float(windows["comfortable"].mean()) if not windows.empty else 0.0
        warnings = len(self.load_warnings)
        self.summary_var.set(
            f"日期：{self.start_var.get()} ～ {self.end_var.get()}\n"
            f"有資料天數：{dates}\n"
            f"營業時間資料：{len(opening):,} 筆\n"
            f"有效一小時視窗：{len(windows):,}\n"
            f"全部視窗舒適率：{comfortable:.0%}\n"
            f"讀取警告：{warnings}"
        )
        self.status_var.set(
            "分析已更新；推薦少於 5 個樣本日者僅供參考。"
        )

    def _update_recommendations(self, summary):
        lines = ["舒適＝60 分鐘內至少 90% 的觀測值 ≤ 30 人\n"]
        if summary.empty:
            lines.append("目前區間沒有足夠的完整一小時資料。")
        else:
            for row in summary[summary["rank"] == 1].itertuples(index=False):
                confidence = "" if row.sample_days >= 5 else "  ⚠ 樣本少"
                lines.append(
                    f"{row.weekday_name}  {row.start_time}\n"
                    f"  舒適率 {row.comfort_probability:.0%}｜"
                    f"平均 {row.average_count:.1f} 人｜n={row.sample_days}"
                    f"{confidence}\n"
                )

        self.recommendation.config(state="normal")
        self.recommendation.delete("1.0", "end")
        self.recommendation.insert("1.0", "\n".join(lines))
        self.recommendation.config(state="disabled")

    def _draw(self, opening, windows, summary):
        if self.colorbar is not None:
            self.colorbar.remove()
            self.colorbar = None
        self.axis.clear()
        chart_type = self.chart_var.get()
        if chart_type == CHART_TYPES[0]:
            self._draw_recent_days(opening)
        elif chart_type == CHART_TYPES[1]:
            self._draw_weekday_average(opening)
        elif chart_type == CHART_TYPES[2]:
            self._draw_comfort_heatmap(summary)
        else:
            self._draw_daily_summary(opening)
        self.axis.grid(True, alpha=0.2)

    def _draw_recent_days(self, opening):
        data = opening.copy()
        data["date"] = data["timestamp"].dt.date
        dates = sorted(data["date"].unique())[-7:]
        for date in dates:
            day = data[data["date"] == date].copy()
            day["minute"] = day["timestamp"].dt.hour * 60 + day["timestamp"].dt.minute
            curve = day.groupby("minute", as_index=False)["count"].mean()
            self.axis.plot(curve["minute"], curve["count"], linewidth=1.5, label=str(date))
        self._format_time_axis()
        self.axis.axhline(COMFORT_THRESHOLD, color="#16a34a", linestyle="--", label="30 人")
        self.axis.set_title("選取區間最近 7 個有資料日的人數走勢")
        self.axis.set_ylabel("人數")
        if dates:
            self.axis.legend(fontsize=8, ncol=2)

    def _draw_weekday_average(self, opening):
        data = opening.copy()
        data["date"] = data["timestamp"].dt.date
        data["weekday"] = data["timestamp"].dt.dayofweek
        data["minute"] = (
            (data["timestamp"].dt.hour * 60 + data["timestamp"].dt.minute) // 10 * 10
        )
        daily = data.groupby(["date", "weekday", "minute"], as_index=False)["count"].mean()
        weekly = daily.groupby(["weekday", "minute"], as_index=False)["count"].mean()
        for weekday in range(7):
            curve = weekly[weekly["weekday"] == weekday]
            if not curve.empty:
                self.axis.plot(curve["minute"], curve["count"], linewidth=2, label=WEEKDAY_NAMES[weekday])
        self._format_time_axis()
        self.axis.axhline(COMFORT_THRESHOLD, color="#16a34a", linestyle="--", label="30 人")
        self.axis.set_title("各星期的 10 分鐘平均走勢（每天等權）")
        self.axis.set_ylabel("平均人數")
        self.axis.legend(fontsize=8, ncol=2)

    def _draw_comfort_heatmap(self, summary):
        if summary.empty:
            self.axis.text(0.5, 0.5, "沒有有效的一小時視窗", ha="center", va="center")
            return
        pivot = summary.pivot(index="weekday", columns="start_minute", values="comfort_probability")
        pivot = pivot.reindex(range(7))
        image = self.axis.imshow(pivot, aspect="auto", vmin=0, vmax=1, cmap="RdYlGn")
        starts = list(pivot.columns)
        tick_indexes = list(range(0, len(starts), 6))
        self.axis.set_xticks(tick_indexes)
        self.axis.set_xticklabels(
            [f"{starts[i] // 60:02d}:{starts[i] % 60:02d}" for i in tick_indexes],
            rotation=45,
            ha="right",
        )
        self.axis.set_yticks(range(7))
        self.axis.set_yticklabels([WEEKDAY_NAMES[i] for i in range(7)])
        self.axis.set_title("一小時舒適成功率熱圖")
        self.colorbar = self.figure.colorbar(
            image,
            ax=self.axis,
            label="舒適機率",
            fraction=0.035,
            pad=0.02,
        )

    def _draw_daily_summary(self, opening):
        data = opening.copy()
        data["date"] = data["timestamp"].dt.date
        daily = data.groupby("date")["count"].agg(
            average="mean",
            p90=lambda values: values.quantile(0.9),
        )
        self.axis.plot(daily.index, daily["average"], marker="o", markersize=3, label="每日平均")
        self.axis.plot(daily.index, daily["p90"], linewidth=1.5, label="每日 P90")
        self.axis.axhline(COMFORT_THRESHOLD, color="#16a34a", linestyle="--", label="30 人")
        self.axis.set_title("每日平均與第 90 百分位人數")
        self.axis.set_ylabel("人數")
        self.axis.tick_params(axis="x", rotation=45)
        self.axis.legend()

    def _format_time_axis(self):
        ticks = list(range(9 * 60, 21 * 60, 60))
        self.axis.set_xlim(9 * 60, 20 * 60 + 50)
        self.axis.set_xticks(ticks)
        self.axis.set_xticklabels([f"{minute // 60:02d}:00" for minute in ticks], rotation=45)
        self.axis.set_xlabel("時間")

    def export_png(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="匯出圖表",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
        )
        if path:
            self.figure.savefig(path, dpi=160, bbox_inches="tight")
            self.status_var.set(f"已匯出：{path}")


def main():
    root = tk.Tk()
    try:
        GymDashboard(root)
    except Exception as exc:
        root.withdraw()
        messagebox.showerror("無法啟動歷史分析", str(exc), parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
