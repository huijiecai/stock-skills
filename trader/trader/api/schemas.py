"""api·响应模型:一切 JSON 响应的 data 部分在此定义(T2.1)。

端点声明 `response_model=Envelope[XxxOut]` 并返回 `Envelope(data=...)`;
traceId 由 envelope 中间件补位(端点不传),错误路径(4xx/5xx)不进
response_model,仍由中间件构造错误信封。

精度分层(见 ADR-0014):
- 手拼小结构(操作回执/对话/工具试运行)逐字段精确建模;
- store 表行建核心字段 + extra="allow":可有可无的列靠 extra 透传——
  core 加列即 API 可见,不为追求精确把 SELECT 列清单复制两份
  (core 加列忘改模型 → response_model 过滤 → 前端静默丢字段);
- 组装结构(rounds/live/curve)按组装盘建顶层字段,内层可选键透传。
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """成功信封:data + status + traceId(中间件补位)。错误信封不进此模型。"""
    data: T
    status: str = "SUCCESS"
    traceId: str = ""


class Row(BaseModel):
    """store 表行/组装结构的共同基座:声明的字段有类型,未声明的键原样透传。"""
    model_config = ConfigDict(extra="allow")


# ── auth ──────────────────────────────────────────────

class UserOut(Row):
    id: int
    email: str
    display_name: str = ""
    is_admin: bool = False
    # created_at 等整行其余列:me 返回全行靠 extra 透传;login 手拼不带则不输出

class RegisterOut(Row):
    id: int
    email: str
    display_name: str = ""

class LoginOut(Row):
    token: str
    user: UserOut

class LogoutOut(Row):
    ok: bool
    note: str

class OkOut(Row):
    ok: bool


# ── systems ───────────────────────────────────────────

class SystemRow(Row):
    id: int
    slug: str
    display_name: str = ""
    manifest: dict = Field(default_factory=dict)
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    user_id: int = 0

class SystemBrief(Row):
    slug: str
    display_name: str = ""
    status: str = "active"

class ManifestOut(Row):
    slug: str
    stages: list[str]
    policy: dict = Field(default_factory=dict)

class StageVar(Row):
    name: str
    desc: str = ""
    example: str = ""
    source: str = ""
    value: Any = None

class StageContext(Row):
    kind: str
    vars: list[StageVar]
    # note 仅 stage="(system)" 路径有 → extra 透传

class PromptRef(Row):
    stage: str
    prompt: str
    latest_version: int | None = None

class PromptVersionRow(Row):
    id: int
    prompt_id: int
    version: int
    sha256: str = ""
    size: int = 0
    created_at: str = ""

class PromptContent(Row):
    prompt: str
    version: int
    content: str

class PromptSaved(Row):
    prompt: str
    version: int
    changed: bool

class RestoreOut(Row):
    restored: str
    status: str

class DeleteOut(Row):
    deleted: str
    status: str
    note: str

class RunStarted(Row):
    started: bool
    system: str
    stage: str
    date: str
    kind: str
    clock: str
    run_inputs: dict = Field(default_factory=dict)
    note: str = ""


# ── portfolios / curve ────────────────────────────────

class PortfolioRow(Row):
    id: int
    owner_user: int = 0
    system_id: int = 0
    name: str = ""
    type: str = "paper"
    broker_account_id: int | None = None
    created_at: str = ""
    # has_positions(tools 试运行目录附加)等:extra 透传

class CurvePoint(Row):
    ts: str
    equity: int           # 分
    run_id: int | None = None

class DailyPoint(Row):
    date: str
    equity: int           # 分
    pnl: int              # 分
    pct: float = 0.0
    run_id: int | None = None

class CurveOut(Row):
    initial: int | None   # 分;钱包未开局为 None
    points: list[CurvePoint]
    daily: list[DailyPoint]


# ── runs ──────────────────────────────────────────────

class RunRow(Row):
    id: int
    user_id: int = 0
    slug: str
    kind: str
    trade_date: str | None = None
    portfolio_id: int = 0
    status: str = "running"
    system_id: int = 0
    system: str | None = None          # LEFT JOIN systems.slug
    stage: str = ""
    clock: str = "real"
    clock_date: str | None = None
    prompt_versions: str = "{}"
    fingerprint: str | None = None
    metrics: dict | None = None
    created_at: str = ""
    sealed_at: str | None = None
    heartbeat_at: str | None = None
    stage_contract: dict = Field(default_factory=dict)
    run_inputs: dict = Field(default_factory=dict)

class ReplayStarted(Row):
    started: bool
    system: str
    date: str
    note: str = ""

class RoundBrief(Row):
    n: int
    has_transcript: bool
    time: str = ""             # loop 轮的时间戳
    summary: str = ""          # 轮摘要
    in_progress: bool = False  # 进行中的最新轮
    failed: bool = False       # 连续失败未成轮(如 LLM 断连重试链)
    failures: int = 0          # 失败次数(仅 failed 时有意义)
    error: str = ""            # 最后一次错误摘要(仅 failed 时有意义)
    # single/outputs 视场次类型出现 → extra 透传

class RoundsOverview(Row):
    rounds: list[RoundBrief]

class Step(Row):
    kind: str
    # body/tool/args 按 kind 出现 → extra 透传

class RoundDetail(Row):
    n: int
    log_md: str | None
    steps: list[Step]
    usage: dict = Field(default_factory=dict)

class EventRow(Row):
    id: int
    round: int
    kind: str
    tool: str | None = None
    body: str | None = None
    created_at: str = ""

class LiveSteps(Row):
    round: int
    in_progress: bool
    steps: list[EventRow]

class StopOut(Row):
    stopped: int
    status: str
    note: str = ""

class SealOut(Row):
    sealed: int
    status: str

class PositionRow(Row):
    code: str
    name: str = ""
    quantity: int
    sellable: int = 0
    avg_cost: float       # 元(Wallet 已换算)
    bought_on: str = ""

class FillRow(Row):
    id: int
    code: str
    side: str
    quantity: int
    price_cents: int
    cash_before_cents: int = 0
    cash_after_cents: int = 0
    position_before: int = 0
    position_after: int = 0
    created_at: str = ""
    reason: str = ""
    name: str = ""
    trade_time: str | None = None
    portfolio_id: int = 0
    run_id: int | None = None

class RunTrading(Row):
    portfolio: int
    cash: float | None    # 元;钱包未开局为 None
    initial: float | None
    positions: list[PositionRow]
    fills: list[FillRow]

class AccountOut(Row):
    cash: float
    market_value: float
    asset: float
    positions: list[PositionRow]

class RunDocumentRow(Row):
    """场次证据链文档(for_run):文档列 + 关联列(relation/round/slot...)。"""
    id: int
    doc_type: str
    name: str = ""
    trade_date: str | None = None
    meta: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    relation: str = ""
    round: int = 0
    stage: str = ""
    slot: str = ""
    source_stage: str = ""
    source_output: str = ""
    linked_at: str = ""
    size: int = 0

class RunDocumentContent(Row):
    """证据链单文档全文(get_for_run):关联列 + content 快照。"""
    id: int
    doc_type: str
    name: str = ""
    trade_date: str | None = None
    meta: dict = Field(default_factory=dict)
    content: str = ""
    relation: str = ""
    round: int = 0
    stage: str = ""
    slot: str = ""
    source_stage: str = ""
    source_output: str = ""
    linked_at: str = ""
    document_updated_at: str = ""

class DocumentBrief(Row):
    id: int
    doc_type: str
    name: str = ""
    trade_date: str | None = None
    ref_id: int | None = None
    meta: dict = Field(default_factory=dict)
    size: int = 0
    created_at: str = ""
    updated_at: str = ""

class DocContent(Row):
    content: str

class WatchlistSummary(Row):
    name: str
    member_count: int
    updated_at: str = ""

class WatchlistMember(Row):
    code: str
    name: str = ""
    fields: dict = Field(default_factory=dict)


# ── tools ─────────────────────────────────────────────

class ToolParam(Row):
    name: str
    type: str = "str"
    required: bool = False
    default: Any = None

class ToolInfo(Row):
    name: str
    group: str
    write: bool
    desc: str = ""
    doc: str = ""
    params: list[ToolParam]

class TestUser(Row):
    id: int
    display_name: str = ""

class ToolsCatalog(Row):
    tools: list[ToolInfo]
    portfolios: list[PortfolioRow]
    test_user: TestUser

class ToolCallOut(Row):
    name: str
    args: dict = Field(default_factory=dict)
    portfolio: int
    output: str
    truncated: bool
    write_warning: str | None


# ── chat(对话与教练)──────────────────────────────────

class ChatAnchor(Row):
    run_id: int
    stage: str = ""
    trade_date: str = ""
    clock: str = "real"
    mode: str = "frozen"

class ChatMessage(Row):
    role: str
    content: str

class ChatReplyOut(Row):
    reply: str
    turn: int
    anchor: ChatAnchor

class ChatHistory(Row):
    messages: list[ChatMessage]
    anchor: ChatAnchor

class CoachConvRow(Row):
    id: int
    title: str = ""
    archived: bool = False
    updated_at: str = ""
    size: int = 0

class CoachNewOut(Row):
    id: int

class CoachHistory(Row):
    messages: list[ChatMessage]
    archived: bool = False

class CoachArchiveOut(Row):
    id: int
    archived: bool

class CoachReplyOut(Row):
    id: int
    reply: str
    turn: int
    title: str | None
