"""轮次概览的失败可见性(8/25 run 486 事故):连续失败聚成红条,偶发失败不噪音。

docstring 统一格式:<场景>:<验证点>
"""
import random

from trader.core.events import default_events, set_current_round
from trader.core.queries import rounds_overview
from trader.core.runs import default_runs


def _mk_run(status: str = "sealed") -> dict:
    uid = 10086
    slug = f"failvis-{random.randint(10**6, 10**7)}"
    run = default_runs().create(slug, "live", "20260825", {}, system_id=1,
                                user_id=uid, stage="live",
                                clock="real", portfolio_id=999)
    default_runs().set_status(run["id"], status)
    return default_runs().get(slug, uid)


def test_consecutive_failures_surface_as_failed_round():
    """连续失败链:无轮日志的轮聚合出 failed 红条,带次数与最后错误。"""
    run = _mk_run()
    ev = default_events()
    ev.append(run["id"], 5, "round_start", body="第 5 轮 · 实时看盘 13:27:09")
    for _ in range(3):
        ev.append(run["id"], 5, "round_end", body="中断重试: ModelAPIError")
    overview = rounds_overview(run)
    failed = [x for x in overview["rounds"] if x.get("failed")]
    assert len(failed) == 1
    assert failed[0]["n"] == 5 and failed[0]["failures"] == 3
    assert "ModelAPIError" in failed[0]["error"]
    assert failed[0]["in_progress"] is False   # 场已封存,不标进行中


def test_recovered_round_is_not_marked_failed():
    """偶发失败后成功:轮日志已落库 → 健康重试,不产生红条。"""
    from trader.core.context import set_context
    from trader.core.documents import default_documents
    run = _mk_run()
    ev = default_events()
    ev.append(run["id"], 3, "round_end", body="中断重试: OperationalError")
    # 该轮最终成功:按引擎真实路径落轮日志(set_context + set_current_round + save + link)
    set_context(999, run["id"], 10086)
    set_current_round(3)
    doc_id = default_documents().save(
        "watch_live", "第 3 轮日志正文", name="r3", trade_date="20260825",
        portfolio_id=999)
    default_documents().link_run(doc_id, "output")
    overview = rounds_overview(run)
    assert not [x for x in overview["rounds"] if x.get("failed")]
    assert any(x["n"] == 3 for x in overview["rounds"])   # 正常轮仍在列表


def test_single_failure_is_not_noise():
    """单次失败即成功:重试机制正常工作,不值得打扰用户。"""
    run = _mk_run()
    ev = default_events()
    ev.append(run["id"], 2, "round_end", body="中断重试: TimeoutError")
    overview = rounds_overview(run)
    assert not [x for x in overview["rounds"] if x.get("failed")]
