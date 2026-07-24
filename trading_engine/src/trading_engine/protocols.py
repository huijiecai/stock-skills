from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from trading_engine.models import ExecutionResult, MarketSnapshot, TradeProposal


class MarketDataProvider(Protocol):
    def snapshot(self, at: datetime) -> MarketSnapshot:
        """Return only market data observable at or before the requested time."""


class TradingClock(Protocol):
    def now(self) -> datetime:
        """Return the current engine time."""

    def advance(self, step: timedelta) -> datetime:
        """Advance the engine clock and return the new time."""


class ExecutionBroker(Protocol):
    def submit(self, proposal: TradeProposal) -> ExecutionResult:
        """Validate and execute a structured trade proposal."""
