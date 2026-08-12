"""DeepSeek LLM provider for read-only judgment.

Implements the :class:`JudgmentProvider` protocol by sending the L0 decision
context (rendered as plain text) to DeepSeek's Anthropic-compatible API and
parsing the JSON proposals into a :class:`JudgmentReport`.

Configuration via environment variables:
    TRADER_LLM_API_KEY   - API key (required when provider=deepseek)
    TRADER_LLM_BASE_URL  - API base URL (default https://api.deepseek.com/anthropic)
    TRADER_LLM_MODEL     - model name (default deepseek-v4-flash)
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from trading_engine.errors import JudgmentError
from trading_engine.models import (
    JudgmentContext,
    JudgmentProposal,
    JudgmentReport,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class DeepSeekProvider:
    """Calls DeepSeek (Anthropic-compatible) to produce trade judgments."""

    name = "deepseek"
    model: str

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("TRADER_LLM_API_KEY", "")
        self.base_url = (
            base_url
            or os.environ.get("TRADER_LLM_BASE_URL", "")
            or "https://api.deepseek.com/anthropic"
        ).rstrip("/")
        self.model = model or os.environ.get("TRADER_LLM_MODEL", "") or "deepseek-v4-flash"
        if not self.api_key:
            raise JudgmentError(
                "TRADER_LLM_API_KEY is required for the deepseek provider"
            )

    # ------------------------------------------------------------------ #
    # JudgmentProvider protocol
    # ------------------------------------------------------------------ #

    def judge(self, context: JudgmentContext) -> JudgmentReport:
        if context.domain_context is None:
            raise JudgmentError("deepseek provider requires a decision context")

        domain = context.domain_context
        l0_text = _render_l0(domain)
        # Only ask the LLM to judge *positions* -- pool members are context,
        # not trade targets.  Non-position codes are auto-filled as WAIT so
        # the full proposal set matches the snapshot's quote codes.
        position_codes = {
            item.get("position", {}).get("code", "")
            for item in domain.get("positions", [])
            if item.get("position", {}).get("code")
        }
        judgment_quotes = [q for q in context.quotes if q.code in position_codes]
        if not judgment_quotes:
            # No positions at all -> everything is WAIT
            judgment_quotes = []
        code_table = "\n".join(
            f"  {q.code} 现价{q.price:.2f} 涨跌{q.change_pct:+.2f}% "
            f"成交{q.amount / 1e8:.1f}亿"
            for q in judgment_quotes
        )
        user_prompt = _build_prompt(l0_text, code_table, judgment_quotes)
        if judgment_quotes:
            raw_text = self._call_api(user_prompt)
            judged = _parse_proposals(raw_text, judgment_quotes)
        else:
            judged = []
        proposals = _merge_proposals(judged, context.quotes, position_codes)

        return JudgmentReport(
            snapshot_id=context.snapshot_id,
            as_of=context.as_of,
            provider=self.name,
            model=self.model,
            proposals=tuple(proposals),
            limitations=(
                "由 DeepSeek LLM 基于当轮 L0 上下文产出;仅对持仓股给出真实判断,"
                "主题池成员自动 WAIT。BUY/SELL 仍须经 PaperBroker 硬规则校验"
                "(T+1/主板/整手/风险预算)方可执行。",
            ),
        )

    # ------------------------------------------------------------------ #
    # HTTP call
    # ------------------------------------------------------------------ #

    def _call_api(self, user_prompt: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url)
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=2048,
                thinking={"type": "disabled"},
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIStatusError as exc:
            raise JudgmentError(
                f"deepseek API error {exc.status_code}: {str(exc)[:300]}"
            ) from exc
        except Exception as exc:
            raise JudgmentError(f"deepseek API call failed: {exc}") from exc

        # Anthropic SDK returns typed content blocks; collect text blocks
        text_parts: list[str] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
        return "\n".join(text_parts)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #

def _render_l0(domain_context: dict[str, Any]) -> str:
    """Render the L0 context text from the serialized DecisionContext.

    This mirrors :func:`trading_engine.context_cli.format_context_text` but
    works on the raw dict (``domain_context``) so the provider has no import
    cycle with the CLI layer.  Values come from ``model_dump(mode='json')`` so
    Decimals arrive as strings -- ``_num`` normalises them.
    """
    lines: list[str] = []
    as_of = domain_context.get("as_of")
    if isinstance(as_of, str):
        try:
            dt = datetime.fromisoformat(as_of)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_SHANGHAI)
            lines.append(f"决策上下文 {dt.astimezone(_SHANGHAI).strftime('%Y-%m-%d %H:%M')}")
        except ValueError:
            pass
    account = domain_context.get("account", {})
    positions = domain_context.get("positions", [])
    executions = domain_context.get("execution_history", [])
    lines.append(
        f"账户=paper 现金=¥{_num(account.get('cash')):,.2f} "
        f"总资产=¥{_num(domain_context.get('total_assets')):,.2f} "
        f"持仓={len(positions)} 当日成交={len(executions)}"
    )

    discovery = domain_context.get("market_discovery") or {}

    # ① 指数
    indices = discovery.get("indices") or []
    if indices:
        lines.append("")
        lines.append("--- ① 指数 ---")
        short = {
            "上证指数": "上证", "深证成指": "深证", "科创50": "科创50",
            "创业板指": "创业板", "沪深300": "沪深300", "深证700": "深证700",
            "中证500": "中证500", "中证1000": "中证1000", "上证50": "上证50",
        }
        parts = [
            f"{short.get(idx.get('name'), idx.get('name', ''))}"
            f"{_fmt(idx.get('change_pct'))}"
            for idx in indices
        ]
        limit_ups = discovery.get("limit_up_codes") or []
        note = f" | 封板涨停{len(limit_ups)}只" if limit_ups else ""
        lines.append(" ".join(parts[:4]) + note)
        if len(parts) > 4:
            lines.append("         " + " ".join(parts[4:]))

    # ② 持仓
    lines.append("")
    lines.append(f"--- ② 持仓（{len(positions)}）---")
    for item in positions:
        pos = item.get("position", {})
        quote = item.get("quote", {})
        code = pos.get("code", "?")
        name = pos.get("name", code)
        lines.append(
            f"  {code} {_pad(name, 8)} 现价{_num(quote.get('price')):.2f} "
            f"涨跌{_fmt(quote.get('change_pct'))} "
            f"浮盈{_fmt(item.get('pnl_pct'))} "
            f"市值¥{_num(item.get('market_value')):,.0f}"
        )

    # ③ 强势板块
    sectors = discovery.get("sector_leaders") or []
    if sectors:
        lines.append("")
        lines.append("--- ③ 强势板块 ---")
        concepts = [s for s in sectors if s.get("block_type") == "concept"]
        styles = [s for s in sectors if s.get("block_type") == "style"]
        for s in concepts[:10]:
            lines.append(
                f"  {_pad(s.get('name', ''), 16)}{_fmt(s.get('change_pct'))} "
                f"涨停{s.get('limit_up_count', 0)}"
            )
        if styles:
            lines.append("  style:")
            lines.append("  " + " ".join(
                f"{s.get('name', '')}{_fmt(s.get('change_pct'))}" for s in styles[:5]
            ))
        limit_dirs = sorted(
            [s for s in concepts if s.get("limit_up_count", 0) > 0],
            key=lambda s: s.get("limit_up_count", 0),
            reverse=True,
        )[:4]
        if limit_dirs:
            lines.append(
                "  涨停方向: "
                + " ".join(
                    f"{s.get('name', '')}({s.get('limit_up_count', 0)}涨停)"
                    for s in limit_dirs
                )
            )

    # ④ 主题池
    pools = [p for p in (domain_context.get("pools") or [])
             if p.get("pool", {}).get("key") != "current_holdings"]
    if pools:
        lines.append("")
        lines.append("--- ④ 主题池 ---")
        for pool in pools:
            m = pool.get("metrics")
            if not m:
                continue
            lines.append(
                f"{pool.get('pool', {}).get('name', '?')}: "
                f"{m.get('up_count', 0)}涨{m.get('down_count', 0)}跌 "
                f"涨停{m.get('limit_up_count', 0)} "
                f"广度{_num(m.get('breadth_pct', 0)):.0f}% "
                f"领涨:{','.join((m.get('leader_codes') or [])[:3])}"
            )
            for sig in pool.get("member_signals", []):
                star = "★" if sig.get("is_limit_up") else (
                    "▲" if sig.get("is_strong") else ""
                )
                name = _pad(sig.get("name") or sig.get("code", ""), 8)
                amt = _num(sig.get("amount", 0)) / 1e8
                lines.append(
                    f"  {sig.get('code', '?')} {name} "
                    f"{_fmt(sig.get('change_pct'))} 成交{amt:.1f}亿{star}"
                )

    return "\n".join(lines)


def _build_prompt(l0_text: str, code_table: str, quotes) -> str:
    code_list = ", ".join(q.code for q in quotes)
    return f"""你是A股日内交易决策助手。基于下方当轮看盘上下文(L0),为每只持仓股输出判断。

