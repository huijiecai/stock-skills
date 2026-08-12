"""Trading-system strategy packages.

A strategy package wires a concrete trading methodology (e.g. expectation-driven,
trend-following, limit-up chasing) into the engine's generic agent runtime.
Each package exports:

- ``SYSTEM_PROMPT``: the prompt that tells the LLM how to think and decide
- ``register_tools(agent)``: registers the strategy-specific tools the LLM may call
  (e.g. get_heartbeat, probe_pool). Universal tools (probe_stock, trade) are
  registered by the engine itself.

The engine (``trading_engine.agent``) never imports a strategy; the CLI loads the
requested package and passes its ``SYSTEM_PROMPT`` + ``register_tools`` into
``build_agent``. This keeps the engine free of any strategy-specific concepts
(no "pool", no "thesis", no heartbeat format).
"""
