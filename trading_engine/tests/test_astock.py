from pathlib import Path

from trading_engine.market.astock import AstockClient


def test_check_reports_version_for_executable(tmp_path: Path) -> None:
    binary = tmp_path / "astock"
    binary.write_text("#!/bin/sh\necho 'astock version test'\n", encoding="utf-8")
    binary.chmod(0o755)

    health = AstockClient(binary).check()

    assert health.available is True
    assert health.version == "astock version test"
    assert health.error is None


def test_check_reports_missing_binary(tmp_path: Path) -> None:
    health = AstockClient(tmp_path / "missing").check()

    assert health.available is False
    assert health.error == "astock binary does not exist"
