# NCU GYM Real-Time Monitor

**Find a quieter hour. Spend less time waiting for equipment.**

A Windows desktop widget for National Central University's weight room: live occupancy, animated reactions, today's crowd curve, and a historical dashboard to help choose your next workout time.

## Preview

<table>
  <tr>
    <td align="center"><img src="for_git_intro/widget_current.png" width="360" alt="Midnight Monitor dark theme"><br><b>Midnight Monitor</b></td>
    <td align="center"><img src="for_git_intro/widget_morandi.png" width="360" alt="Morandi Violet theme"><br><b>Morandi Violet</b></td>
  </tr>
</table>

*Actual application screenshots with demo occupancy data. The widget UI is in English; the history dashboard is currently in Traditional Chinese.*

## What it does

- Live count, crowd status, GIFs, and recent change in `people / 10 min`.
- Drag across monitors, resize to a count-only view, or expand for today's chart.
- Four themes—Morandi Violet, Botanical Cream, Cherry Blush, and Midnight Monitor—plus always-on-top mode and optional Windows startup.
- Date-range analysis, weekday curves, comfort heatmap, and PNG export.

| Occupancy | Widget status | Animation folder |
|---|---|---|
| ≤30 people | `Gym time!` | `gif/low/` |
| 31–45 people | `fuwaa` | `gif/mid/` |
| ≥46 people | `Stay in lab` | `gif/high/` |
| No current reading | `No data` / connection status | `gif/close/` |

Add your GIFs or images to these folders. Each file plays for **10 seconds**, then the next one plays; the category loops until the occupancy changes.

## Historical results

![Weekday average occupancy](for_git_intro/weekday_average.png)

Ten-minute weekday averages with equal weight per day. The dashed line marks 30 people.

![Probability of a comfortable one-hour workout](for_git_intro/comfort_heatmap.png)

Greener slots more often met the comfort rule; stars mark the best observed start time per weekday. These are historical examples, not live forecasts; low-sample slots are less reliable.

**Comfort rule:** at least 90% of readings in a continuous 60-minute window are ≤30 people. Incomplete windows and gaps longer than five minutes are excluded.

## Get started

Requires **Windows and Python 3.10+** with Tkinter. Tested locally with Python 3.13.

```powershell
git clone https://github.com/yao02201/NCU-GYM-Real-Time-Monitor.git
cd NCU-GYM-Real-Time-Monitor
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe gym.pyw
```

To see console output, run `.\.venv\Scripts\python.exe gym.py` instead. Keep this project folder in place after enabling launch at startup.

**Controls:** drag the content to move · drag an edge to resize · click a color dot to change theme · right-click for history, startup, and exit · `Esc` to close.

Open the history dashboard separately:

```powershell
.\.venv\Scripts\python.exe gym_dashboard.py
```

<details>
<summary>Development and customization</summary>

```powershell
python -m unittest discover -s tests -v
python gym_analysis.py --since 2026-03-21 --until 2026-04-10
python tools/preview_widget.py --theme midnight_monitor
```

The preview uses demo data and does not fetch readings or alter your normal widget settings. `F1`–`F4` switch themes; `F5`–`F7` show compact, normal, and expanded layouts.

```text
gym.py / gym.pyw       Desktop widget and windowless launcher
gym_core.py           Feed parser and trend calculation
gym_analysis.py        One-hour analysis
gym_dashboard.py       Interactive historical dashboard
widget_window.py       Resizing and multi-monitor behavior
monitor_instance.py    Single-instance guard
gif/                   low / mid / high / close animations
gym_count/             Daily CSV logs and existing historical samples
tests/                 Automated checks
```

New CSV logs, virtual environments, and Python caches are ignored by Git. Window and theme preferences are stored under `%LOCALAPPDATA%\NCUGymMonitor`.

</details>

Data comes from the [NCU PE Office](https://pe.ncu.edu.tw/about/66.html). This is an independent student project. Opening-hour filtering currently uses 09:00–20:50; temporary closures follow official announcements. GIFs and character artwork belong to their respective creators.

---

## 中文簡介

中央大學健身房即時人數小工具，幫你找到比較舒服的一小時。可自由拖移、縮放、切換四種主題，並顯示當日折線與近期趨勢；右鍵可開啟日期區間分析或設定開機啟動。

- **≤30 人**：`Gym time!`；**31–45 人**：`fuwaa`；**≥46 人**：`Stay in lab`。
- 舒適時段＝連續 60 分鐘內，至少 90% 的紀錄不超過 30 人。
- 動畫依 `gif/low`、`mid`、`high`、`close` 分類，每個播放 10 秒。
- 上方展示圖使用示範資料；統計圖為歷史結果，可在 Dashboard 選日期重新分析。

安裝與操作請見上方 **Get started**。新的人數紀錄只存在本機，不會自動上傳。
