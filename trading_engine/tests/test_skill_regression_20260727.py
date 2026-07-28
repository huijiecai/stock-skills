from __future__ import annotations

import sqlite3
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from trading_engine.analysis import ReadOnlyAnalyzer
from trading_engine.context import DecisionContextBuilder
from trading_engine.context_store import ContextStore
from trading_engine.models import JudgmentProposal, JudgmentReport, MarketSnapshot
from trading_engine.paper import PaperBroker
from trading_engine.paper_store import PaperStore
from trading_engine.storage import ReplayStore


SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADING_DATE = datetime(2026, 7, 27, tzinfo=SHANGHAI).date()
PREMARKET = datetime(2026, 7, 27, 9, 10, tzinfo=SHANGHAI)

POOL_CODES = {
    "innovation_pool": (
        "603127",
        "603259",
        "600276",
        "000963",
        "002262",
        "600196",
        "002422",
    ),
    "storage_pool": (
        "000021",
        "002156",
        "600584",
        "300223",
        "603986",
        "002049",
        "688347",
        "688981",
    ),
    "changxin_pool": (
        "000021",
        "603986",
        "002409",
        "688548",
        "688019",
        "300054",
    ),
    "cpo_pool": (
        "002281",
        "300308",
        "300502",
        "300394",
        "688205",
        "688498",
        "300548",
    ),
    "armor_pool": (
        "601606",
        "002265",
        "002189",
        "000625",
        "600698",
        "600178",
    ),
    "mlcc_pool": (
        "000636",
        "300408",
        "603260",
        "603678",
        "603989",
    ),
}

PRE_CLOSE = {
    "603127": 45.26,
    "000021": 41.99,
    "002281": 186.80,
    "601606": 32.05,
    "000636": 40.22,
}


class BuyOnlyProvider:
    name = "skill-regression"
    model = "20260727-fixture"

    def __init__(self, target_code: str, quantity: int) -> None:
        self.target_code = target_code
        self.quantity = quantity

    def judge(self, context):
        proposals = []
        for quote in context.quotes:
            buying = quote.code == self.target_code
            proposals.append(
                JudgmentProposal(
                    code=quote.code,
                    action="BUY" if buying else "WAIT",
                    quantity=self.quantity if buying else None,
                    confidence=0.9 if buying else 0.7,
                    reason=(
                        "fixture confirms the stored premarket plan"
                        if buying
                        else "no stored trigger for this code"
                    ),
                    evidence=("structured-context",),
                )
            )
        return JudgmentReport(
            snapshot_id=context.snapshot_id,
            as_of=context.as_of,
            provider=self.name,
            model=self.model,
            proposals=tuple(proposals),
        )


