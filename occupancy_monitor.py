"""Occupancy status and refresh-cycle behavior for the desktop Widget."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import parse_qs, urljoin, urlparse


@dataclass(frozen=True)
class WidgetPresentation:
    primary_text: str
    secondary_text: str | None
    theme: str
    gif_key: str | None
    blink: bool


class OccupancyStatus(Enum):
    VALID = "valid"
    UNAVAILABLE = "unavailable"
    OFFLINE = "offline"
    DATA_ERROR = "data-error"


@dataclass(frozen=True)
class OccupancyReading:
    status: OccupancyStatus
    count: int | None = None

    @classmethod
    def valid(cls, count: int) -> "OccupancyReading":
        if count < 0:
            raise ValueError("A Valid reading must be a non-negative integer")
        return cls(OccupancyStatus.VALID, count)

    @classmethod
    def unavailable(cls) -> "OccupancyReading":
        return cls(OccupancyStatus.UNAVAILABLE)

    @classmethod
    def offline(cls) -> "OccupancyReading":
        return cls(OccupancyStatus.OFFLINE)

    @classmethod
    def data_error(cls) -> "OccupancyReading":
        return cls(OccupancyStatus.DATA_ERROR)


class HttpResponse(Protocol):
    text: str
    content: bytes

    def raise_for_status(self) -> None: ...


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> HttpResponse: ...


class SourceOfflineError(Exception):
    """Raised by an HTTP adapter when the occupancy source is unreachable."""


class _IframeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.source: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "iframe" or self.source is not None:
            return
        self.source = dict(attrs).get("src")


class NcuOccupancySource:
    PAGE_URL = "https://pe.ncu.edu.tw/about/66.html"
    TARGET_ROW = "重訓室"

    def __init__(self, *, http_client: HttpClient) -> None:
        self._http_client = http_client
        self._csv_url: str | None = None

    def read(self) -> OccupancyReading:
        try:
            return self._read_reachable_source()
        except (SourceOfflineError, TimeoutError, ConnectionError):
            return OccupancyReading.offline()
        except Exception:
            return OccupancyReading.data_error()

    def _read_reachable_source(self) -> OccupancyReading:
        csv_url = self._csv_url or self._discover_csv_url()
        response = self._http_client.get(
            csv_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()

        reader = csv.reader(io.StringIO(response.content.decode("utf-8")))
        for row in reader:
            cells = [cell.strip() for cell in row]
            if not any(self.TARGET_ROW in cell for cell in cells):
                continue
            if any(cell.casefold() == "n/a" for cell in cells):
                return OccupancyReading.unavailable()
            for cell in cells:
                match = re.fullmatch(r"([0-9]+)\s*人?", cell)
                if match:
                    return OccupancyReading.valid(int(match.group(1)))
            raise ValueError("The gym row has no supported occupancy value")
        raise ValueError("The occupancy feed has no gym row")

    def _discover_csv_url(self) -> str:
        response = self._http_client.get(
            self.PAGE_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()

        parser = _IframeParser()
        parser.feed(response.text)
        if not parser.source:
            raise ValueError("The NCU page has no occupancy feed")

        iframe_url = urljoin(self.PAGE_URL, parser.source)
        parsed = urlparse(iframe_url)
        query = parse_qs(parsed.query)
        path = parsed.path.replace("/pubhtml", "/pub")
        gid = query.get("gid", ["0"])[0]
        cell_range = query.get("range", ["A1:B10"])[0]
        self._csv_url = (
            f"{parsed.scheme}://{parsed.netloc}{path}"
            f"?output=csv&gid={gid}&range={cell_range}"
        )
        return self._csv_url


class OccupancySource(Protocol):
    def read(self) -> OccupancyReading: ...


class WidgetView(Protocol):
    def render(self, presentation: WidgetPresentation) -> None: ...


class OccupancyLogger(Protocol):
    def record(self, count: int) -> None: ...


class CsvOccupancyLogger:
    def __init__(
        self,
        log_directory: Path,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._log_directory = log_directory
        self._now = now
        self._last_logged_at: datetime | None = None

    def record(self, count: int) -> None:
        current_time = self._now()
        if self._last_logged_at is not None:
            elapsed = (current_time - self._last_logged_at).total_seconds()
            if elapsed < 60:
                return

        self._log_directory.mkdir(parents=True, exist_ok=True)
        log_file = self._log_directory / (
            f"gym_count_{current_time.strftime('%Y-%m-%d')}.csv"
        )
        new_file = not log_file.exists()
        with log_file.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if new_file:
                writer.writerow(["timestamp", "count"])
            writer.writerow([current_time.strftime("%Y-%m-%d %H:%M:%S"), count])
        self._last_logged_at = current_time


class Scheduler(Protocol):
    def call_later(self, delay_ms: int, callback: Callable[[], None]) -> None: ...


class OccupancyMonitor:
    """Run user-visible refresh cycles through one application-level seam."""

    def __init__(
        self,
        *,
        source: OccupancySource,
        view: WidgetView,
        logger: OccupancyLogger,
        scheduler: Scheduler,
    ) -> None:
        self._source = source
        self._view = view
        self._logger = logger
        self._scheduler = scheduler

    def start(self) -> None:
        self._view.render(
            WidgetPresentation(
                primary_text="Loading...",
                secondary_text=None,
                theme="neutral",
                gif_key=None,
                blink=False,
            )
        )
        self._scheduler.call_later(0, self.refresh)

    def refresh(self) -> None:
        try:
            reading = self._source.read()
        except Exception:
            reading = OccupancyReading.data_error()
        count = reading.count

        if reading.status is OccupancyStatus.UNAVAILABLE:
            self._view.render(
                WidgetPresentation(
                    primary_text="N/A",
                    secondary_text=None,
                    theme="neutral",
                    gif_key=None,
                    blink=False,
                )
            )
            self._scheduler.call_later(10_000, self.refresh)
            return

        if reading.status is OccupancyStatus.OFFLINE:
            self._view.render(
                WidgetPresentation(
                    primary_text="Offline",
                    secondary_text=None,
                    theme="offline",
                    gif_key=None,
                    blink=False,
                )
            )
            self._scheduler.call_later(10_000, self.refresh)
            return

        if reading.status is OccupancyStatus.DATA_ERROR:
            self._view.render(
                WidgetPresentation(
                    primary_text="Error",
                    secondary_text="Restart if this persists",
                    theme="data-error",
                    gif_key=None,
                    blink=False,
                )
            )
            self._scheduler.call_later(10_000, self.refresh)
            return

        if reading.status is not OccupancyStatus.VALID or count is None:
            raise ValueError("Unsupported occupancy status")

        if count < 35:
            theme = "low"
            gif_key = "low"
        elif count <= 45:
            theme = "medium"
            gif_key = "mid"
        else:
            theme = "high"
            gif_key = "high"

        try:
            self._logger.record(count)
        except Exception:
            self._view.render(
                WidgetPresentation(
                    primary_text="Error",
                    secondary_text="Restart if this persists",
                    theme="data-error",
                    gif_key=None,
                    blink=False,
                )
            )
            self._scheduler.call_later(10_000, self.refresh)
            return
        self._view.render(
            WidgetPresentation(
                primary_text=str(count),
                secondary_text=None,
                theme=theme,
                gif_key=gif_key,
                blink=count < 25,
            )
        )
        self._scheduler.call_later(10_000, self.refresh)
