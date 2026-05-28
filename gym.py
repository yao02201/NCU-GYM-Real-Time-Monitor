### Real-Time Gym Monitor
## most of the coding is by ChatGPT
## you can customize the color boundary, GIFs in different states, and when the numbers start blinking
## when people are less than 35 -> green
## between 35 and 45 -> orange
## larger than 45 -> red
## less than 25 -> the numbers blink, which means GO to GYM!

import csv
import io
import os
import requests
import tkinter as tk
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from PIL import Image, ImageTk, ImageSequence


# ===== Paths =====
# Use the folder where this .py/.pyw file is located as the base directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

GIF_DIR = os.path.join(BASE_DIR, "gif")
LOG_DIR = os.path.join(BASE_DIR, "gym_count")


# ===== Settings =====
PAGE_URL = "https://pe.ncu.edu.tw/about/66.html"
REFRESH_MS = 10_000          # UI refresh every 10 sec
LOG_INTERVAL_MS = 60_000     # save one point every 60 sec
BLINK_MS = 450
GIF_SIZE = (110, 110)

GIF_FILES = {
    "low": os.path.join(GIF_DIR, "gymtime.gif"),
    "mid": os.path.join(GIF_DIR, "blueguy.gif"),
    "high": os.path.join(GIF_DIR, "usingcomputer.gif")
}

state = {
    "csv_url": None,
    "count": None,
    "gif_key": "mid",
    "gif_index": 0,
    "blink_on": True,
    "drag_x": 0,
    "drag_y": 0,
    "gif_sets": {},
    "fg": "#111827",
    "bg_card": "#ffffff",
    "last_logged_at": None
}


# ===== Logging =====
def init_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def get_today_log_file():
    today_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"gym_count_{today_str}.csv")


def ensure_log_file():
    log_file = get_today_log_file()

    if not os.path.exists(log_file):
        with open(log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "count"])

    return log_file


def should_log_now():
    now = datetime.now()

    if state["last_logged_at"] is None:
        state["last_logged_at"] = now
        return True

    elapsed = (now - state["last_logged_at"]).total_seconds()

    if elapsed >= LOG_INTERVAL_MS / 1000:
        state["last_logged_at"] = now
        return True

    return False


def append_log(count):
    if count is None:
        return

    if not should_log_now():
        return

    log_file = ensure_log_file()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, count])


