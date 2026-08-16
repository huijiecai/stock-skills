"""知识工具(AI 调用):预期库读写(预期研究的结果存储)。

预期 = 方向(direction)下的具体事件(event),独立生命周期(同方向可多波)。
写入拆两步(避免复杂嵌套参数,模型传参更稳):
  1) add_expectation(6 个字符串参数)→ 返回 id
  2) add_pool_member(expectation_id, 逐只追加,role 分级)
买入前提:方向已研究(status=active),未研究 = 不能买。
"""

from pydantic_ai import RunContext
from tabulate import tabulate

from trader.store import default_expectations


def get_expectations(ctx: RunContext[None]) -> str:
    """查全部预期(方向/事件/阶段/状态/核心池数)。看盘判断"这方向研究过没":未研究=不能买。"""
    data = default_expectations().get_all()
    if not data:
        return "预期库为空(没有任何已研究的预期)——所有方向都未研究,按规则不能买入"
    rows = [[e["id"], e["direction"], e["event"], e["stage"], e["status"],
             f"{e['core_count']}/{e['pool_count']}"] for e in data]
    return tabulate(rows, headers=["id", "方向", "事件", "阶段", "状态", "核心/池"],
                    tablefmt="plain")


def get_pool(ctx: RunContext[None], expectation_id: int) -> str:
    """查某预期详情:逻辑/兑现标志/失效标志 + 池成员(角色/受益理由)。"""
    e = default_expectations().get(expectation_id)
    if e is None:
        return f"预期 {expectation_id} 不存在(先 get_expectations 查 id)"
    rows = [[m["code"], m["name"], m["role"], m["reason"]] for m in e["pool"]]
    table = tabulate(rows, headers=["代码", "名称", "角色", "受益理由"], tablefmt="plain")
    return (f"#{e['id']} {e['direction']} · {e['event']} [{e['stage']}/{e['status']}]\n"
            f"逻辑:{e['thesis']}\n催化锚点:{e['catalyst']}\n"
            f"兑现标志:{e['fulfill_flag']}\n失效标志:{e['fail_flag']}\n"
            + (f"失效原因:{e['invalid_reason']}\n" if e.get("invalid_reason") else "")
            + table)


def add_expectation(ctx: RunContext[None], direction: str, event: str, thesis: str,
                    catalyst: str, fulfill_flag: str, fail_flag: str) -> str:
    """研究完新预期后写入(先写预期本体,再用 add_pool_member 逐只加池成员)。
    direction=方向归类(如"存储芯片");event=具体预期事件(如"存货涨价")——同方向可多波;
    thesis=市场在交易什么;catalyst=催化锚点(可验证依据);
    fulfill_flag=兑现标志(什么情况=故事讲完);fail_flag=失效标志(什么情况=被证伪)。
    """
    try:
        eid = default_expectations().add(
            direction, event, thesis, catalyst, fulfill_flag, fail_flag, pool=[]
        )
    except ValueError as e:
        return f"拒绝:{e}"
    return f"已写入预期 #{eid}:{direction} · {event}(现在用 add_pool_member 逐只加池成员)"


def add_pool_member(ctx: RunContext[None], expectation_id: int, code: str,
                    name: str = "", role: str = "related", reason: str = "") -> str:
    """给预期追加单个池成员。role=leader(龙头候选)/core(核心直接受益)/related(相关);
    reason 写清楚为什么受益(如"存储模组占营收70%,涨价直接增厚")。"""
    try:
        default_expectations().add_pool_member(expectation_id, code, name, role, reason)
    except ValueError as e:
        return f"拒绝:{e}"
    return f"已加 #{expectation_id} 池成员:{code} {name}({role})"


def update_expectation(ctx: RunContext[None], expectation_id: int, stage: str = "",
                       status: str = "", invalid_reason: str = "") -> str:
    """更新预期。stage:observing/emerging/confirmed/climax/fulfilling/ended;
    status:researching/active/fulfilled/invalid(失效时必须写 invalid_reason 说明)。"""
    try:
        default_expectations().update(expectation_id,
                                      stage=stage or None, status=status or None,
                                      invalid_reason=invalid_reason or None)
    except ValueError as e:
        return f"拒绝:{e}"
    parts = [f"已更新 #{expectation_id}"]
    if stage:
        parts.append(f"stage→{stage}")
    if status:
        parts.append(f"status→{status}")
    if invalid_reason:
        parts.append(f"原因:{invalid_reason}")
    return " ".join(parts)
