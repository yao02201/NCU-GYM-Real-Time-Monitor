"""Shared configuration and parsing helpers for the NCU gym monitor."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup


PAGE_URL = "https://pe.ncu.edu.tw/about/66.html"
GYM_ROW_LABEL = "重訓室"
COMFORT_THRESHOLD = 30

# The published regular opening hours are 09:00-20:50. Temporary closures and
# holiday schedules still need to be handled separately when analysing data.
OPEN_TIME = time(9, 0)
CLOSE_TIME = time(20, 50)
TREND_LOOKBACK_MINUTES = 20
TREND_FLAT_THRESHOLD_PER_10_MIN = 1.5


class OccupancyStatus(str, Enum):
    VALID = "valid"
    UNAVAILABLE = "unavailable"
    OFFLINE = "offline"
    DATA_ERROR = "data_error"


@dataclass(frozen=True)
class OccupancyReading:
    status: OccupancyStatus
    count: int | None = None
    detail: str | None = None


class GymCountUnavailable(ValueError):
    """The official feed explicitly reports that the count is unavailable."""


def is_regular_open_time(moment: datetime) -> bool:
    """Return whether *moment* falls inside the regular gym opening window."""

    local_time = moment.time().replace(tzinfo=None)
    return OPEN_TIME <= local_time < CLOSE_TIME


def build_csv_url(page_html: str, page_url: str = PAGE_URL) -> str:
    """Extract the published Google Sheets CSV URL from the official page."""

    soup = BeautifulSoup(page_html, "html.parser")
    iframe_url = None

    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "").strip()
        if "docs.google.com/spreadsheets" in src and "/pubhtml" in src:
            iframe_url = urljoin(page_url, src)
            break

    if iframe_url is None:
        raise ValueError("找不到官方人數試算表 iframe")

    parsed = urlparse(iframe_url)
    query = parse_qs(parsed.query)
    params = {
        "output": "csv",
        "gid": query.get("gid", ["0"])[0],
        "range": query.get("range", ["A1:B10"])[0],
    }
    path = parsed.path.replace("/pubhtml", "/pub")
    return f"{parsed.scheme}://{parsed.netloc}{path}?{urlencode(params)}"


def parse_gym_count(csv_text: str) -> int:
    """Parse the weight-room count from the official two-column CSV."""

    for row in csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))):
        cells = [cell.strip() for cell in row]
        if len(cells) < 2 or cells[0] != GYM_ROW_LABEL:
            continue

        if cells[1].casefold() == "n/a":
            raise GymCountUnavailable("官方目前未提供重訓室人數")

        match = re.fullmatch(r"(\d+)\s*人?", cells[1])
        if not match:
            raise ValueError(f"重訓室人數格式無法辨識: {cells[1]!r}")

        count = int(match.group(1))
        if count > 500:
            raise ValueError(f"重訓室人數超出合理範圍: {count}")
        return count

    raise ValueError("CSV 中找不到重訓室人數")


def estimate_trend(
    points: list[tuple[datetime, int]],
    lookback_minutes: int = TREND_LOOKBACK_MINUTES,
    flat_threshold_per_10_min: float = TREND_FLAT_THRESHOLD_PER_10_MIN,
) -> tuple[str, float] | None:
    """Estimate recent direction using a least-squares slope.

    The returned rate is people per 10 minutes. Linear regression over a short
    window is less sensitive to one-minute counter noise than subtracting only
    the last two observations.
    """

    if len(points) < 2:
        return None

    ordered = sorted(points, key=lambda point: point[0])
    latest = ordered[-1][0]
    cutoff = latest - timedelta(minutes=lookback_minutes)
    recent = [(timestamp, count) for timestamp, count in ordered if timestamp >= cutoff]

    if len(recent) < 5:
        return None

    first_timestamp = recent[0][0]
    x_values = [
        (timestamp - first_timestamp).total_seconds() / 60 for timestamp, _ in recent
    ]
    if x_values[-1] < 5:
        return None

    y_values = [float(count) for _, count in recent]
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return None

    slope_per_minute = sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)
    ) / denominator
    rate_per_10_minutes = slope_per_minute * 10

    if rate_per_10_minutes > flat_threshold_per_10_min:
        direction = "rising"
    elif rate_per_10_minutes < -flat_threshold_per_10_min:
        direction = "falling"
    else:
        direction = "steady"

    return direction, rate_per_10_minutes
