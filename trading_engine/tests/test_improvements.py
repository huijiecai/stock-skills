"""Tests for the trading-loop improvement plan features.

Covers: A1 (evidence kind=policy), A2 (causal_chain), A3 (bet_pct),
B1 (context show by date), B2 (tool_call records), D2 (paper history).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from trading_engine.cli import app
from trading_engine.config import TraderSettings
from trading_engine.context_store import ContextStore, EVIDENCE_KINDS
from trading_engine.errors import ContextError, StorageError
from trading_engine.storage import ReplayStore


SHANGHAI = ZoneInfo("Asia/Shanghai")
AS_OF = datetime(2026, 7, 28, 10, 30, tzinfo=SHANGHAI)
runner = CliRunner()


def _quote(code: str, price: float, pre_close: float) -> dict:
    return {
        "code": code,
        "price": price,
        "pre_close": pre_close,
        "change_pct": (price - pre_close) / pre_close * 100,
        "volume": 1000,
        "amount": 1_000_000,
        "open": pre_close,
        "high": max(price, pre_close),
        "low": min(price, pre_close),
    }


def _backdate_core_state(database: Path, timestamp: datetime) -> None:
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


def _seed_basic(tmp_path: Path) -> tuple[ReplayStore, ContextStore]:
    database = tmp_path / "trader.db"
    store = ReplayStore(database)
    context_store = ContextStore(database)
    store.create_account("paper", Decimal("100000"), Decimal("50000"))
    store.upsert_position(
        "paper",
        "603127",
        "昭衍新药",
        300,
        300,
        Decimal("50.00"),
        AS_OF.date() - timedelta(days=1),
    )
    thesis = store.upsert_thesis(
        "innovation_medicine",
        "创新药",
        "active",
        "研发需求改善",
        "需求完成定价",
        "需求被否定",
    )
    store.link_position_thesis("paper", "603127", thesis.key)
    pool = store.upsert_watch_pool("innovation_pool", "创新药直接受益池", thesis.key)
    store.set_watch_pool_member(pool.key, "603127", "direct", True)
    store.set_watch_pool_member(pool.key, "300255", "research", False)
    factor = store.upsert_risk_factor("growth", "成长风格", Decimal("60"))
    store.link_position_risk_factor("paper", "603127", factor.key)
    context_store.add_evidence(
        thesis_key=thesis.key,
        kind="announcement",
        source_name="交易所公告",
        published_at=AS_OF.replace(hour=9, minute=0),
        observed_at=AS_OF.replace(hour=9, minute=1),
        summary="可观察的历史证据",
        stance="supports",
        reliability="high",
    )
    _backdate_core_state(database, AS_OF.replace(hour=9, minute=10))
    return store, context_store


# ---------------------------------------------------------------------------
# A1: evidence slimming -- market removed, policy added
# ---------------------------------------------------------------------------


class TestEvidenceKinds:
    def test_market_is_no_longer_valid(self, tmp_path: Path) -> None:
        _seed_basic(tmp_path)
        store = ReplayStore(tmp_path / "trader.db")
        ctx = ContextStore(tmp_path / "trader.db")
        with pytest.raises(ContextError, match="invalid evidence kind"):
            ctx.add_evidence(
                "innovation_medicine",
                "market",
                "source",
                AS_OF.replace(hour=9, minute=0),
                AS_OF.replace(hour=9, minute=1),
                "summary",
                "neutral",
                "medium",
            )

    def test_policy_is_valid(self, tmp_path: Path) -> None:
        _seed_basic(tmp_path)
        ctx = ContextStore(tmp_path / "trader.db")
        evidence = ctx.add_evidence(
            "innovation_medicine",
            "policy",
            "药监局",
            AS_OF.replace(hour=9, minute=0),
            AS_OF.replace(hour=9, minute=1),
            "新政加速审批",
            "supports",
            "high",
        )
        assert evidence.kind == "policy"

    def test_evidence_kinds_set(self) -> None:
        assert EVIDENCE_KINDS == {
            "announcement", "news", "industry", "policy", "other"
        }
        assert "market" not in EVIDENCE_KINDS

    def test_old_market_rows_migrated_to_other(self, tmp_path: Path) -> None:
        database = tmp_path / "trader.db"
        store = ReplayStore(database)
        ctx = ContextStore(database)
        store.upsert_thesis(
            "test_thesis", "测试", "active", "s", "r", "i"
        )
        # Insert a row with kind=market by bypassing the old CHECK constraint
        with sqlite3.connect(database) as conn:
            conn.execute(
                "DROP TABLE IF EXISTS catalyst_evidence"
            )
            conn.execute(
                """
                CREATE TABLE catalyst_evidence (
                    id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(id),
                    kind TEXT NOT NULL CHECK (
                        kind IN ('announcement', 'news', 'industry', 'market', 'other')
                    ),
                    source_name TEXT NOT NULL,
                    source_url TEXT,
                    published_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    stance TEXT NOT NULL CHECK (stance IN ('supports', 'contradicts', 'neutral')),
                    reliability TEXT NOT NULL CHECK (reliability IN ('low', 'medium', 'high')),
                    created_at TEXT NOT NULL,
                    CHECK (published_at <= observed_at)
                )
                """
            )
            thesis_id = conn.execute(
                "SELECT id FROM theses WHERE key = 'test_thesis'"
            ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO catalyst_evidence (
                    id, thesis_id, kind, source_name, source_url,
                    published_at, observed_at, summary, stance,
                    reliability, created_at
                ) VALUES (?, ?, 'market', 'src', NULL,
                    '2026-07-28T09:00:00+08:00',
                    '2026-07-28T09:01:00+08:00',
                    'market evidence', 'neutral', 'medium',
                    '2026-07-28T09:02:00+00:00')
                """,
                ("test-evidence-id", thesis_id),
            )
            conn.commit()

        # Re-creating ContextStore triggers the migration
        ctx2 = ContextStore(database)
        evidence = ctx2.list_evidence(("test_thesis",))
        assert len(evidence) == 1
        assert evidence[0].kind == "other"