def _seed(tmp_path: Path):
    database = tmp_path / "trader.db"
    store = ReplayStore(database)
    context_store = ContextStore(database)
    paper_store = PaperStore(database)
    store.create_account("paper", Decimal("108128.40"), Decimal("59074.40"))

    positions = (
        ("603127", "昭衍新药", 300, Decimal("55.68"), "innovation"),
        ("000021", "深科技", 400, Decimal("38.73"), "storage"),
        ("002281", "光迅科技", 100, Decimal("183.36"), "cpo"),
    )
    for code, name, quantity, cost, _ in positions:
        store.upsert_position(
            "paper", code, name, quantity, quantity, cost, TRADING_DATE.replace(day=24)
        )

    thesis_specs = {
        "innovation": ("创新药", "continuous", "confirmed"),
        "storage": ("长鑫上市与存储扩产", "event", "realizing"),
        "cpo": ("CPO资本开支", "continuous", "confirmed"),
        "armor": ("兵装集团重组", "event", "confirmed"),
        "mlcc": ("AI服务器高端MLCC", "continuous", "emerging"),
    }
    for key, (title, thesis_type, stage) in thesis_specs.items():
        store.upsert_thesis(
            key,
            title,
            "active" if key != "mlcc" else "watch",
            f"{title}的可验证摘要",
            f"{title}完成定价",
            f"{title}证据与资金共同失效",
            thesis_type,
            stage,
            f"{title}盘前催化锚",
            f"事件 -> 需求/关系 -> {title}直接受益池",
            "sub_industry",
            f"{title}固定池广度和领导价格共同确认",
        )
        context_store.add_evidence(
            thesis_key=key,
            kind="industry",
            source_name="20260727 regression fixture",
            published_at=PREMARKET.replace(hour=8, minute=0),
            observed_at=PREMARKET.replace(hour=8, minute=30),
            summary=f"{title}在盘前已知的可观察证据",
            stance="supports",
            reliability="high",
        )

    for code, _, _, _, thesis_key in positions:
        store.link_position_thesis("paper", code, thesis_key)

    pool_theses = {
        "innovation_pool": "innovation",
        "storage_pool": "storage",
        "changxin_pool": "storage",
        "cpo_pool": "cpo",
        "armor_pool": "armor",
        "mlcc_pool": "mlcc",
    }
    for pool_key, codes in POOL_CODES.items():
        pool = store.upsert_watch_pool(
            pool_key,
            pool_key,
            pool_theses[pool_key],
            monitoring_status="dormant" if pool_key == "mlcc_pool" else "active",
        )
        for code in codes:
            tradable = code.startswith(
                ("600", "601", "603", "605", "000", "001", "002", "003")
            )
            store.set_watch_pool_member(
                pool.key,
                code,
                "direct" if tradable else "research",
                tradable,
                relationship="direct" if tradable else "research",
            )

    store.upsert_risk_factor("healthcare", "医药", Decimal("30"))
    store.upsert_risk_factor("tech", "科技成长硬件", Decimal("60"))
    store.upsert_risk_factor("armor", "兵装重组", Decimal("30"))
    store.link_position_risk_factor("paper", "603127", "healthcare")
    store.link_position_risk_factor("paper", "000021", "tech")
    store.link_position_risk_factor("paper", "002281", "tech")

    store.upsert_trade_plan(
        key="sell_deeptech_20260727",
        trading_date=TRADING_DATE,
        thesis_key="storage",
        action="SELL",
        target_code="000021",
        target_name="深科技",
        quantity=200,
        priority=0,
        exit_mode="trade_confirmation",
        risk_factor_key="tech",
        observation_times=(time(9, 35), time(9, 50)),
        required_observations=2,
        trigger_conditions=(
            "09:35和09:50两个独立观察点均显示存储池<=2/8且长鑫直接池<=2/6",
            "深科技同时跌出两个池前二且首轮反抽无持续承接",
            "长鑫科技本体继续高开走低",
        ),
        guard_conditions=("只卖隔夜可卖数量",),
        cancel_conditions=(
            "任一观察点长鑫直接池恢复到3/6以上",
            "深科技从低点明显反抽或恢复相对强度",
        ),
        ranking_notes="持仓退出优先于新开仓，但必须满足完整组合",
        rationale="出口B不能由单个价格跌幅或同一段行情重复触发",
    )
    store.upsert_trade_plan(
        key="buy_greatwall_20260727",
        trading_date=TRADING_DATE,
        thesis_key="armor",
        action="BUY",
        target_code="601606",
        target_name="长城军工",
        quantity=500,
        priority=1,
        buy_point_type="confirmation",
        risk_factor_key="armor",
        observation_times=(time(9, 46),),
        trigger_conditions=(
            "兵装固定关系池至少4/6上涨",
            "长城军工不是一字板并在可成交分歧后重新领先",
        ),
        guard_conditions=("单主题低于30%且交易后现金为正",),
        cancel_conditions=("关系池不足4/6或长城不再领先",),
        ranking_notes="未归因候选不得进入排序，长城满足时排名第一",
        rationale="兵装集团分立重组关系的资金重新定价",
    )
    store.upsert_trade_plan(
        key="buy_fenghua_20260727",
        trading_date=TRADING_DATE,
        thesis_key="mlcc",
        action="BUY",
        target_code="000636",
        target_name="风华高科",
        quantity=500,
        priority=2,
        buy_point_type="confirmation",
        risk_factor_key="tech",
        observation_times=(time(9, 56),),
        trigger_conditions=(
            "休眠MLCC固定池至少4/5上涨后重新激活",
            "风华高科日内跌破昨收后重新主动并保持池内第一",
        ),
        guard_conditions=(
            "本批前两名尚未用满",
            "交易后科技共同风险不超过60%且单主题不超过30%",
        ),
        cancel_conditions=("固定池缩至2/5以下或出现更强直接领导",),
        ranking_notes="兵装之后的第二名；未归因候选不参与排序",
        rationale="AI服务器需求向高端MLCC器件传导",
    )

    _backdate_core_state(database, PREMARKET)
    return store, context_store, paper_store


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


