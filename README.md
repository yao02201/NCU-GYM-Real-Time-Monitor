# NCU GYM Real-Time Monitor

A Windows desktop widget and interactive dashboard for the National Central
University gym. It shows the live weight-room count, records opening-hour
history, visualizes crowd patterns, and recommends comfortable one-hour slots.

The project is designed to answer one practical question: **when can I train
for an hour without walking into a crowded gym?**

## Features

- Live weight-room count from the [NCU PE Office](https://pe.ncu.edu.tw/about/66.html)
- Responsive, draggable, always-on-top desktop widget
- Resize from any edge or corner:
  - compact: current count only
  - normal: count, GIF, recent trend, and crowd status
  - expanded: today's occupancy chart and the 30-person comfort line
- Latest observation time shown directly on the daily chart
- Recent trend estimated from a 20-minute linear slope
- Three persistent visual themes selectable from the widget header
- Optional Windows per-user auto-start from the right-click menu
- Interactive historical dashboard with selectable date ranges
- Quality-checked one-hour recommendation analysis

The regular published gym hours are 09:00-20:50. Temporary closures and
holiday schedules are still subject to official announcements.

## Comfort definition

```text
At least 90% of observations in a continuous 60-minute window are <= 30 people.
```

Recommendations prioritize the probability of satisfying this rule, followed
by the 90th-percentile and average crowd levels. A low average alone can hide a
crowded part of the workout.

## Quick start

```bash
git clone https://github.com/yao02201/NCU-GYM-Real-Time-Monitor.git
cd NCU-GYM-Real-Time-Monitor
python -m pip install -r requirements.txt
python gym.py
```

On Windows, `gym.pyw` starts the same widget without a console window.

Widget controls:

- drag the content to move the widget
- drag any edge or corner to resize it
- click one of the three color circles to switch between visual themes
- press `Esc` to close it
- right-click to open historical analysis, toggle auto-start, or exit

## Interactive historical dashboard

Open it from the widget's right-click menu or run:

```bash
python gym_dashboard.py
```

The dashboard provides:

- existing-date selectors for the start and end of the analysis period
- recent daily curves
- equal-weight weekday average curves
- a comfortable-hour probability heatmap
- daily average and 90th-percentile trends
- best one-hour recommendation for every weekday
- sample counts, data-quality warnings, zoom/pan, and PNG export

## Command-line analysis

Analyze all available logs:

```bash
python gym_analysis.py
```

Analyze a semester or another date range:

```bash
python gym_analysis.py --since 2026-09-01 --until 2027-01-31
```

Useful options:

```text
--threshold 30       Comfortable count threshold
--step-minutes 10    Candidate start-time interval
--minimum-days 5     Minimum valid days before recommending a window
```

An hourly window is excluded if it has too few samples, starts or ends too far
from the requested boundaries, or contains a gap longer than five minutes.

## Trend calculation

The trend indicator uses least-squares regression over the latest 20 minutes,
instead of subtracting only the latest two readings. This reduces one-minute
counter noise. A change within ±1.5 people per 10 minutes is shown as steady.

## Project structure

```text
.
├── gym.py                 # Responsive live widget
├── gym.pyw                # Windowless Windows launcher
├── gym_core.py            # Shared thresholds, parser, and trend calculation
├── gym_analysis.py        # 60-minute recommendation analysis
├── gym_dashboard.py       # Interactive historical charts
├── gym_statistic.ipynb    # Exploratory notebook
├── requirements.txt
├── gif/                   # Widget animations
├── gym_count/             # Local daily CSV logs
└── tests/                 # Unit tests
```

Run tests with:

```bash
python -m unittest discover -s tests -v
```

---

## 中文說明

這是一個中央大學健身房即時人數桌面小工具。除了顯示目前重訓室人數，也會記錄
營業時間內的歷史資料、顯示當日折線圖、判斷近期人數趨勢，並分析比較舒服的
一小時。核心目標是找出一天之中適合連續健身一小時、且大多數時間不超過 30 人
的時段，減少白跑或在人潮尖峰等待器材的情況。

### 視窗操作

- 拖曳視窗內容可移動位置。
- 拖曳任一邊框或角落可調整大小。
- 點選上方三個無邊框色點，可切換莫蘭迪玫瑰、奶油小花與櫻花粉霧。
- 縮到最小時只顯示目前人數。
- 放大後會依序顯示 GIF、最近趨勢、人數狀態與當日折線圖；最新資料時間會標在折線圖上。
- 按 `Esc` 關閉。
- 按滑鼠右鍵可開啟歷史分析、切換開機自啟或結束程式。

開機自啟使用 Windows 使用者層級設定，不需要系統管理員權限，也能隨時從右鍵
選單取消。

### 互動式歷史分析

執行 `python gym_dashboard.py`，或從 Widget 的右鍵選單開啟。可以選擇開始與結束
日期，程式會自動重新統計並切換以下圖表：

- 最近七個有資料日的人數曲線
- 各星期平均走勢
- 舒適時段成功率熱圖
- 每日平均與第 90 百分位趨勢

介面也會顯示各星期最佳一小時、舒適成功率、平均人數和樣本天數，並可縮放、
平移或匯出 PNG。

### 舒適時段定義

```text
連續 60 分鐘內，至少 90% 的觀測值不超過 30 人。
```

分析會排除資料量不足、邊界缺漏或中斷超過五分鐘的時段，再依舒適成功率、第
90 百分位人數與平均人數排序。

### 人數趨勢

趨勢不是只比較相鄰兩筆資料，而是對最近 20 分鐘做線性迴歸，取得近似的一次微分
斜率。每 10 分鐘變化在 ±1.5 人內顯示為持平，避免計數的小幅抖動讓箭頭反覆切換。

### 注意事項

- 官方例行開放時間目前為 09:00-20:50，臨時休館與假日時段仍以體育室公告為準。
- 新產生的 CSV 預設只保留在本機，不會被 Git 自動提交。
- 歷史推薦最好依學期、寒暑假或指定日期區間分開分析。
