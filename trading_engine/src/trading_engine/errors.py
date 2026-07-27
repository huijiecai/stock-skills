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


class LiveDataError(TradingEngineError):
    """Raised when a real-time market snapshot is missing or inconsistent."""


class JudgmentError(TradingEngineError):
    """Raised when a read-only judgment cannot be produced safely."""


class PortfolioError(TradingEngineError):
    """Raised when independent account or position input is invalid."""


class ContextError(TradingEngineError):
    """Raised when an auditable decision context cannot be built safely."""
