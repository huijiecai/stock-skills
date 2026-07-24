class TradingEngineError(Exception):
    """Base exception for expected trading engine failures."""


class ConfigurationError(TradingEngineError):
    """Raised when the workspace configuration cannot be resolved."""


class AstockError(TradingEngineError):
    """Raised when an astock command cannot be executed successfully."""


class ReplayError(TradingEngineError):
    """Raised when a historical replay cannot proceed safely."""


class StorageError(TradingEngineError):
    """Raised when persisted engine state is missing or inconsistent."""