{l0_text}

需要判断的股票(每只必须输出一条判断,code 必须在此列表中: {code_list}):
{code_table}

【交易规则约束】
1. action 可选: WAIT(继续观察) / RESEARCH(需研究,不交易) / BUY(买入) / SELL(卖出)
2. BUY/SELL 必须带 quantity,为 100 的整数倍(整手)。WAIT/RESEARCH 不能带 quantity。
3. T+1: 当日买入的股票当日不可卖出(代码以 T+1 标记的持仓不可卖)。
4. 主板限制: 只可交易主板股(代码前缀 000/001/002/003/600/601/603/605),创业板300/301、科创板688 不可新开仓。
5. 风险预算: 单主题仓位≤30%,科技类共同风险因子≤60%。
6. 14:50 后不开新仓。
7. 卖出判断须基于: 持仓跌幅>2%触发评估 / 预期失效 / 资金撤退确认。
8. 买入判断须基于: 三维确认(资金广度+价格响应+可验证依据),不可仅凭单一价格波动。

【输出格式】
严格输出 JSON 数组,不要 markdown 代码块,不要解释文字。每个元素:
{{"code":"000021","action":"WAIT","confidence":0.3,"reason":"简短理由","evidence":["证据1","证据2"],"quantity":null}}

BUY/SELL 时 quantity 为整数(100的倍数),其余为 null。"""


def _parse_proposals(raw_text: str, quotes) -> list[JudgmentProposal]:
    # strip markdown fences if present
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        fence = re.compile(r"^```[a-zA-Z]*\n?", re.MULTILINE)
        cleaned = fence.sub("", cleaned)
        cleaned = cleaned.replace("```", "").strip()

    valid_codes = {q.code for q in quotes}
    items: list[dict] = []

    # Strategy 1: try parsing as JSON array
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        parsed = _try_parse_json(match.group(0))
        if isinstance(parsed, list) and all(isinstance(i, dict) for i in parsed):
            items = parsed

    # Strategy 2: try parsing as single JSON object
    if not items:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            obj = _try_parse_json(match.group(0))
            if isinstance(obj, dict):
                items = [obj]
            elif isinstance(obj, list) and all(isinstance(i, dict) for i in obj):
                items = obj

    # Strategy 3: regex fallback - extract individual proposal objects
    if not items:
        items = _regex_extract_proposals(cleaned)

    if not items:
        raise JudgmentError(f"deepseek returned no JSON: {raw_text[:200]}")

    proposals: list[JudgmentProposal] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", ""))
        if code not in valid_codes:
            continue
        action = str(item.get("action", "WAIT")).upper()
        if action not in {"WAIT", "RESEARCH", "BUY", "SELL"}:
            action = "WAIT"
        quantity = item.get("quantity")
        if quantity is not None:
            try:
                quantity = int(quantity)
            except (TypeError, ValueError):
                quantity = None
        if action in {"WAIT", "RESEARCH"} and quantity is not None:
            quantity = None
        if action in {"BUY", "SELL"} and quantity is None:
            action = "RESEARCH"
        evidence = item.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence]
        elif not isinstance(evidence, list):
            evidence = []
        proposals.append(
            JudgmentProposal(
                code=code,
                action=action,
                confidence=float(item.get("confidence", 0.5)),
                reason=str(item.get("reason", "无理由")),
                evidence=tuple(str(e) for e in evidence if e),
                quantity=quantity,
            )
        )

    if not proposals:
        raise JudgmentError("deepseek returned no valid proposals")
    return proposals


def _try_parse_json(text: str):
    """Try json.loads, then try repairing common LLM JSON errors."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Repair: fix unquoted evidence array items by re-quoting the whole object
    repaired = _repair_json(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _repair_json(text: str) -> str:
    """Best-effort repair of common LLM JSON mistakes.

    Handles the case where the LLM writes evidence as a comma-separated list
    inside the array but forgets to quote subsequent items, e.g.:
        "evidence":["valid","unquoted item","another item"
    becomes:
        "evidence":["valid","unquoted item","another item"]
    """
    # Fix unbalanced brackets in arrays: count [ vs ] and append missing ]
    open_sq = text.count("[")
    close_sq = text.count("]")
    if open_sq > close_sq:
        text = text + "]" * (open_sq - close_sq)
    open_cr = text.count("{")
    close_cr = text.count("}")
    if open_cr > close_cr:
        text = text + "}" * (open_cr - close_cr)
    return text


def _regex_extract_proposals(text: str) -> list[dict]:
    """Last-resort: extract proposal fields via regex when JSON parsing fails."""
    items: list[dict] = []
    # Find each code-action block
    pattern = re.compile(
        r'"code"\s*:\s*"(?P<code>\d{6})"'
        r'.*?"action"\s*:\s*"(?P<action>[A-Z]+)"'
        r'.*?"confidence"\s*:\s*(?P<confidence>[\d.]+)'
        r'.*?"reason"\s*:\s*"(?P<reason>[^"]*)"',
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        item = {
            "code": m.group("code"),
            "action": m.group("action"),
            "confidence": float(m.group("confidence")),
            "reason": m.group("reason"),
            "evidence": [],
            "quantity": None,
        }
        # try to extract quantity if present
        q_match = re.search(r'"quantity"\s*:\s*(\d+)', text[m.end():m.end()+200])
        if q_match:
            item["quantity"] = int(q_match.group(1))
        items.append(item)
    return items


def _merge_proposals(
    judged: list[JudgmentProposal],
    all_quotes,
    position_codes: set[str],
) -> list[JudgmentProposal]:
    """Combine LLM-judged positions with auto-WAIT for non-position codes."""
    judged_by_code = {p.code: p for p in judged}
    merged: list[JudgmentProposal] = []
    for quote in all_quotes:
        if quote.code in judged_by_code:
            merged.append(judged_by_code[quote.code])
        else:
            merged.append(
                JudgmentProposal(
                    code=quote.code,
                    action="WAIT",
                    confidence=0.1,
                    reason="主题池成员,非持仓,自动观察",
                    evidence=("pool_member_auto_wait",),
                )
            )
    return merged


def _num(value) -> float:
    """Coerce JSON-serialized Decimals (strings) or numbers to float."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value) -> str:
    if value is None:
        return "?"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "?"


def _pad(text: str, width: int) -> str:
    display = sum(2 if ord(c) > 127 else 1 for c in text)
    return text + " " * max(0, width - display)
