import json
import sqlite3
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from trading_engine.cli import app
from trading_engine.config import TraderSettings
from trading_engine.market.context import DecisionContextBuilder
from trading_engine.market.context_store import ContextStore
from trading_engine.store.models import MarketSnapshot, ReplayRun
from trading_engine.store.storage import ReplayStore


runner = CliRunner()


def _backdate_state(database: Path, timestamp: datetime) -> None:
    value = timestamp.isoformat()
    with sqlite3.connect(database) as connection:
        for table in (
            "accounts",
            "positions",
            "theses",
            "watch_pools",
            "watch_pool_members",
            "risk_factors",
            "trade_plans",
        ):
            connection.execute(
                f"UPDATE {table} SET created_at = ?, updated_at = ?", (value, value)
            )
        for table in ("position_theses", "position_risk_factors"):
            connection.execute(f"UPDATE {table} SET created_at = ?", (value,))


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "trading_engine").mkdir()
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


def test_independent_account_and_position_cli(tmp_path: Path, monkeypatch) -> None:
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr("trading_engine.cli.TraderSettings.load", lambda: settings)

    init_result = runner.invoke(
        app,
        [
            "account",
            "init",
            "--initial-cash",
            "100000",
            "--cash",
            "20229.40",
        ],
    )
    position_result = runner.invoke(
        app,
        [
            "position",
            "set",
            "--code",
            "603127",
            "--name",
            "昭衍新药",
            "--quantity",
            "300",
            "--sellable",
            "300",
            "--cost",
            "55.68",
            "--bought-on",
            "2026-07-16",
        ],
    )
    list_result = runner.invoke(app, ["position", "list", "--json"])

    assert init_result.exit_code == 0
    assert "独立账户 paper" in init_result.stdout
    assert position_result.exit_code == 0
    positions = json.loads(list_result.stdout)
    assert positions[0]["code"] == "603127"
    assert positions[0]["average_cost"] == "55.68"


def test_position_cli_rejects_invalid_sellable_quantity(
    tmp_path: Path, monkeypatch
) -> None:
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr("trading_engine.cli.TraderSettings.load", lambda: settings)
    runner.invoke(app, ["account", "init", "--cash", "100000"])

    result = runner.invoke(
        app,
        [
            "position",
            "set",
            "--code",
            "603127",
            "--name",
            "昭衍新药",
            "--quantity",
            "300",
            "--sellable",
            "301",
            "--cost",
            "55.68",
            "--bought-on",
            "2026-07-16",
        ],
    )

    assert result.exit_code == 1
    assert "sellable quantity must be between zero" in result.stderr


def test_independent_research_context_cli(tmp_path: Path, monkeypatch) -> None:
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr("trading_engine.cli.TraderSettings.load", lambda: settings)
    runner.invoke(app, ["account", "init", "--cash", "100000"])
    runner.invoke(
        app,
        [
            "position",
            "set",
            "--code",
            "603127",
            "--name",
            "昭衍新药",
            "--quantity",
            "300",
            "--sellable",
            "300",
            "--cost",
            "55.68",
            "--bought-on",
            "2026-07-16",
        ],
    )

    thesis_result = runner.invoke(
        app,
        [
            "thesis",
            "set",
            "--key",
            "innovation_medicine",
            "--title",
            "创新药",
            "--status",
            "active",
            "--summary",
            "海外授权与研发需求改善",
            "--realization",
            "完成定价",
            "--invalidation",
            "需求被否定",
        ],
    )
    link_result = runner.invoke(
        app,
        [
            "thesis",
            "link",
            "--key",
            "innovation_medicine",
            "--code",
            "603127",
        ],
    )
    runner.invoke(
        app,
        [
            "pool",
            "set",
            "--key",
            "innovation_pool",
            "--name",
            "创新药直接受益池",
            "--thesis",
            "innovation_medicine",
        ],
    )
    runner.invoke(
        app,
        [
            "pool",
            "member",
            "--pool",
            "innovation_pool",
            "--code",
            "603127",
        ],
    )
    pool_result = runner.invoke(
        app, ["pool", "show", "--key", "innovation_pool", "--json"]
    )
    risk_result = runner.invoke(
        app,
        [
            "risk",
            "set",
            "--key",
            "growth",
            "--name",
            "成长风格",
            "--max-exposure",
            "60",
            "--json",
        ],
    )
    risk_link_result = runner.invoke(
        app,
        ["risk", "link", "--key", "growth", "--code", "603127"],
    )

    assert thesis_result.exit_code == 0
    assert link_result.exit_code == 0
    assert json.loads(pool_result.stdout)["members"][0]["code"] == "603127"
    assert json.loads(risk_result.stdout)[0]["max_exposure_pct"] == "60"
    assert risk_link_result.exit_code == 0


def test_structured_trade_plan_cli(tmp_path: Path, monkeypatch) -> None:
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path / "data",
    )
    monkeypatch.setattr("trading_engine.cli.TraderSettings.load", lambda: settings)
    thesis = runner.invoke(
        app,
        [
            "thesis",
            "set",
            "--key",
            "defense_restructuring",
            "--title",
            "兵装集团重组",
            "--status",
            "active",
            "--summary",
            "旧事件重新定价",
            "--realization",
            "方案披露并完成定价",
            "--invalidation",
            "关系池与领导同时断裂",
            "--type",
            "event",
            "--stage",
            "confirmed",
            "--catalyst-anchor",
            "兵装集团分立",
            "--transmission-chain",
            "集团关系调整到上市平台重估",
            "--linkage",
            "company",
            "--confirmation",
            "关系池至少4/6且领导分歧修复",
        ],
    )
    risk = runner.invoke(
        app,
        [
            "risk",
            "set",
            "--key",
            "defense",
            "--name",
            "兵装风险",
            "--max-exposure",
            "30",
        ],
    )
    plan = runner.invoke(
        app,
        [
            "plan",
            "set",
            "--key",
            "buy_great_wall_20260727",
            "--date",
            "2026-07-27",
            "--thesis",
            "defense_restructuring",
            "--action",
            "BUY",
            "--code",
            "601606",
            "--name",
            "长城军工",
            "--quantity",
            "500",
            "--priority",
            "1",
            "--trigger",
            "关系池至少4/6上涨",
            "--trigger",
            "领导分歧后重新主动",
            "--ranking-notes",
            "同批最多执行前两名",
            "--rationale",
            "旧重组关系重新定价",
            "--buy-point",
            "confirmation",
            "--risk",
            "defense",
            "--observe",
            "09:35",
            "--observe",
            "09:50",
            "--json",
        ],
    )
    listed = runner.invoke(
        app,
        ["plan", "list", "--date", "2026-07-27", "--json"],
    )

    assert thesis.exit_code == 0
    assert risk.exit_code == 0
    assert plan.exit_code == 0
    payload = json.loads(listed.stdout)
    assert payload[0]["target_code"] == "601606"
    assert payload[0]["observation_times"] == ["09:35:00", "09:50:00"]
