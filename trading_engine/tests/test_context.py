from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from trading_engine.analysis import ReadOnlyAnalyzer
from trading_engine.cli import app
from trading_engine.config import TraderSettings
from trading_engine.context import DecisionContextBuilder, extract_context_quotes
from trading_engine.context_store import ContextStore
from trading_engine.errors import ContextError, JudgmentError
from trading_engine.models import MarketSnapshot
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


def _seed_context_state(
    tmp_path: Path,
) -> tuple[ReplayStore, ContextStore, DecisionContextBuilder]:
    database = tmp_path / "trader.db"
    store = ReplayStore(database)
    context_store = ContextStore(database)
    store.create_account("default", Decimal("100000"), Decimal("50000"))
    store.upsert_position(
        "default",
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
    store.link_position_thesis("default", "603127", thesis.key)
    pool = store.upsert_watch_pool(
        "innovation_pool", "创新药直接受益池", thesis.key
    )
    store.set_watch_pool_member(pool.key, "603127", "direct", True)
    store.set_watch_pool_member(pool.key, "300255", "research", False)
    factor = store.upsert_risk_factor("growth", "成长风格", Decimal("60"))
    store.link_position_risk_factor("default", "603127", factor.key)
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
    context_store.add_evidence(
        thesis_key=thesis.key,
        kind="news",
        source_name="未来新闻",
        published_at=AS_OF.replace(hour=11, minute=0),
        observed_at=AS_OF.replace(hour=11, minute=1),
        summary="行情时点之后才出现",
        stance="supports",
        reliability="medium",
    )
    return store, context_store, DecisionContextBuilder(store, context_store)


def _live_snapshot(
    store: ReplayStore, include_pool_member: bool = True
):
    quotes = [_quote("603127", 52, 50)]
    if include_pool_member:
        quotes.append(_quote("300255", 20, 19))
    return store.record_market_snapshot(
        MarketSnapshot(
            as_of=AS_OF,
            source="astock-live",
            payload={"mode": "shadow", "quotes": quotes},
        )
    )


def test_complete_context_is_deterministic_and_excludes_future_evidence(
    tmp_path: Path,
) -> None:
    store, context_store, builder = _seed_context_state(tmp_path)
    market_record = _live_snapshot(store)

    first = builder.build(market_record)
    second = builder.build(market_record)

    assert first.id == second.id
    assert first.fingerprint == second.fingerprint
    assert first.context.ready_for_judgment is True
    assert first.context.blockers == ()
    assert first.context.total_assets == Decimal("65600.00")
    assert first.context.positions[0].unrealized_pnl == Decimal("600.00")
    assert first.context.pools[0].coverage_pct == Decimal("100.0000")
    assert first.context.evidence[0].summary == "可观察的历史证据"
    assert first.context.excluded_future_evidence_count == 1
    assert context_store.latest_context("default") == first


def test_live_context_accepts_zero_session_range_before_first_trade(
    tmp_path: Path,
) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    quote = _quote("603127", 50, 50)
    quote.update({"open": 0, "high": 0, "low": 0})
    market_record = store.record_market_snapshot(
        MarketSnapshot(
            as_of=AS_OF,
            source="astock-live",
            payload={"mode": "shadow", "quotes": [quote]},
        )
    )

    context_quote = extract_context_quotes(market_record)[0]

    assert context_quote.open == Decimal("0")
    assert context_quote.high == Decimal("0")
    assert context_quote.low == Decimal("0")


def test_missing_pool_quote_blocks_judgment_without_losing_position_context(
    tmp_path: Path,
) -> None:
    store, _, builder = _seed_context_state(tmp_path)

    record = builder.build(_live_snapshot(store, include_pool_member=False))

    assert record.context.ready_for_judgment is False
    assert record.context.positions[0].position.code == "603127"
    assert record.context.pools[0].missing_codes == ("300255",)
    assert "pool:innovation_pool:missing_quotes=300255" in record.context.blockers


def test_missing_position_quote_and_future_state_fail_closed(tmp_path: Path) -> None:
    store, _, builder = _seed_context_state(tmp_path)
    missing_position = store.record_market_snapshot(
        MarketSnapshot(
            as_of=AS_OF,
            source="astock-live",
            payload={"mode": "shadow", "quotes": [_quote("300255", 20, 19)]},
        )
    )
    with pytest.raises(ContextError, match="missing position quote"):
        builder.build(missing_position)

    historical = store.record_market_snapshot(
        MarketSnapshot(
            as_of=datetime(2026, 7, 23, 10, 30, tzinfo=SHANGHAI),
            source="astock-live",
            payload={
                "mode": "shadow",
                "quotes": [
                    _quote("603127", 52, 50),
                    _quote("300255", 20, 19),
                ],
            },
        )
    )
    with pytest.raises(ContextError, match="updated after the market snapshot"):
        builder.build(historical)


def test_position_buy_date_after_market_snapshot_is_rejected(tmp_path: Path) -> None:
    store, _, builder = _seed_context_state(tmp_path)
    store.upsert_position(
        "default",
        "603127",
        "昭衍新药",
        300,
        0,
        Decimal("50.00"),
        AS_OF.date() + timedelta(days=1),
    )

    with pytest.raises(ContextError, match="buy date after"):
        builder.build(_live_snapshot(store))


def test_replay_quote_rejects_future_bar_and_uses_only_visible_bars(
    tmp_path: Path,
) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    visible_bar = {
        "code": "603127",
        "time": AS_OF - timedelta(minutes=1),
        "open": 50,
        "high": 52,
        "low": 49,
        "close": 51,
        "volume": 100,
        "amount": 5100,
    }
    record = store.record_market_snapshot(
        MarketSnapshot(
            as_of=AS_OF,
            source="astock-replay",
            payload={
                "instruments": {
                    "603127": {"pre_close": 50, "bars": [visible_bar]}
                }
            },
        )
    )

    quote = extract_context_quotes(record)[0]
    assert quote.price == Decimal("51.0")
    assert quote.volume == 100

    future_bar = {**visible_bar, "time": AS_OF + timedelta(minutes=1)}
    future_record = store.record_market_snapshot(
        record.snapshot.model_copy(
            update={
                "payload": {
                    "instruments": {
                        "603127": {"pre_close": 50, "bars": [future_bar]}
                    }
                }
            }
        )
    )
    with pytest.raises(ContextError, match="future bar"):
        extract_context_quotes(future_record)


def test_complete_replay_context_uses_same_contract_deterministically(
    tmp_path: Path,
) -> None:
    store, _, builder = _seed_context_state(tmp_path)

    def instrument(code: str, price: float, pre_close: float) -> dict:
        return {
            "pre_close": pre_close,
            "bars": [
                {
                    "code": code,
                    "time": AS_OF - timedelta(minutes=1),
                    "open": pre_close,
                    "high": max(price, pre_close),
                    "low": min(price, pre_close),
                    "close": price,
                    "volume": 100,
                    "amount": price * 100,
                }
            ],
        }

    market_record = store.record_market_snapshot(
        MarketSnapshot(
            as_of=AS_OF,
            source="astock-replay",
            payload={
                "instruments": {
                    "603127": instrument("603127", 52, 50),
                    "300255": instrument("300255", 20, 19),
                }
            },
        )
    )

    first = builder.build(market_record)
    second = builder.build(market_record)

    assert first.id == second.id
    assert first.context.market_source == "astock-replay"
    assert first.context.ready_for_judgment is True
    assert first.context.excluded_future_evidence_count == 1

    judgment = ReadOnlyAnalyzer(store).analyze(market_record, first)
    assert judgment.input_context.decision_context_id == first.id
    assert judgment.input_context.decision_context_fingerprint == first.fingerprint
    assert judgment.input_context.domain_context is not None
    assert judgment.input_context.policy == "context-read-only-v1"
    assert {proposal.code for proposal in judgment.report.proposals} == {
        "603127",
        "300255",
    }


def test_context_cli_build_and_show_use_persisted_independent_state(
    tmp_path: Path, monkeypatch
) -> None:
    store, _, _ = _seed_context_state(tmp_path)
    _live_snapshot(store)
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path,
    )
    monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)
    monkeypatch.setattr("trading_engine.cli.TraderSettings.load", lambda: settings)

    build_result = runner.invoke(app, ["context", "build", "--json"])
    show_result = runner.invoke(app, ["context", "show", "--json"])
    analyze_result = runner.invoke(app, ["analyze", "context", "--json"])

    assert build_result.exit_code == 0
    assert show_result.exit_code == 0
    built = json.loads(build_result.stdout)
    shown = json.loads(show_result.stdout)
    assert built["id"] == shown["id"]
    assert built["context"]["ready_for_judgment"] is True
    assert analyze_result.exit_code == 0
    analyzed = json.loads(analyze_result.stdout)
    assert analyzed["input_context"]["decision_context_id"] == built["id"]


