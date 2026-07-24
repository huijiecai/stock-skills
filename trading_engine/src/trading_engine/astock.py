from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from trading_engine.errors import AstockError
from trading_engine.models import AstockHealth


class AstockClient:
    def __init__(self, binary: Path, timeout_seconds: float = 10.0) -> None:
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def check(self) -> AstockHealth:
        if not self.binary.is_file():
            return AstockHealth(
                available=False,
                binary=self.binary,
                error="astock binary does not exist",
            )
        if not self.binary.stat().st_mode & 0o111:
            return AstockHealth(
                available=False,
                binary=self.binary,
                error="astock binary is not executable",
            )

        started = time.monotonic()
        try:
            result = self.run("--version")
        except AstockError as exc:
            return AstockHealth(
                available=False,
                binary=self.binary,
                latency_ms=_elapsed_ms(started),
                error=str(exc),
            )

        return AstockHealth(
            available=True,
            binary=self.binary,
            version=result.strip(),
            latency_ms=_elapsed_ms(started),
        )

    def run(self, *arguments: str) -> str:
        try:
            result = subprocess.run(
                [str(self.binary), *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AstockError(f"cannot execute astock: {exc}") from exc

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise AstockError(
                f"astock exited with status {result.returncode}: {detail}"
            )
        return result.stdout

    def run_json(self, *arguments: str) -> Any:
        raw = self.run(*arguments, "--json")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AstockError(
                f"astock returned invalid JSON for: {' '.join(arguments)}"
            ) from exc


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))