# ---------------------------------------------------------------------------
# A2: pool member causal_chain
# ---------------------------------------------------------------------------


class TestCausalChain:
    def test_set_member_with_causal_chain(self, tmp_path: Path) -> None:
        store = ReplayStore(tmp_path / "trader.db")
        store.upsert_thesis("t1", "测试", "active", "s", "r", "i")
        store.upsert_watch_pool("p1", "池1", "t1")
        member = store.set_watch_pool_member(
            "p1", "603127", "direct", True,
            causal_chain="研发需求 -> CXO订单 -> 昭衍新药",
        )
        assert member.causal_chain == "研发需求 -> CXO订单 -> 昭衍新药"

        # Verify round-trip
        members = store.list_watch_pool_members("p1")
        assert members[0].causal_chain == "研发需求 -> CXO订单 -> 昭衍新药"

    def test_causal_chain_defaults_to_none(self, tmp_path: Path) -> None:
        store = ReplayStore(tmp_path / "trader.db")
        store.upsert_thesis("t1", "测试", "active", "s", "r", "i")
        store.upsert_watch_pool("p1", "池1", "t1")
        member = store.set_watch_pool_member("p1", "603127", "direct", True)
        assert member.causal_chain is None

    def test_update_causal_chain_via_upsert(self, tmp_path: Path) -> None:
        store = ReplayStore(tmp_path / "trader.db")
        store.upsert_thesis("t1", "测试", "active", "s", "r", "i")
        store.upsert_watch_pool("p1", "池1", "t1")
        store.set_watch_pool_member("p1", "603127", "direct", True)
        member = store.set_watch_pool_member(
            "p1", "603127", "direct", True,
            causal_chain="新传导链",
        )
        assert member.causal_chain == "新传导链"


# ---------------------------------------------------------------------------
# A3: thesis bet_pct
# ---------------------------------------------------------------------------


