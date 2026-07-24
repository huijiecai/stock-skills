class TradingEngineError(Exception):
    """Base exception for expected trading engine failures."""


class ConfigurationError(TradingEngineError):
    """Raised when the workspace configuration cannot be resolved."""


class AstockError(TradingEngineError):
    """Raised when an astock command cannot be executed successfully."""
