from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from occupancy_monitor import (
    CsvOccupancyLogger,
    NcuOccupancySource,
    OccupancyMonitor,
    OccupancyReading,
    WidgetPresentation,
)


class RecordingView:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    def render(self, presentation: WidgetPresentation) -> None:
        self.events.append(("render", presentation))


class RecordingScheduler:
    def __init__(self, events: list[object]) -> None:
        self.events = events

    def call_later(self, delay_ms: int, callback: object) -> None:
        self.events.append(("schedule", delay_ms, callback))


class UnexpectedSource:
    def read(self) -> object:
        raise AssertionError("Loading must render before the first source attempt")


class FailingSource:
    def read(self) -> object:
        raise RuntimeError("unexpected refresh failure")


class UnexpectedLogger:
    def record(self, count: int) -> None:
        raise AssertionError("Loading must not write an occupancy record")


class FixedSource:
    def __init__(self, reading: OccupancyReading) -> None:
        self.reading = reading

    def read(self) -> OccupancyReading:
        return self.reading


class SequenceSource:
    def __init__(self, *readings: OccupancyReading) -> None:
        self.readings = list(readings)

    def read(self) -> OccupancyReading:
        return self.readings.pop(0)


class ControlledClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


class RecordingLogger:
    def __init__(self) -> None:
        self.counts: list[int] = []

    def record(self, count: int) -> None:
        self.counts.append(count)


class FailingLogger:
    def record(self, count: int) -> None:
        raise OSError("occupancy log is unavailable")


class HttpResponse:
    def __init__(self, body: str) -> None:
        self.text = body
        self.content = body.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


class ScriptedHttpClient:
    def __init__(self, *responses: HttpResponse | Exception) -> None:
        self.responses = list(responses)

    def get(self, url: str, **kwargs: object) -> HttpResponse:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class OfflineHttpClient:
    def get(self, url: str, **kwargs: object) -> HttpResponse:
        raise TimeoutError("source timed out")


