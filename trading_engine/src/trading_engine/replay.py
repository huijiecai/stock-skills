from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from trading_engine.astock import AstockClient
from trading_engine.errors import ReplayError, StorageError
from trading_engine.models import MarketSnapshot, MinuteBar, ReplayRun
from trading_engine.protocols import MarketDataProvider
from trading_engine.storage import ReplayStore


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
ONE_MINUTE = timedelta(minutes=1)


class ReplayClock:
    def __init__(self, trading_date: date, current: datetime | None = None) -> None:
        self.trading_date = trading_date
        self._timeline = replay_timeline(trading_date)
        self._index_by_time = {value: index for index, value in enumerate(self._timeline)}
        self._current = current or self._timeline[0]
        if self._current.tzinfo is None:
            self._current = self._current.replace(tzinfo=SHANGHAI_TZ)
        if self._current not in self._index_by_time:
            raise ReplayError(
                f"invalid replay checkpoint time: {self._current.isoformat()}"
            )

    def now(self) -> datetime:
        return self._current

    def advance(self, step: timedelta = ONE_MINUTE) -> datetime:
        if step != ONE_MINUTE:
            raise ReplayError("Phase 1 replay only supports one-minute steps")
        current_index = self._index_by_time[self._current]
        if current_index + 1 >= len(self._timeline):
            raise ReplayError("replay is already at market close")
        self._current = self._timeline[current_index + 1]
        return self._current


