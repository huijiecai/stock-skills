"""引擎循环机制测试:等待分片的墙上时钟语义(机器睡眠唤醒不补睡)+ 场次心跳
+ 封场指标的场次归因(共享组合不背历史包袱)。"""
import trader.core.engine as eng
from trader.core.ledger import Wallet
from trader.core.runs import Runs

TOOL = "engine"


class _Clock:
    """假时钟:time() 读表,sleep() 走表;可选注入"唤醒跳跃"模拟系统睡眠后唤醒。"""

    def __init__(self, jump_after: float = 0.0, jump: float = 0.0):
        self.t = 1_000_000.0
        self.jump_after, self.jump = jump_after, jump
        self.slept_total = 0.0
        self.n_sleeps = 0

    def time(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.n_sleeps += 1
        self.slept_total += s
        self.t += s
        if self.jump_after and self.slept_total >= self.jump_after:
            self.t += self.jump          # 唤醒:墙上时钟瞬间前跳(睡眠期间进程冻结)
            self.jump_after = 0.0


def test_interruptible_sleep_counts_down(monkeypatch):
    """分片等待正常走表:25 秒倒数切成 10+10+5,未请求停止返回 False。"""
    clock = _Clock()
    monkeypatch.setattr(eng, "time_mod", clock)
    assert eng._interruptible_sleep(25, 999_999_999, chunk=10) is False
    assert clock.n_sleeps == 3
    assert abs(clock.slept_total - 25) < 1e-6


def test_interruptible_sleep_wakes_after_machine_sleep(monkeypatch):
    """机器睡眠后唤醒:墙上时钟已过 deadline 立即返回,不补睡剩余倒计时。

    复现 2026-08-21 run 336 事故:午休 90 分钟倒计时,macOS 睡眠 2 小时,
    旧实现(累计 waited)唤醒后继续数完剩余分钟,整场看盘被拖过收盘。"""
    clock = _Clock(jump_after=10.0, jump=7200.0)   # 第一个分片后系统睡 2 小时
    monkeypatch.setattr(eng, "time_mod", clock)
    eng._interruptible_sleep(5400, 999_999_999, chunk=10)
    assert clock.n_sleeps <= 2      # 唤醒后第一个分片即发现过期退出,而非 540 个分片


def test_poll_refreshes_heartbeat_and_reads_status(request):
    """心跳轮询:poll 一次往返刷 heartbeat_at 并返回状态;stopping 判定不回归。"""
    schema = f"t_{request.node.name[:40]}"
    from trader.core.systems import Systems
    Systems(schema=schema)                     # list() join systems,先建表
    runs = Runs(schema=schema)
    run = runs.create("hb-run", "live", "20260821", {}, system_id=1, user_id=0,
                      stage="live", portfolio_id=0)
    assert run["heartbeat_at"] == run["created_at"]       # 建场即有心跳,不误报僵死
    assert runs.poll(run["id"]) == "running"              # 轮询返回状态
    assert runs.get_by_id(run["id"])["heartbeat_at"] >= run["created_at"]
    hb = runs.get_by_id(run["id"])["heartbeat_at"]
    assert runs.list(user_id=0)[0]["heartbeat_at"] == hb  # 列表也带出心跳(前端判僵死)
    runs.set_status(run["id"], "stopping")
    assert runs.poll(run["id"]) == "stopping"             # 优雅停止路径不变


# ── 封场指标:场次归因 ───────────────────────────────────

def _patch_metrics_env(monkeypatch, schema: str, quotes: dict[str, float]):
    """把 compute_metrics 的三个外部依赖指到测试 schema/假行情。"""
    import trader.core.db as db
    import trader.core.market as market
    real_connect = db._connect
    monkeypatch.setattr(eng, "default_wallet", lambda: Wallet(schema=schema))
    monkeypatch.setattr(
        db, "_connect",
        lambda schema_=None: real_connect(schema if schema_ is None else schema_))
    monkeypatch.setattr(market, "_fetch_quotes",
                        lambda mode, codes, date="", time=None:
                        [{"code": c, "price": quotes[c]} for c in codes if c in quotes])


def test_metrics_run_scoped_on_shared_portfolio(request, monkeypatch):
    """live 共享组合:封场指标只归因本场——历史盈亏不背锅,卖老底认组合成本。

    复现 run 336 场景的抽象版:组合先亏 500(历史),本场卖继承持仓 +500、
    买新票浮盈 +200 → 本场应 +700(+0.7%),而非整本的 -x%。"""
    schema = f"t_{request.node.name[:40]}"
    acct = Wallet(schema=schema)          # 建表即兜底预置组合0钱包(10万分)
    acct.buy("000001", 1000, 10.0, on="2026-08-17", portfolio_id=0)
    acct.settle("2026-08-18", portfolio_id=0)                    # T+1 解锁可卖
    acct.sell("000001", 500, 9.0, portfolio_id=0)                # 历史:已实现 -500
    acct.sell("000001", 500, 11.0, portfolio_id=0, run_id=7)     # 本场:老底 10 元买的 +500
    acct.buy("600000", 100, 20.0, on="2026-08-21", portfolio_id=0, run_id=7)
    _patch_metrics_env(monkeypatch, schema, quotes={"600000": 22.0})

    m = eng.compute_metrics(0, "20260821", run_id=7, mode="live")
    assert m["n_fills"] == 2                     # 只算本场(整本 4 笔)
    assert m["realized_trades"] == 1
    assert m["pnl"] == 700.0                     # +500 已实现 + 200 浮盈
    assert m["initial"] == 99_500.0              # 期初=期末-本场盈亏
    assert m["return_pct"] == 0.7
    assert m["win_rate"] == 100.0
    assert m["max_drawdown_pct"] == 0.0


def test_metrics_single_run_portfolio_unchanged(request, monkeypatch):
    """回放一场一组合:run_id 过滤前后口径一致(回归护栏,老行为不漂移)。"""
    schema = f"t_{request.node.name[:40]}"
    acct = Wallet(schema=schema)          # 建表即兜底预置组合0钱包(10万分)
    acct.buy("000002", 100, 10.0, on="2026-08-17", portfolio_id=0, run_id=5)
    _patch_metrics_env(monkeypatch, schema, quotes={"000002": 10.5})

    m_run = eng.compute_metrics(0, "20260821", run_id=5, mode="replay")
    m_all = eng.compute_metrics(0, "20260821", mode="replay")
    assert m_run == m_all
    assert m_run["initial"] == 100_000.0         # 单一场组合:期初=钱包初始资金
    assert m_run["pnl"] == 50.0                  # 100×(10.5-10) 浮盈
    assert m_run["return_pct"] == 0.05
