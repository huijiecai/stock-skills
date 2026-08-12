"""Shared date/time parsing helpers."""

from __future__ import annotations

from datetime import date, datetime

from trading_engine.errors import TradingEngineError


def parse_trading_date(value: str, label: str = "date") -> date:
    """Parse a trading date from either ``YYYY-MM-DD`` or ``YYYYMMDD``.

    Raises :class:`TradingEngineError` with a friendly message on failure.
    """
    if not value:
        raise TradingEngineError(f"{label} must not be empty")
    # date.fromisoformat handles "YYYY-MM-DD"
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    # fall back to compact "YYYYMMDD"
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        raise TradingEngineError(
            f"{label} must use YYYY-MM-DD or YYYYMMDD format"
        ) from None
