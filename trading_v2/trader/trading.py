"""交易能力:下单规则 + 交易工具。

底层逻辑(_ 前缀):规则校验,工具内部用,AI 看不到。
工具函数(无 _):AI 调用的,注册到 agent。
"""
from pydantic_ai import RunContext


# ── 底层逻辑(不是工具,工具内部调)──────────────────────

def _check_t1(code: str, quantity: int) -> str | None:
    """T+1 校验:当日买入不可卖。返回 None=通过,返回 str=拒绝原因。"""
    # TODO 积木5
    pass


def _check_lot(quantity: int) -> str | None:
    """整手校验:必须是 100 的倍数。"""
    # TODO 积木5
    pass


def _check_mainboard(code: str) -> str | None:
    """主板校验:000/001/002/003/600/601/603/605 开头才能交易。"""
    # TODO 积木5
    pass


# ── 持仓状态(内存,后面可迁移到 SQLite)──────────────────

_positions: dict[str, dict] = {}  # {code: {quantity, sellable, cost}}


# ── 工具(AI 调用,注册到 agent)─────────────────────────

def trade(ctx: RunContext, action: str, code: str, quantity: int, reason: str) -> str:
    """下单交易。action=BUY/SELL。会被 T+1/整手/主板规则校验。"""
    # TODO 积木5:调 _check_* 校验,通过则更新 _positions
    pass


def query_positions(ctx: RunContext) -> str:
    """查当前持仓。"""
    # TODO 积木5
    pass
