"""Expectation-driven trading strategy.

Implements the full expectation-management methodology:
- Three-dimensional confirmation (funding breadth + price depth + verifiable basis)
- §4.1 dual-exit selling (exit A: thesis invalidated; exit B: funding retreat)
- Divergence ≠ end (hold while the thesis basis is still being validated)

The engine treats this as just another ``(SYSTEM_PROMPT, register_tools)`` pair;
nothing in ``trading_engine.engine.agent`` knows about "pools", "theses", or the
heartbeat format — those live here.
"""

# Re-export the strategy's prompt and tool registrar for the CLI/loader.
from trading_engine.strategies.expectation_driven.strategy import (
    SYSTEM_PROMPT,
    register_tools,
)

__all__ = ["SYSTEM_PROMPT", "register_tools"]
