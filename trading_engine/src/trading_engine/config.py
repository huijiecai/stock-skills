from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from trading_engine.errors import ConfigurationError


class TraderSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: Path
    astock_binary: Path
    data_dir: Path

    @classmethod
    def load(cls) -> "TraderSettings":
        repo_root_value = os.environ.get("TRADER_REPO_ROOT")
        repo_root = (
            Path(repo_root_value).expanduser().resolve()
            if repo_root_value
            else _discover_repo_root()
        )

        astock_value = os.environ.get("TRADER_ASTOCK_BINARY")
        astock_binary = (
            Path(astock_value).expanduser().resolve()
            if astock_value
            else repo_root / "astock" / "build" / "astock"
        )

        data_dir_value = os.environ.get("TRADER_DATA_DIR")
        data_dir = (
            Path(data_dir_value).expanduser().resolve()
            if data_dir_value
            else repo_root / "trading_engine" / "data"
        )

        return cls(
            repo_root=repo_root,
            astock_binary=astock_binary,
            data_dir=data_dir,
        )


def _discover_repo_root() -> Path:
    candidates = [Path.cwd(), *Path.cwd().parents]
    source_path = Path(__file__).resolve()
    candidates.extend([source_path.parent, *source_path.parents])

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "astock").is_dir() and (resolved / "skills").is_dir():
            return resolved

    raise ConfigurationError(
        "cannot locate stock repository; set TRADER_REPO_ROOT explicitly"
    )