class TestBetPct:
    def test_set_thesis_with_bet_pct(self, tmp_path: Path) -> None:
        store = ReplayStore(tmp_path / "trader.db")
        thesis = store.upsert_thesis(
            "t1", "测试", "active", "s", "r", "i",
            bet_pct=Decimal("15.50"),
        )
        assert thesis.bet_pct == Decimal("15.50")

        # Verify round-trip
        loaded = store.get_thesis("t1")
        assert loaded.bet_pct == Decimal("15.50")

    def test_bet_pct_defaults_to_none(self, tmp_path: Path) -> None:
        store = ReplayStore(tmp_path / "trader.db")
        thesis = store.upsert_thesis("t1", "测试", "active", "s", "r", "i")
        assert thesis.bet_pct is None

    def test_update_bet_pct_via_upsert(self, tmp_path: Path) -> None:
        store = ReplayStore(tmp_path / "trader.db")
        store.upsert_thesis("t1", "测试", "active", "s", "r", "i")
        thesis = store.upsert_thesis(
            "t1", "测试", "active", "s", "r", "i",
            bet_pct=Decimal("20"),
        )
        assert thesis.bet_pct == Decimal("20")

    def test_cli_thesis_set_with_bet(self, tmp_path: Path, monkeypatch) -> None:
        settings = TraderSettings(
            repo_root=tmp_path,
            astock_binary=tmp_path / "astock",
            data_dir=tmp_path,
        )
        monkeypatch.setattr("trading_engine.cli.TraderSettings.load", lambda: settings)
        result = runner.invoke(
            app,
            [
                "thesis", "set",
                "--key", "t1",
                "--title", "测试预期",
                "--status", "active",
                "--summary", "摘要",
                "--realization", "实现条件",
                "--invalidation", "失效条件",
                "--bet", "12.5",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert Decimal(data[0]["bet_pct"]) == Decimal("12.5")


# ---------------------------------------------------------------------------
# B1: context show by date
# ---------------------------------------------------------------------------


class TestContextShowByDate:
    def _build_context(
        self, store: ReplayStore, ctx_store: ContextStore, as_of: datetime
    ):
        from trading_engine.context import DecisionContextBuilder
        from trading_engine.models import MarketSnapshot

        builder = DecisionContextBuilder(store, ctx_store)
        snapshot = MarketSnapshot(
            as_of=as_of,
            source="astock-live",
            payload={
                "mode": "shadow",
                "quotes": [
                    _quote("603127", 52, 50),
                    _quote("300255", 20, 19),
                ],
            },
        )
        return builder.build(snapshot, "paper")

    def test_get_context_by_date_returns_latest_of_day(
        self, tmp_path: Path
    ) -> None:
        store, ctx_store = _seed_basic(tmp_path)
        # Build two contexts on the same day
        r1 = self._build_context(store, ctx_store, AS_OF.replace(hour=9, minute=35))
        r2 = self._build_context(store, ctx_store, AS_OF.replace(hour=10, minute=30))

        # No until_time: should return the latest context of the day
        found = ctx_store.get_context_by_date("paper", AS_OF.date())
        assert found is not None
        assert found.id == r2.id

    def test_get_context_by_date_with_until_returns_before_cutoff(
        self, tmp_path: Path
    ) -> None:
        store, ctx_store = _seed_basic(tmp_path)
        r1 = self._build_context(store, ctx_store, AS_OF.replace(hour=9, minute=35))
        r2 = self._build_context(store, ctx_store, AS_OF.replace(hour=10, minute=30))

        # until 10:00 should return the 9:35 context
        found = ctx_store.get_context_by_date("paper", AS_OF.date(), "10:00")
        assert found is not None
        assert found.id == r1.id

    def test_get_context_by_date_returns_none_if_no_match(
        self, tmp_path: Path
    ) -> None:
        _seed_basic(tmp_path)
        ctx_store = ContextStore(tmp_path / "trader.db")
        found = ctx_store.get_context_by_date("paper", AS_OF.date() + timedelta(days=1))
        assert found is None

    def test_cli_context_show_with_date(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        store, ctx_store = _seed_basic(tmp_path)
        self._build_context(store, ctx_store, AS_OF)
        settings = TraderSettings(
            repo_root=tmp_path,
            astock_binary=tmp_path / "astock",
            data_dir=tmp_path,
        )
        monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)
        result = runner.invoke(
            app,
            ["context", "show", "--date", "2026-07-28", "--json"],
        )
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert "2026-07-28" in data["context"]["as_of"]

    def test_cli_context_show_accepts_compact_date(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        store, ctx_store = _seed_basic(tmp_path)
        self._build_context(store, ctx_store, AS_OF)
        settings = TraderSettings(
            repo_root=tmp_path,
            astock_binary=tmp_path / "astock",
            data_dir=tmp_path,
        )
        monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)
        result = runner.invoke(
            app,
            ["context", "show", "--date", "20260728", "--json"],
        )
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert "2026-07-28" in data["context"]["as_of"]

    def test_cli_context_show_rejects_invalid_date(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        store, ctx_store = _seed_basic(tmp_path)
        self._build_context(store, ctx_store, AS_OF)
        settings = TraderSettings(
            repo_root=tmp_path,
            astock_binary=tmp_path / "astock",
            data_dir=tmp_path,
        )
        monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)
        result = runner.invoke(
            app,
            ["context", "show", "--date", "2026/07/28", "--json"],
        )
        assert result.exit_code == 1
        assert "YYYY-MM-DD or YYYYMMDD" in result.stderr


# ---------------------------------------------------------------------------
# B2: tool_call records
# ---------------------------------------------------------------------------


class TestToolCallRecords:
    def _build_context(self, tmp_path: Path):
        from trading_engine.context import DecisionContextBuilder
        from trading_engine.models import MarketSnapshot

        store, ctx_store = _seed_basic(tmp_path)
        builder = DecisionContextBuilder(store, ctx_store)
        snapshot = MarketSnapshot(
            as_of=AS_OF,
            source="astock-live",
            payload={
                "mode": "shadow",
                "quotes": [
                    _quote("603127", 52, 50),
                    _quote("300255", 20, 19),
                ],
            },
        )
        record = builder.build(snapshot, "paper")
        return ctx_store, record

    def test_add_tool_call_returns_record(self, tmp_path: Path) -> None:
        ctx_store, record = self._build_context(tmp_path)

        tool_call = ctx_store.add_tool_call(
            context_id=record.id,
            tool="astock.live.block.rank",
            arguments=json.dumps({"freq": "1m"}),
            result=json.dumps({"blocks": [{"code": "PCB", "rank": 3}]}),
        )
        assert tool_call.context_id == record.id
        assert tool_call.tool == "astock.live.block.rank"
        assert "PCB" in tool_call.result
        assert tool_call.created_at is not None

    def test_list_tool_calls_filters_by_context(self, tmp_path: Path) -> None:
        ctx_store, record = self._build_context(tmp_path)

        ctx_store.add_tool_call(
            record.id, "astock.live.block.rank",
            '{"freq":"1m"}', '{"rank":3}',
        )
        ctx_store.add_tool_call(
            record.id, "astock.query.kline",
            '{"code":"603127"}', '{"close":52}',
        )

        all_calls = ctx_store.list_tool_calls()
        assert len(all_calls) == 2

        filtered = ctx_store.list_tool_calls(record.id)
        assert len(filtered) == 2
        assert all(c.context_id == record.id for c in filtered)

        empty = ctx_store.list_tool_calls("nonexistent-id")
        assert empty == ()

    def test_add_tool_call_rejects_empty_fields(self, tmp_path: Path) -> None:
        ctx_store, record = self._build_context(tmp_path)

        with pytest.raises(ContextError, match="tool name"):
            ctx_store.add_tool_call(
                record.id, "  ", "{}", "{}"
            )

    def test_add_tool_call_rejects_nonexistent_context(
        self, tmp_path: Path
    ) -> None:
        _seed_basic(tmp_path)
        ctx_store = ContextStore(tmp_path / "trader.db")

        with pytest.raises(StorageError, match="does not exist"):
            ctx_store.add_tool_call(
                "nonexistent", "astock.tool", "{}", "{}"
            )

    def test_cli_tool_call_add_and_list(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        ctx_store, record = self._build_context(tmp_path)
        settings = TraderSettings(
            repo_root=tmp_path,
            astock_binary=tmp_path / "astock",
            data_dir=tmp_path,
        )
        monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)

        add_result = runner.invoke(
            app,
            [
                "context", "tool-call", "add",
                "--context", record.id,
                "--tool", "astock.live.block.rank",
                "--arguments", '{"freq":"1m"}',
                "--result", '{"rank":3}',
                "--json",
            ],
        )
        assert add_result.exit_code == 0, add_result.stdout
        data = json.loads(add_result.stdout)
        assert data[0]["tool"] == "astock.live.block.rank"

        list_result = runner.invoke(
            app,
            ["context", "tool-call", "list", "--context", record.id, "--json"],
        )
        assert list_result.exit_code == 0, list_result.stdout
        data = json.loads(list_result.stdout)
        assert len(data) == 1
        assert data[0]["tool"] == "astock.live.block.rank"


# ---------------------------------------------------------------------------
# D2: paper history
# ---------------------------------------------------------------------------


class TestPaperHistory:
    def test_cli_paper_history_empty(self, tmp_path: Path, monkeypatch) -> None:
        _seed_basic(tmp_path)
        settings = TraderSettings(
            repo_root=tmp_path,
            astock_binary=tmp_path / "astock",
            data_dir=tmp_path,
        )
        monkeypatch.setattr("trading_engine.paper_cli.TraderSettings.load", lambda: settings)
        result = runner.invoke(app, ["paper", "history"])
        assert result.exit_code == 0, result.stdout
        assert "无" in result.stdout

    def test_cli_paper_history_json_empty(self, tmp_path: Path, monkeypatch) -> None:
        _seed_basic(tmp_path)
        settings = TraderSettings(
            repo_root=tmp_path,
            astock_binary=tmp_path / "astock",
            data_dir=tmp_path,
        )
        monkeypatch.setattr("trading_engine.paper_cli.TraderSettings.load", lambda: settings)
        result = runner.invoke(app, ["paper", "history", "--json"])
        assert result.exit_code == 0, result.stdout
        assert json.loads(result.stdout) == []