def test_analyzer_refuses_blocked_context(tmp_path: Path) -> None:
    store, _, builder = _seed_context_state(tmp_path)
    market_record = _live_snapshot(store, include_pool_member=False)
    context_record = builder.build(market_record)

    with pytest.raises(JudgmentError, match="decision context is blocked"):
        ReadOnlyAnalyzer(store).analyze(market_record, context_record)


def test_context_contains_plans_dormant_pools_paths_and_observation_history(
    tmp_path: Path,
) -> None:
    store, context_store, builder = _seed_context_state(tmp_path)
    store.upsert_thesis(
        "innovation_medicine",
        "创新药",
        "active",
        "研发需求改善",
        "需求完成定价",
        "需求被否定",
        "continuous",
        "confirmed",
        "创新药BD与研发订单",
        "研发需求 -> CXO订单 -> 昭衍新药",
        "sub_industry",
        "固定池多数上涨且昭衍保持前二",
    )
    mlcc = store.upsert_thesis(
        "ai_server_mlcc",
        "AI服务器高端MLCC",
        "watch",
        "AI服务器需求向高端MLCC传导",
        "服务器订单和MLCC需求完成定价",
        "需求转弱且直接池联动消失",
        "continuous",
        "emerging",
        "AI服务器资本开支",
        "AI服务器扩产 -> 高端MLCC需求 -> 风华高科",
        "sub_industry",
        "固定池至少4/5上涨且风华分歧后重新领先",
    )
    pool = store.upsert_watch_pool(
        "mlcc_pool",
        "AI服务器高端MLCC池",
        mlcc.key,
        monitoring_status="dormant",
    )
    for code in ("000636", "300408", "603260", "603678", "603989"):
        store.set_watch_pool_member(
            pool.key,
            code,
            "direct",
            code.startswith(("000", "600", "601", "603", "605")),
        )
    store.upsert_risk_factor("tech_growth", "科技成长", Decimal("60"))
    store.upsert_trade_plan(
        key="buy_fenghua_20260728",
        trading_date=AS_OF.date(),
        thesis_key=mlcc.key,
        action="BUY",
        target_code="000636",
        target_name="风华高科",
        quantity=500,
        priority=2,
        trigger_conditions=(
            "MLCC固定池至少4/5上涨",
            "风华高科经历分歧后重新主动并保持池内第一",
        ),
        ranking_notes="按新鲜度、确认质量、领导和账户风险排序",
        rationale="服务器资本开支向高端MLCC需求传导",
        buy_point_type="confirmation",
        risk_factor_key="tech_growth",
        observation_times=(time(9, 35), time(9, 50)),
        required_observations=2,
        guard_conditions=("交易后科技共同风险不超过60%",),
        cancel_conditions=("固定池缩至2/5以下",),
    )
    context_store.add_evidence(
        thesis_key=mlcc.key,
        kind="industry",
        source_name="fixture",
        published_at=AS_OF.replace(hour=8, minute=0),
        observed_at=AS_OF.replace(hour=8, minute=1),
        summary="盘前可观察的AI服务器需求证据",
        stance="supports",
        reliability="high",
    )

    codes = builder.required_live_codes("default", AS_OF.date())
    assert "000636" in codes
    assert "300408" in codes

    def market(at: datetime, fenghua_price: float):
        rows = [
            _quote("603127", 52, 50),
            _quote("300255", 20, 19),
            {
                **_quote("000636", fenghua_price, 40),
                "open": 40.5,
                "high": fenghua_price,
                "low": 39.8,
            },
            _quote("300408", 32, 30),
            _quote("603260", 21, 20),
            _quote("603678", 42, 40),
            _quote("603989", 31, 30),
        ]
        return store.record_market_snapshot(
            MarketSnapshot(
                as_of=at,
                source="astock-live",
                payload={"mode": "shadow", "quotes": rows},
            )
        )

    first_market = market(AS_OF.replace(hour=9, minute=35), 42)
    first = builder.build(first_market)
    assert first.context.ready_for_judgment is True
    ReadOnlyAnalyzer(store).analyze(first_market, first)

    second = builder.build(market(AS_OF.replace(hour=9, minute=50), 43))

    mlcc_context = next(
        item for item in second.context.pools if item.pool.key == "mlcc_pool"
    )
    plan_context = second.context.trade_plans[0]
    assert mlcc_context.pool.monitoring_status == "dormant"
    assert mlcc_context.metrics is not None
    assert mlcc_context.metrics.up_count == 5
    assert mlcc_context.metrics.leader_codes[0] == "000636"
    fenghua = next(
        item for item in mlcc_context.member_signals if item.code == "000636"
    )
    assert fenghua.path.dipped_below_pre_close is True
    assert fenghua.path.recovered_above_pre_close is True
    assert len(plan_context.observed_times) == 2
    assert plan_context.missing_observation_times == ()
    assert [item.as_of.time() for item in second.context.observation_history] == [
        time(9, 35)
    ]
    assert second.context.prior_decisions
    assert second.context.strategy_rules is not None
    assert second.context.strategy_rules.max_batch_buys == 2
    assert second.context.market_discovery is not None
    assert "full_market_candidates" in second.context.market_discovery.missing_capabilities


