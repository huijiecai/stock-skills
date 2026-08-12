"""Tests for the DeepSeek LLM provider (JSON parsing + prompt rendering)."""

from __future__ import annotations

import pytest

from trading_engine.errors import JudgmentError
from trading_engine.llm_provider import (
    _build_prompt,
    _parse_proposals,
    _render_l0,
)
from trading_engine.models import LiveQuote

QUOTES = (
    LiveQuote(
        code="000021", price=40.0, pre_close=39.91, change_pct=0.23,
        volume=120736, amount=4.8e8, open=39.39, high=40.27, low=39.38,
    ),
    LiveQuote(
        code="000636", price=57.26, pre_close=58.28, change_pct=-1.75,
        volume=161868, amount=9.3e8, open=57.18, high=58.2, low=56.7,
    ),
    LiveQuote(
        code="601606", price=32.47, pre_close=32.66, change_pct=-0.58,
        volume=24688, amount=0.8e8, open=32.3, high=32.77, low=32.18,
    ),
)


def test_parse_valid_array():
    raw = (
        '[{"code":"000021","action":"WAIT","confidence":0.6,"reason":"观察",'
        '"evidence":["e1"],"quantity":null},'
        '{"code":"000636","action":"SELL","confidence":0.8,"reason":"止损",'
        '"evidence":["主题走弱"],"quantity":200}]'
    )
    proposals = _parse_proposals(raw, QUOTES)
    assert len(proposals) == 2
    assert proposals[0].action == "WAIT"
    assert proposals[0].quantity is None
    assert proposals[1].action == "SELL"
    assert proposals[1].quantity == 200


def test_parse_single_object():
    raw = (
        '{"code":"000021","action":"RESEARCH","confidence":0.4,'
        '"reason":"需研究","evidence":["x"],"quantity":null}'
    )
    proposals = _parse_proposals(raw, QUOTES)
    assert len(proposals) == 1
    assert proposals[0].action == "RESEARCH"


def test_parse_broken_evidence_uses_regex_fallback():
    # LLM wrote evidence items outside the array (unquoted/truncated) --
    # regex fallback must still extract code/action/confidence/reason.
    raw = (
        '{"code":"000021","action":"WAIT","confidence":0.75,"reason":"测试",'
        '"evidence":["valid evidence"],"个股现价+0.40%","000021涨幅低于","quantity":null}'
    )
    proposals = _parse_proposals(raw, QUOTES)
    assert len(proposals) == 1
    assert proposals[0].code == "000021"
    assert proposals[0].action == "WAIT"
    assert proposals[0].confidence == 0.75


def test_parse_ignores_unknown_codes():
    raw = '[{"code":"999999","action":"SELL","confidence":0.9,"reason":"x","quantity":100}]'
    with pytest.raises(JudgmentError):
        _parse_proposals(raw, QUOTES)


def test_parse_buy_without_quantity_degrades_to_research():
    raw = '[{"code":"000021","action":"BUY","confidence":0.7,"reason":"买","quantity":null}]'
    proposals = _parse_proposals(raw, QUOTES)
    assert proposals[0].action == "RESEARCH"
    assert proposals[0].quantity is None


def test_parse_markdown_fence_stripped():
    raw = (
        '```json\n'
        '[{"code":"000021","action":"WAIT","confidence":0.5,"reason":"观察",'
        '"evidence":[],"quantity":null}]\n'
        '```'
    )
    proposals = _parse_proposals(raw, QUOTES)
    assert len(proposals) == 1
    assert proposals[0].code == "000021"


def test_render_l0_handles_string_decimals():
    # model_dump(mode='json') serialises Decimals as strings
    domain = {
        "as_of": "2026-08-07T09:31:00+08:00",
        "account": {"cash": "58653.00"},
        "total_assets": "113476.40",
        "positions": [
            {
                "position": {"code": "000021", "name": "深科技"},
                "quote": {"price": "39.68", "change_pct": "-0.58"},
                "pnl_pct": "2.45",
                "market_value": "15872.00",
            }
        ],
        "execution_history": [],
        "market_discovery": {},
        "pools": [],
    }
    text = _render_l0(domain)
    assert "现金=¥58,653.00" in text
    assert "000021 深科技" in text
    assert "+2.45%" in text


def test_build_prompt_contains_codes_and_rules():
    code_table = "  000021 现价40.00 涨跌+0.23%"
    prompt = _build_prompt("L0 text", code_table, QUOTES)
    assert "000021" in prompt
    assert "T+1" in prompt
    assert "BUY/SELL" in prompt
    assert "L0 text" in prompt
