import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from trading_engine.cli import app
from trading_engine.config import TraderSettings
from trading_engine.models import MarketSnapshot, ReplayRun


runner = CliRunner()


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "skills").mkdir()
    binary = tmp_path / "astock" / "astock"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\necho 'astock version test'\n", encoding="utf-8")
    binary.chmod(0o755)
    return tmp_path, binary


def test_version_option_does_not_require_a_command() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "trader 0.1.0"


def test_config_show_uses_explicit_repo_root(tmp_path: Path) -> None:
    repo_root, binary = _workspace(tmp_path)

    result = runner.invoke(
        app,
        ["config", "show"],
        env={"TRADER_REPO_ROOT": str(repo_root)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["repo_root"] == str(repo_root)
    assert payload["astock_binary"] == str(binary)


def test_astock_check_is_machine_readable(tmp_path: Path) -> None:
    repo_root, _ = _workspace(tmp_path)

    result = runner.invoke(
        app,
        ["astock", "check"],
        env={"TRADER_REPO_ROOT": str(repo_root)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["available"] is True
    assert payload["version"] == "astock version test"


def test_replay_command_parses_date_codes_and_until(monkeypatch) -> None:
    calls = []
    timestamp = datetime(2026, 7, 23, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    run = ReplayRun(
        id="run-1",
        trading_date=date(2026, 7, 23),
        codes=("603127",),
        current_time=timestamp,
        status="paused",
        created_at=timestamp,
        updated_at=timestamp,
    )

    class StubEngine:
        def start(self, trading_date, codes, until):
            calls.append((trading_date, codes, until))
            return run

    monkeypatch.setattr("trading_engine.cli._replay_engine", lambda: StubEngine())

    result = runner.invoke(
        app,
        [
            "replay",
            "--date",
            "20260723",
            "--code",
            "603127",
            "--until",
            "10:30",
        ],
    )

    assert result.exit_code == 0
    assert calls == [(date(2026, 7, 23), ("603127",), time(10, 30))]
    assert json.loads(result.stdout)["status"] == "paused"


def test_watch_prints_readable_shadow_snapshot(tmp_path: Path, monkeypatch) -> None:
    observed_at = datetime(
        2026, 7, 27, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    snapshot = MarketSnapshot(
        as_of=observed_at,
        source="astock-live",
        payload={
            "mode": "shadow",
            "quotes": [
                {
                    "code": "603127",
                    "price": 49.79,
                    "pre_close": 45.26,
                    "change_pct": 10.0088,
                    "volume": 493871,
                    "amount": 2389605632,
                    "open": 44.4,
                    "high": 49.79,
                    "low": 44.4,
                }
            ],
        },
    )
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path / "data",
    )

    class StubLiveMarketData:
        def __init__(self, _client, codes) -> None:
            assert codes == ("603127",)

        def snapshot(self):
            return snapshot

    monkeypatch.setattr("trading_engine.cli.TraderSettings.load", lambda: settings)
    monkeypatch.setattr("trading_engine.cli.LiveMarketData", StubLiveMarketData)

    result = runner.invoke(app, ["watch", "--code", "603127"])

    assert result.exit_code == 0
    assert "模式：只读影子，不执行交易" in result.stdout
    assert "603127" in result.stdout
    assert "49.79" in result.stdout