class ReplayMarketData:
    def __init__(
        self,
        client: AstockClient,
        trading_date: date,
        codes: tuple[str, ...],
    ) -> None:
        self.client = client
        self.trading_date = trading_date
        self.codes = codes
        self._series: dict[str, tuple[float, tuple[MinuteBar, ...]]] = {}

    def snapshot(self, at: datetime) -> MarketSnapshot:
        at = _as_shanghai_time(at)
        if at.date() != self.trading_date:
            raise ReplayError("snapshot time is outside the configured trading date")

        instruments: dict[str, Any] = {}
        for code in self.codes:
            pre_close, bars = self._load(code)
            visible = [bar for bar in bars if bar.time <= at]
            instruments[code] = {
                "pre_close": pre_close,
                "bars": [bar.model_dump(mode="json") for bar in visible],
            }

        return MarketSnapshot(
            as_of=at,
            source="astock-replay",
            payload={"instruments": instruments},
        )

    def _load(self, code: str) -> tuple[float, tuple[MinuteBar, ...]]:
        cached = self._series.get(code)
        if cached is not None:
            return cached

        compact_date = self.trading_date.strftime("%Y%m%d")
        daily_rows = self.client.run_json(
            "query",
            "kline",
            code,
            "--freq",
            "daily",
            "--from",
            compact_date,
            "--to",
            compact_date,
            "--no-sync",
        )
        minute_rows = self.client.run_json(
            "query",
            "kline",
            code,
            "--freq",
            "1m",
            "--date",
            compact_date,
            "--limit",
            "300",
            "--no-sync",
        )
        if not isinstance(daily_rows, list) or len(daily_rows) != 1:
            raise ReplayError(f"{code}: expected exactly one daily bar")
        if not isinstance(minute_rows, list) or len(minute_rows) != 240:
            count = len(minute_rows) if isinstance(minute_rows, list) else "invalid"
            raise ReplayError(f"{code}: expected 240 minute bars, got {count}")

        bars = tuple(self._parse_minute_bar(code, row) for row in minute_rows)
        expected_times = replay_timeline(self.trading_date)[1:]
        actual_times = tuple(bar.time for bar in bars)
        if actual_times != expected_times:
            raise ReplayError(f"{code}: minute timestamps are incomplete or out of order")

        result = (float(daily_rows[0]["pre_close"]), bars)
        self._series[code] = result
        return result

    def _parse_minute_bar(self, code: str, row: dict[str, Any]) -> MinuteBar:
        raw_time = str(row["time"])
        parsed = datetime.strptime(
            f"{self.trading_date.year}-{raw_time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=SHANGHAI_TZ)
        if parsed.date() != self.trading_date:
            raise ReplayError(f"{code}: minute bar date does not match replay date")
        fields = {
            key: row[key]
            for key in ("open", "high", "low", "close", "volume", "amount")
        }
        return MinuteBar(code=code, time=parsed, **fields)


class ReplayEngine:
    def __init__(
        self,
        store: ReplayStore,
        provider_factory: Callable[[date, tuple[str, ...]], MarketDataProvider],
    ) -> None:
        self.store = store
        self.provider_factory = provider_factory

    def start(
        self,
        trading_date: date,
        codes: tuple[str, ...],
        until: time,
    ) -> ReplayRun:
        if not codes:
            raise ReplayError("at least one --code is required")
        clock = ReplayClock(trading_date)
        target = replay_time(trading_date, until)
        if target <= clock.now():
            raise ReplayError("replay target must be after 09:30")

        provider = self.provider_factory(trading_date, codes)
        provider.snapshot(clock.now())
        run = self.store.create_run(trading_date, codes, clock.now())
        return self._execute(run, provider, clock, target)

    def resume(self, until: time) -> ReplayRun:
        run = self.store.latest_run(("running", "paused"))
        if run is None:
            raise StorageError("no resumable replay run exists")
        target = replay_time(run.trading_date, until)
        if target <= run.current_time:
            raise ReplayError(
                "resume target must be later than the current checkpoint"
            )
        provider = self.provider_factory(run.trading_date, run.codes)
        clock = ReplayClock(run.trading_date, run.current_time)
        return self._execute(run, provider, clock, target)

    def status(self) -> ReplayRun:
        run = self.store.latest_run()
        if run is None:
            raise StorageError("no replay run exists")
        return run

    def _execute(
        self,
        run: ReplayRun,
        provider: MarketDataProvider,
        clock: ReplayClock,
        target: datetime,
    ) -> ReplayRun:
        close_time = replay_timeline(run.trading_date)[-1]
        while clock.now() < target:
            current = clock.advance()
            snapshot = provider.snapshot(current)
            status = "completed" if current == close_time else "running"
            if current == target and status != "completed":
                status = "paused"
            run = self.store.record_checkpoint(
                run.id,
                current,
                _checkpoint_state(snapshot),
                status,
            )
        return run


def replay_timeline(trading_date: date) -> tuple[datetime, ...]:
    values = [_at(trading_date, 9, 30)]
    values.extend(_minute_range(trading_date, time(9, 31), time(11, 30)))
    values.extend(_minute_range(trading_date, time(13, 1), time(15, 0)))
    return tuple(values)


def replay_time(trading_date: date, value: time) -> datetime:
    candidate = datetime.combine(trading_date, value, SHANGHAI_TZ)
    if candidate not in replay_timeline(trading_date):
        raise ReplayError(
            "time must be 09:30, 09:31-11:30, or 13:01-15:00"
        )
    return candidate


def parse_clock_time(value: str) -> time:
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ReplayError("time must use HH:MM format") from exc


def _minute_range(
    trading_date: date, start: time, end: time
) -> list[datetime]:
    current = datetime.combine(trading_date, start, SHANGHAI_TZ)
    stop = datetime.combine(trading_date, end, SHANGHAI_TZ)
    values = []
    while current <= stop:
        values.append(current)
        current += ONE_MINUTE
    return values


def _at(trading_date: date, hour: int, minute: int) -> datetime:
    return datetime.combine(trading_date, time(hour, minute), SHANGHAI_TZ)


def _as_shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(SHANGHAI_TZ)


def _checkpoint_state(snapshot: MarketSnapshot) -> dict[str, Any]:
    instruments = snapshot.payload["instruments"]
    return {
        "source": snapshot.source,
        "as_of": snapshot.as_of.isoformat(),
        "bar_counts": {
            code: len(instrument["bars"])
            for code, instrument in instruments.items()
        },
        "latest_bar_time": {
            code: instrument["bars"][-1]["time"] if instrument["bars"] else None
            for code, instrument in instruments.items()
        },
    }