def _quote(code: str, change_pct: float, at: datetime) -> dict:
    pre_close = PRE_CLOSE.get(code, 20.0)
    price = round(pre_close * (1 + change_pct / 100), 2)
    opening = pre_close
    low = min(price, pre_close)
    high = max(price, pre_close)
    amount = 500_000_000
    if code == "601606" and at.time() >= time(9, 42):
        opening, low, high, amount = 32.26, 32.25, 35.26, 3_000_000_000
    if code == "000636" and at.time() >= time(9, 54):
        opening, low, high, amount = 40.94, 40.01, 43.43, 4_000_000_000
    if code == "000021" and at.time() >= time(9, 50):
        opening, low, high = 41.16, 39.50, 41.79
    return {
        "code": code,
        "price": price,
        "pre_close": pre_close,
        "change_pct": (price - pre_close) / pre_close * 100,
        "volume": 1_000_000,
        "amount": amount,
        "open": opening,
        "high": high,
        "low": low,
    }


def _market(store: ReplayStore, at: datetime, changes: dict[str, float]):
    all_codes = sorted({code for codes in POOL_CODES.values() for code in codes})
    rows = [_quote(code, changes.get(code, -1), at) for code in all_codes]
    candidate_code = "601606" if at.time() < time(9, 54) else "000636"
    candidate = next(row for row in rows if row["code"] == candidate_code)
    discovery_candidate = {
        "code": candidate_code,
        "name": "长城军工" if candidate_code == "601606" else "风华高科",
        "industry": "国防军工" if candidate_code == "601606" else "电子元件",
        "sector": "兵装重组" if candidate_code == "601606" else "MLCC",
        "business": "集团上市平台" if candidate_code == "601606" else "高端MLCC",
        "price": candidate["price"],
        "pre_close": candidate["pre_close"],
        "change_pct": candidate["change_pct"],
        "amount": candidate["amount"],
        "low": candidate["low"],
        "rebound_pct": (candidate["price"] - candidate["low"])
        / candidate["pre_close"]
        * 100,
        "limit_up": candidate["change_pct"] >= 9.5,
        "reasons": ["strong_move"],
    }
    return store.record_market_snapshot(
        MarketSnapshot(
            as_of=at,
            source="astock-live",
            payload={
                "mode": "shadow",
                "quotes": rows,
                "market_discovery": {
                    "coverage_mode": "full_market",
                    "scanned_codes": all_codes,
                    "universe_count": 3200,
                    "scanned_count": 3198,
                    "missing_quote_count": 2,
                    "failed_batches": 0,
                    "candidate_codes": [candidate_code],
                    "candidates": [discovery_candidate],
                    "top_amount": [discovery_candidate],
                    "sector_leaders": [
                        {
                            "code": "sh880507",
                            "name": discovery_candidate["sector"],
                            "block_type": "concept",
                            "change_pct": 4.4,
                            "amount": 12_000_000_000,
                            "limit_up_count": 2,
                        }
                    ],
                    "indices": [
                        {
                            "code": "000001",
                            "name": "上证指数",
                            "price": 3800,
                            "pre_close": 3790,
                            "change_pct": 0.26,
                            "amount": 500_000_000_000,
                        },
                        {
                            "code": "000852",
                            "name": "中证1000",
                            "price": 7200,
                            "pre_close": 7120,
                            "change_pct": 1.12,
                            "amount": 400_000_000_000,
                        },
                    ],
                    "limit_up_codes": [],
                    "missing_capabilities": [],
                },
            },
        )
    )


def _analyze_buy(store, market, context, target_code: str, quantity: int):
    return ReadOnlyAnalyzer(
        store,
        BuyOnlyProvider(target_code, quantity),
        max_attempts=1,
    ).analyze(market, context)