# ===== Data Fetching =====
def get_csv_url():
    if state["csv_url"]:
        return state["csv_url"]

    try:
        r = requests.get(
            PAGE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        iframe = soup.find("iframe")

        if not iframe:
            return None

        iframe_url = urljoin(PAGE_URL, iframe.get("src"))

        parsed = urlparse(iframe_url)
        path = parsed.path.replace("/pubhtml", "/pub")
        qs = parse_qs(parsed.query)

        gid = qs.get("gid", ["0"])[0]
        rng = qs.get("range", ["A1:B10"])[0]

        state["csv_url"] = (
            f"{parsed.scheme}://{parsed.netloc}{path}"
            f"?output=csv&gid={gid}&range={rng}"
        )

        return state["csv_url"]

    except Exception as e:
        print("取得 CSV URL 失敗:", e)
        return None


def fetch_count():
    try:
        csv_url = get_csv_url()

        if not csv_url:
            return None

        r = requests.get(
            csv_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        r.raise_for_status()

        reader = csv.reader(io.StringIO(r.content.decode("utf-8")))

        for row in reader:
            row = [c.strip() for c in row]

            if any("重訓室" in c for c in row):
                for c in row:
                    c = c.replace("人", "").strip()

                    if c.isdigit():
                        return int(c)

        return None

    except Exception as e:
        print("fetch_count 錯誤:", e)
        return None


# ===== GIF =====
def load_gif(path):
    if not os.path.exists(path):
        print("缺少 GIF:", path)
        return [], []

    frames, delays = [], []

    try:
        img = Image.open(path)

        for frame in ImageSequence.Iterator(img):
            delay = frame.info.get("duration", 100) or 100

            frame = frame.convert("RGBA")
            frame.thumbnail(GIF_SIZE)

            frames.append(ImageTk.PhotoImage(frame))
            delays.append(delay)

    except Exception as e:
        print(f"載入 GIF 失敗 {path}:", e)

    return frames, delays


def load_all_gifs():
    state["gif_sets"] = {
        key: load_gif(path)
        for key, path in GIF_FILES.items()
    }


def select_gif_key(count):
    if count is None:
        return "mid"

    if count < 35:
        return "low"

    if count <= 45:
        return "mid"

    return "high"


def animate_gif():
    frames, delays = state["gif_sets"].get(state["gif_key"], ([], []))

    if not frames:
        root.after(300, animate_gif)
        return

    i = state["gif_index"]

    gif_label.config(image=frames[i])
    state["gif_index"] = (i + 1) % len(frames)

    root.after(delays[i], animate_gif)


# ===== Theme =====
def get_theme(n):
    if n is None:
        return "#f3f4f6", "#ffffff", "#111827", "#6b7280", "#d1d5db"

    if n < 35:
        return "#dcfce7", "#bbf7d0", "#14532d", "#166534", "#16a34a"

    if n <= 45:
        return "#ffedd5", "#fed7aa", "#7c2d12", "#9a3412", "#f59e0b"

    return "#fee2e2", "#fecaca", "#7f1d1d", "#991b1b", "#dc2626"


def apply_theme(n):
    bg_main, bg_card, fg, fg_muted, border = get_theme(n)

    root.configure(bg=bg_main)
    outer.config(bg=bg_main)

    for widget in (card, top, content, gif_label, count_label):
        widget.config(bg=bg_card)

    card.config(
        highlightbackground=border,
        highlightcolor=border
    )

    title.config(bg=bg_card, fg=fg_muted)
    close_btn.config(bg=bg_card, fg=fg_muted)
    count_label.config(bg=bg_card, fg=fg)

    state["fg"] = fg
    state["bg_card"] = bg_card


# ===== UI Update =====
def refresh_data():
    n = fetch_count()

    state["count"] = n
    state["blink_on"] = True

    apply_theme(n)

    if n is None:
        count_var.set("Error")
    else:
        count_var.set(str(n))
        append_log(n)

        new_key = select_gif_key(n)

        if new_key != state["gif_key"]:
            state["gif_key"] = new_key
            state["gif_index"] = 0

    root.after(REFRESH_MS, refresh_data)


def blink_loop():
    n = state["count"]

    if n is not None and n < 25:
        state["blink_on"] = not state["blink_on"]
        count_label.config(
            fg=state["fg"] if state["blink_on"] else state["bg_card"]
        )
    else:
        count_label.config(fg=state["fg"])

    root.after(BLINK_MS, blink_loop)


# ===== Drag =====
def start_drag(e):
    state["drag_x"] = e.x_root - root.winfo_x()
    state["drag_y"] = e.y_root - root.winfo_y()


def on_drag(e):
    root.geometry(
        f"+{e.x_root - state['drag_x']}+{e.y_root - state['drag_y']}"
    )


def close_app(e=None):
    root.destroy()


# ===== UI =====
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.geometry("300x150+100+100")

outer = tk.Frame(root)
outer.pack(fill="both", expand=True, padx=8, pady=8)

card = tk.Frame(outer, highlightthickness=1)
card.pack(fill="both", expand=True)

top = tk.Frame(card)
top.pack(fill="x", padx=12, pady=(10, 0))

title = tk.Label(
    top,
    text="NCU GYM Real-Time Monitor",
    font=("Segoe UI", 12, "bold")
)
title.pack(side="left")

close_btn = tk.Label(
    top,
    text="✕",
    cursor="hand2",
    font=("Segoe UI", 10, "bold")
)
close_btn.pack(side="right")

content = tk.Frame(card)
content.pack(fill="both", expand=True, padx=14, pady=(8, 12))

gif_label = tk.Label(content)
gif_label.pack(side="left", padx=(0, 12))

count_var = tk.StringVar(value="Loading...")
count_label = tk.Label(
    content,
    textvariable=count_var,
    font=("Segoe UI", 37, "bold")
)
count_label.pack(side="left")

for widget in (outer, card, top, title, content, gif_label, count_label):
    widget.bind("<Button-1>", start_drag)
    widget.bind("<B1-Motion>", on_drag)

close_btn.bind("<Button-1>", close_app)
root.bind("<Escape>", close_app)


# ===== Start App =====
init_log_dir()
load_all_gifs()
apply_theme(None)
animate_gif()
refresh_data()
blink_loop()

root.mainloop()