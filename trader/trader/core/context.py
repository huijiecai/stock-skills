"""core·执行上下文和 Stage Context 组装。

行级多租户的注入点:
- user_id:人和人看不见(知识/系统/prompt/组合的归属轴)
- portfolio_id:组合和组合不串(钱与知识的隔离轴;组合=实盘/模拟/实验)
engine 建场/开场时唯一设置——漏带参数不会串,默认值就是"当前用户/当前组合"。
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
from typing import Any

from trader.core.contracts import stage_spec

_user_id: ContextVar[int] = ContextVar("user_id", default=0)
_portfolio_id: ContextVar[int] = ContextVar("portfolio_id", default=0)
_run_id: ContextVar[int | None] = ContextVar("run_id", default=None)
_execution_mode: ContextVar[str] = ContextVar("execution_mode", default="real")
_runtime_date: ContextVar[str] = ContextVar("runtime_date", default="")
_runtime_clock: ContextVar[str] = ContextVar("runtime_clock", default="")


def set_context(portfolio_id: int, run_id: int | None = None, user_id: int = 0) -> None:
    """engine 开场调用:本进程接下来的读写都属于这个用户/组合/这场。"""
    _user_id.set(user_id)
    _portfolio_id.set(portfolio_id)
    _run_id.set(run_id)


def set_execution_mode(mode: str, date: str = "", clock: str = "") -> None:
    """Bind the run clock mode so tools cannot cross live/replay boundaries."""
    if mode not in {"real", "paper", "replay"}:
        raise ValueError(f"未知运行模式: {mode}")
    _execution_mode.set(mode)
    _runtime_date.set(date)
    _runtime_clock.set(clock)


def current_execution_mode() -> str:
    return _execution_mode.get()


def current_runtime_date() -> str:
    return _runtime_date.get()


def current_runtime_clock() -> str:
    return _runtime_clock.get()


def current_user() -> int:
    return _user_id.get()


def current_portfolio() -> int:
    return _portfolio_id.get()


def current_run() -> int | None:
    return _run_id.get()


@dataclass(frozen=True)
class RuntimeEnvelope:
    """The platform-owned identity and clock visible to every stage call."""

    system: str
    stage: str
    run_id: int | None
    user_id: int
    portfolio_id: int
    mode: str
    date: str = ""
    clock: str = ""
    round_no: int = 0
    variables: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, internal: bool = False) -> dict[str, Any]:
        # Identity, portfolio and run identifiers stay in evidence/logs.  The
        # model only needs the clock and execution mode to make a decision.
        if not internal:
            return {
                "mode": self.mode,
                "date": self.date,
                "clock": self.clock,
                "round": self.round_no,
            }
        return {
            "system": self.system,
            "stage": self.stage,
            "run_id": self.run_id,
            "user_id": self.user_id,
            "portfolio_id": self.portfolio_id,
            "mode": self.mode,
            "date": self.date,
            "clock": self.clock,
            "round": self.round_no,
            "variables": dict(self.variables),
        }

    def render(self) -> str:
        return "## 平台运行信封\n\n```json\n" + json.dumps(
            self.to_dict(), ensure_ascii=False, indent=2, default=str
        ) + "\n```"


@dataclass(frozen=True)
class ResolvedInput:
    """One input actually resolved for a stage invocation."""

    slot: str
    kind: str
    source: Any
    required: bool
    content: str
    snapshot: Any = None

    def evidence(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "kind": self.kind,
            "source": self.source,
            "required": self.required,
            "content": self.content,
            "snapshot": self.snapshot,
        }


@dataclass(frozen=True)
class StageContext:
    """Fully assembled context plus the inputs that produced it."""

    envelope: RuntimeEnvelope
    run_inputs: dict[str, Any] = field(default_factory=dict)
    inputs: tuple[ResolvedInput, ...] = ()

    def render(self) -> str:
        sections = [self.envelope.render()]
        instruction = str(self.run_inputs.get("instruction") or "").strip()
        if instruction:
            sections.append("## 本次运行请求\n\n" + instruction)
        if self.inputs:
            blocks = []
            for item in self.inputs:
                blocks.append(
                    f"### {item.slot} ({item.kind})\n"
                    f"来源: `{item.source or 'runtime'}`\n{item.content}"
                )
            sections.append("## 平台提供的阶段输入\n\n" + "\n\n".join(blocks))
        return "\n\n---\n\n".join(sections)

    def evidence(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_dict(internal=True),
            "run_inputs": dict(self.run_inputs),
            "inputs": [item.evidence() for item in self.inputs],
        }


class ContextAssembler:
    """Resolve a StageSpec into a deterministic model context.

    Stage inputs are deliberately limited to persisted artifacts.  Market,
    portfolio and research data are requested by the prompt through tools, so
    adding a stage input cannot silently change the data contract.
    """

    def assemble(self, manifest: dict, stage_name: str, variables: dict[str, Any],
                 envelope: RuntimeEnvelope, docs=None,
                 run_inputs: dict[str, Any] | None = None) -> StageContext:
        spec = stage_spec(stage_name, (manifest.get("stages") or {}).get(stage_name) or {})
        resolved: list[ResolvedInput] = []
        for slot, item in spec.inputs.items():
            if item.kind != "artifact":
                raise RuntimeError(f"阶段 {stage_name} 输入 {slot} 只能引用阶段产物")
            # Import lazily to avoid a documents -> context import cycle.
            from trader.core.stageio import resolve_artifact_input
            content, evidence = resolve_artifact_input(
                manifest, stage_name, slot, variables, docs
            )
            resolved.append(ResolvedInput(
                slot, item.kind, item.source, item.required,
                content, evidence,
            ))
        return StageContext(
            envelope=envelope,
            run_inputs=dict(run_inputs or {}),
            inputs=tuple(resolved),
        )