def test_20260727_context_reproduces_skill_trade_preconditions(tmp_path: Path) -> None:
    store, context_store, paper_store = _seed(tmp_path)
    builder = DecisionContextBuilder(store, context_store)

    first_changes = {code: 1.0 for code in POOL_CODES["innovation_pool"]}
    first_changes.update({code: 1.0 for code in POOL_CODES["cpo_pool"][:5]})
    first_changes.update({"000021": -2.71, "002409": 0.5})
    first = builder.build(
        _market(store, PREMARKET.replace(hour=9, minute=35), first_changes), "paper"
    )
    sell_plan = next(
        item for item in first.context.trade_plans if item.plan.action == "SELL"
    )
    storage = next(item for item in first.context.pools if item.pool.key == "storage_pool")
    changxin = next(item for item in first.context.pools if item.pool.key == "changxin_pool")
    assert storage.metrics.up_count == 0
    assert changxin.metrics.up_count == 1
    assert len(sell_plan.observed_times) == 1
    assert sell_plan.plan.required_observations == 2

    armor_changes = {
        "601606": 7.30,
        "002265": 3.10,
        "002189": 2.67,
        "000625": 0.28,
        "600698": -0.4,
        "600178": -0.6,
    }
    armor_market = _market(
        store,
        PREMARKET.replace(hour=9, minute=46),
        {**first_changes, **armor_changes},
    )
    armor_context = builder.build(armor_market, "paper")
    assert armor_context.context.ready_for_judgment is True
    armor_pool = next(
        item for item in armor_context.context.pools if item.pool.key == "armor_pool"
    )
    assert armor_pool.metrics.up_count == 4
    assert armor_pool.metrics.leader_codes[0] == "601606"
    great_wall = next(
        item for item in armor_pool.member_signals if item.code == "601606"
    )
    assert great_wall.path.one_word_limit_like is False
    armor_judgment = _analyze_buy(
        store, armor_market, armor_context, "601606", 500
    )
    armor_execution = PaperBroker(
        store, context_store, paper_store
    ).execute_judgment("paper", armor_judgment.id)
    assert armor_execution.orders[-1].status == "filled"
    store.link_position_thesis("paper", "601606", "armor")
    store.link_position_risk_factor("paper", "601606", "armor")
    _backdate_core_state(
        store.database, PREMARKET.replace(hour=9, minute=46, second=30)
    )

    second_changes = {**first_changes, **armor_changes}
    second_changes.update(
        {
            "000021": -2.64,
            "002156": 0.4,
            "603986": 1.0,
            "002409": 5.2,
            "688548": 0.8,
        }
    )
    second = builder.build(
        _market(store, PREMARKET.replace(hour=9, minute=50), second_changes), "paper"
    )
    sell_plan = next(
        item for item in second.context.trade_plans if item.plan.action == "SELL"
    )
    changxin = next(item for item in second.context.pools if item.pool.key == "changxin_pool")
    assert len(sell_plan.observed_times) == 2
    assert sell_plan.missing_observation_times == ()
    assert changxin.metrics.up_count == 3
    assert next(
        item for item in second.context.positions if item.position.code == "000021"
    ).quote.path.rebound_from_low_pct > 0
    assert any(
        trade.code == "601606" and trade.quantity == 500
        for trade in second.context.execution_history
    )

    mlcc_changes = {
        "000636": 7.66,
        "300408": 4.53,
        "603260": 3.21,
        "603678": 2.90,
        "603989": 2.24,
    }
    mlcc_market = _market(
        store,
        PREMARKET.replace(hour=9, minute=56),
        {**second_changes, **mlcc_changes},
    )
    mlcc_context = builder.build(mlcc_market, "paper")
    assert mlcc_context.context.ready_for_judgment is True
    mlcc_pool = next(
        item for item in mlcc_context.context.pools if item.pool.key == "mlcc_pool"
    )
    fenghua_plan = next(
        item
        for item in mlcc_context.context.trade_plans
        if item.plan.target_code == "000636"
    )
    assert mlcc_pool.pool.monitoring_status == "dormant"
    assert mlcc_pool.metrics.up_count == 5
    assert mlcc_pool.metrics.leader_codes[0] == "000636"
    fenghua = next(item for item in mlcc_pool.member_signals if item.code == "000636")
    assert fenghua.path.dipped_below_pre_close is True
    assert fenghua.path.recovered_above_pre_close is True
    assert fenghua_plan.plan.priority == 2
    assert mlcc_context.context.strategy_rules.max_batch_buys == 2
    assert mlcc_context.context.market_discovery.coverage_mode == "full_market"
    assert mlcc_context.context.market_discovery.candidates[0].code == "000636"
    assert mlcc_context.context.market_discovery.indices[1].code == "000852"
    assert mlcc_context.context.market_discovery.missing_capabilities == ()
    assert any(
        decision.code == "601606" and decision.action == "BUY"
        for decision in mlcc_context.context.prior_decisions
    )

    mlcc_judgment = _analyze_buy(
        store, mlcc_market, mlcc_context, "000636", 500
    )
    mlcc_execution = PaperBroker(
        store, context_store, paper_store
    ).execute_judgment("paper", mlcc_judgment.id)
    assert mlcc_execution.orders[-1].status == "filled"
    assert store.get_account("paper").cash == Decimal("20229.40")
    assert store.get_position("paper", "601606").sellable_quantity == 0
    assert store.get_position("paper", "000636").sellable_quantity == 0
    assert [fill.code for fill in paper_store.list_fills("paper")] == [
        "601606",
        "000636",
    ]