class OccupancyMonitorTests(unittest.TestCase):
    def test_start_shows_loading_before_the_first_source_attempt(self) -> None:
        events: list[object] = []
        monitor = OccupancyMonitor(
            source=UnexpectedSource(),
            view=RecordingView(events),
            logger=UnexpectedLogger(),
            scheduler=RecordingScheduler(events),
        )

        monitor.start()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="Loading...",
                        secondary_text=None,
                        theme="neutral",
                        gif_key=None,
                        blink=False,
                    ),
                ),
                ("schedule", 0, monitor.refresh),
            ],
        )

    def test_valid_reading_updates_the_widget_logs_and_refreshes_again(self) -> None:
        events: list[object] = []
        logger = RecordingLogger()
        monitor = OccupancyMonitor(
            source=FixedSource(OccupancyReading.valid(24)),
            view=RecordingView(events),
            logger=logger,
            scheduler=RecordingScheduler(events),
        )

        monitor.refresh()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="24",
                        secondary_text=None,
                        theme="low",
                        gif_key="low",
                        blink=True,
                    ),
                ),
                ("schedule", 10_000, monitor.refresh),
            ],
        )
        self.assertEqual(logger.counts, [24])

    def test_explicit_na_is_an_unavailable_reading_not_an_error(self) -> None:
        events: list[object] = []
        logger = RecordingLogger()
        source = NcuOccupancySource(
            http_client=ScriptedHttpClient(
                HttpResponse(
                    '<iframe src="https://docs.google.com/spreadsheets/d/e/x/'
                    'pubhtml?gid=0&amp;range=A1%3AB10"></iframe>'
                ),
                HttpResponse("重訓室,  n/A  \n"),
            )
        )
        monitor = OccupancyMonitor(
            source=source,
            view=RecordingView(events),
            logger=logger,
            scheduler=RecordingScheduler(events),
        )

        monitor.refresh()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="N/A",
                        secondary_text=None,
                        theme="neutral",
                        gif_key=None,
                        blink=False,
                    ),
                ),
                ("schedule", 10_000, monitor.refresh),
            ],
        )
        self.assertEqual(logger.counts, [])

    def test_supported_source_count_is_a_valid_reading(self) -> None:
        events: list[object] = []
        logger = RecordingLogger()
        source = NcuOccupancySource(
            http_client=ScriptedHttpClient(
                HttpResponse(
                    '<iframe src="https://docs.google.com/spreadsheets/d/e/x/'
                    'pubhtml?gid=0&amp;range=A1%3AB10"></iframe>'
                ),
                HttpResponse("重訓室,   25   人  \n"),
            )
        )
        monitor = OccupancyMonitor(
            source=source,
            view=RecordingView(events),
            logger=logger,
            scheduler=RecordingScheduler(events),
        )

        monitor.refresh()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="25",
                        secondary_text=None,
                        theme="low",
                        gif_key="low",
                        blink=False,
                    ),
                ),
                ("schedule", 10_000, monitor.refresh),
            ],
        )
        self.assertEqual(logger.counts, [25])

    def test_source_timeout_is_offline_and_keeps_refreshing(self) -> None:
        events: list[object] = []
        logger = RecordingLogger()
        monitor = OccupancyMonitor(
            source=NcuOccupancySource(http_client=OfflineHttpClient()),
            view=RecordingView(events),
            logger=logger,
            scheduler=RecordingScheduler(events),
        )

        monitor.refresh()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="Offline",
                        secondary_text=None,
                        theme="offline",
                        gif_key=None,
                        blink=False,
                    ),
                ),
                ("schedule", 10_000, monitor.refresh),
            ],
        )
        self.assertEqual(logger.counts, [])

    def test_reachable_unsupported_value_is_a_data_error(self) -> None:
        events: list[object] = []
        logger = RecordingLogger()
        source = NcuOccupancySource(
            http_client=ScriptedHttpClient(
                HttpResponse(
                    '<iframe src="https://docs.google.com/spreadsheets/d/e/x/'
                    'pubhtml?gid=0&amp;range=A1%3AB10"></iframe>'
                ),
                HttpResponse("重訓室,25.0\n"),
            )
        )
        monitor = OccupancyMonitor(
            source=source,
            view=RecordingView(events),
            logger=logger,
            scheduler=RecordingScheduler(events),
        )

        monitor.refresh()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="Error",
                        secondary_text="Restart if this persists",
                        theme="data-error",
                        gif_key=None,
                        blink=False,
                    ),
                ),
                ("schedule", 10_000, monitor.refresh),
            ],
        )
        self.assertEqual(logger.counts, [])

    def test_unexpected_refresh_failure_is_a_retrying_data_error(self) -> None:
        events: list[object] = []
        logger = RecordingLogger()
        monitor = OccupancyMonitor(
            source=FailingSource(),
            view=RecordingView(events),
            logger=logger,
            scheduler=RecordingScheduler(events),
        )

        monitor.refresh()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="Error",
                        secondary_text="Restart if this persists",
                        theme="data-error",
                        gif_key=None,
                        blink=False,
                    ),
                ),
                ("schedule", 10_000, monitor.refresh),
            ],
        )
        self.assertEqual(logger.counts, [])

    def test_only_valid_readings_participate_in_one_minute_logging(self) -> None:
        events: list[object] = []
        clock = ControlledClock(datetime(2026, 8, 10, 12, 0, 0))
        source = SequenceSource(
            OccupancyReading.valid(20),
            OccupancyReading.unavailable(),
            OccupancyReading.valid(21),
            OccupancyReading.data_error(),
            OccupancyReading.valid(22),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            logger = CsvOccupancyLogger(Path(temp_dir), now=clock.now)
            monitor = OccupancyMonitor(
                source=source,
                view=RecordingView(events),
                logger=logger,
                scheduler=RecordingScheduler(events),
            )

            monitor.refresh()
            clock.current += timedelta(seconds=20)
            monitor.refresh()
            clock.current += timedelta(seconds=10)
            monitor.refresh()
            clock.current += timedelta(seconds=20)
            monitor.refresh()
            clock.current += timedelta(seconds=11)
            monitor.refresh()

            log_file = Path(temp_dir) / "gym_count_2026-08-10.csv"
            with log_file.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(
            rows,
            [
                ["timestamp", "count"],
                ["2026-08-10 12:00:00", "20"],
                ["2026-08-10 12:01:01", "22"],
            ],
        )

    def test_logging_failure_is_a_retrying_data_error(self) -> None:
        events: list[object] = []
        monitor = OccupancyMonitor(
            source=FixedSource(OccupancyReading.valid(20)),
            view=RecordingView(events),
            logger=FailingLogger(),
            scheduler=RecordingScheduler(events),
        )

        monitor.refresh()

        self.assertEqual(
            events,
            [
                (
                    "render",
                    WidgetPresentation(
                        primary_text="Error",
                        secondary_text="Restart if this persists",
                        theme="data-error",
                        gif_key=None,
                        blink=False,
                    ),
                ),
                ("schedule", 10_000, monitor.refresh),
            ],
        )

    def test_valid_reading_boundaries_preserve_existing_widget_behavior(self) -> None:
        cases = [
            (24, "low", "low", True),
            (25, "low", "low", False),
            (34, "low", "low", False),
            (35, "medium", "mid", False),
            (45, "medium", "mid", False),
            (46, "high", "high", False),
        ]

        for count, theme, gif_key, blink in cases:
            with self.subTest(count=count):
                events: list[object] = []
                monitor = OccupancyMonitor(
                    source=FixedSource(OccupancyReading.valid(count)),
                    view=RecordingView(events),
                    logger=RecordingLogger(),
                    scheduler=RecordingScheduler(events),
                )

                monitor.refresh()

                self.assertEqual(
                    events[0],
                    (
                        "render",
                        WidgetPresentation(
                            primary_text=str(count),
                            secondary_text=None,
                            theme=theme,
                            gif_key=gif_key,
                            blink=blink,
                        ),
                    ),
                )

    def test_non_valid_statuses_recover_to_a_later_valid_reading(self) -> None:
        events: list[object] = []
        logger = RecordingLogger()
        monitor = OccupancyMonitor(
            source=SequenceSource(
                OccupancyReading.valid(20),
                OccupancyReading.unavailable(),
                OccupancyReading.offline(),
                OccupancyReading.data_error(),
                OccupancyReading.valid(46),
            ),
            view=RecordingView(events),
            logger=logger,
            scheduler=RecordingScheduler(events),
        )

        for _ in range(5):
            monitor.refresh()

        presentations = [
            event[1] for event in events if isinstance(event, tuple) and event[0] == "render"
        ]
        self.assertEqual(
            presentations,
            [
                WidgetPresentation("20", None, "low", "low", True),
                WidgetPresentation("N/A", None, "neutral", None, False),
                WidgetPresentation("Offline", None, "offline", None, False),
                WidgetPresentation(
                    "Error", "Restart if this persists", "data-error", None, False
                ),
                WidgetPresentation("46", None, "high", "high", False),
            ],
        )
        self.assertEqual(logger.counts, [20, 46])

    def test_unsupported_reachable_source_formats_are_data_errors(self) -> None:
        page = HttpResponse(
            '<iframe src="https://docs.google.com/spreadsheets/d/e/x/'
            'pubhtml?gid=0&amp;range=A1%3AB10"></iframe>'
        )
        feed_bodies = [
            "other room,25\n",
            "重訓室,\n",
            "重訓室,--\n",
            "重訓室,unknown\n",
            "重訓室,-1\n",
            "重訓室,about 5 人\n",
            "重訓室,25+\n",
            "重訓室,25.0\n",
        ]

        for feed_body in feed_bodies:
            with self.subTest(feed_body=feed_body):
                events: list[object] = []
                monitor = OccupancyMonitor(
                    source=NcuOccupancySource(
                        http_client=ScriptedHttpClient(page, HttpResponse(feed_body))
                    ),
                    view=RecordingView(events),
                    logger=RecordingLogger(),
                    scheduler=RecordingScheduler(events),
                )

                monitor.refresh()

                self.assertEqual(
                    events[0],
                    (
                        "render",
                        WidgetPresentation(
                            "Error",
                            "Restart if this persists",
                            "data-error",
                            None,
                            False,
                        ),
                    ),
                )

    def test_page_or_feed_timeout_is_offline(self) -> None:
        page = HttpResponse(
            '<iframe src="https://docs.google.com/spreadsheets/d/e/x/'
            'pubhtml?gid=0&amp;range=A1%3AB10"></iframe>'
        )
        clients = [
            ScriptedHttpClient(TimeoutError("page timed out")),
            ScriptedHttpClient(page, TimeoutError("feed timed out")),
        ]

        for client in clients:
            with self.subTest(client=client):
                events: list[object] = []
                monitor = OccupancyMonitor(
                    source=NcuOccupancySource(http_client=client),
                    view=RecordingView(events),
                    logger=RecordingLogger(),
                    scheduler=RecordingScheduler(events),
                )

                monitor.refresh()

                self.assertEqual(
                    events[0],
                    (
                        "render",
                        WidgetPresentation("Offline", None, "offline", None, False),
                    ),
                )


if __name__ == "__main__":
    unittest.main()