def test_context_capture_requests_positions_and_all_active_pool_members(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_context_state(tmp_path)
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path,
    )

    class StubLiveMarketData:
        def __init__(self, _client, codes, include_discovery=False) -> None:
            assert codes == ("300255", "603127")
            assert include_discovery is True

        def snapshot(self):
            return MarketSnapshot(
                as_of=AS_OF,
                source="astock-live",
                payload={
                    "mode": "shadow",
                    "quotes": [
                        _quote("300255", 20, 19),
                        _quote("603127", 52, 50),
                    ],
                },
            )

    monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)
    monkeypatch.setattr("trading_engine.context_cli.LiveMarketData", StubLiveMarketData)

    result = runner.invoke(app, ["context", "capture", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["context"]["ready_for_judgment"] is True


def test_context_replay_cli_uses_required_codes_and_same_builder(
    tmp_path: Path, monkeypatch
) -> None:
    _seed_context_state(tmp_path)
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path,
    )

    class StubReplayMarketData:
        def __init__(self, _client, trading_date, codes) -> None:
            assert trading_date == AS_OF.date()
            assert codes == ("300255", "603127")

        def snapshot(self, at):
            assert at == AS_OF
            return MarketSnapshot(
                as_of=at,
                source="astock-replay",
                payload={
                    "instruments": {
                        "300255": {
                            "pre_close": 19,
                            "bars": [
                                {
                                    "code": "300255",
                                    "time": at - timedelta(minutes=1),
                                    "open": 19,
                                    "high": 20,
                                    "low": 19,
                                    "close": 20,
                                    "volume": 100,
                                    "amount": 2000,
                                }
                            ],
                        },
                        "603127": {
                            "pre_close": 50,
                            "bars": [
                                {
                                    "code": "603127",
                                    "time": at - timedelta(minutes=1),
                                    "open": 50,
                                    "high": 52,
                                    "low": 50,
                                    "close": 52,
                                    "volume": 100,
                                    "amount": 5200,
                                }
                            ],
                        },
                    }
                },
            )

    monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)
    monkeypatch.setattr(
        "trading_engine.context_cli.ReplayMarketData", StubReplayMarketData
    )

    result = runner.invoke(
        app,
        [
            "context",
            "replay",
            "--date",
            "20260728",
            "--until",
            "10:30",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["context"]["market_source"] == "astock-replay"
    assert payload["context"]["excluded_future_evidence_count"] == 1


def test_evidence_cli_add_and_as_of_filter(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "trader.db"
    store = ReplayStore(database)
    store.upsert_thesis(
        "innovation_medicine",
        "创新药",
        "active",
        "summary",
        "realization",
        "invalidation",
    )
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path,
    )
    monkeypatch.setattr("trading_engine.context_cli.TraderSettings.load", lambda: settings)

    add_result = runner.invoke(
        app,
        [
            "evidence",
            "add",
            "--thesis",
            "innovation_medicine",
            "--kind",
            "announcement",
            "--source",
            "交易所",
            "--published-at",
            "2026-07-28T09:00:00+08:00",
            "--observed-at",
            "2026-07-28T09:01:00+08:00",
            "--summary",
            "新增公告",
            "--stance",
            "supports",
            "--reliability",
            "high",
        ],
    )
    before_result = runner.invoke(
        app,
        [
            "evidence",
            "list",
            "--as-of",
            "2026-07-28T08:59:00+08:00",
            "--json",
        ],
    )
    after_result = runner.invoke(
        app,
        [
            "evidence",
            "list",
            "--as-of",
            "2026-07-28T09:01:00+08:00",
            "--json",
        ],
    )

    assert add_result.exit_code == 0
    assert json.loads(before_result.stdout) == []
    assert json.loads(after_result.stdout)[0]["summary"] == "新增公告"


def test_evidence_rejects_naive_or_inverted_timestamps(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    context_store = ContextStore(tmp_path / "trader.db")
    store.upsert_thesis(
        "innovation_medicine",
        "创新药",
        "active",
        "summary",
        "realization",
        "invalidation",
    )
    with pytest.raises(ContextError, match="timezone"):
        context_store.add_evidence(
            "innovation_medicine",
            "news",
            "source",
            datetime(2026, 7, 28, 9, 0),
            datetime(2026, 7, 28, 9, 1),
            "summary",
            "neutral",
            "medium",
        )
    with pytest.raises(ContextError, match="later than"):
        context_store.add_evidence(
            "innovation_medicine",
            "news",
            "source",
            AS_OF,
            AS_OF - timedelta(minutes=1),
            "summary",
            "neutral",
            "medium",
        )
