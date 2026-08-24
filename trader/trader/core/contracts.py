"""Stage runtime contract primitives.

The manifest remains JSON data at the API boundary, but the engine should not
operate on untyped nested dictionaries.  This module is deliberately small and
dependency-free so it can be used by the API, engine, and tests alike.

The contract has four user-facing concerns:

* inputs: data the platform resolves before a model call;
* outputs: business results the stage may publish;
* execution: scheduling and retry limits.

Legacy top-level fields (``kind``, ``interval``, ``request_limit`` and
``window``) are accepted and normalized into ``execution``.  New code should
read the normalized objects rather than branching on the legacy shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CONTRACT_VERSION = 2
INPUT_KINDS = {"artifact"}
OUTPUT_KINDS = {"artifact", "resource", "action", "metric"}
EXECUTION_MODES = {"single", "loop"}
SELECTORS = {"latest", "previous", "recent", "all"}
POLICY_DEFAULTS = {
    "web_search": False,
    "resource_write": False,
    "simulation_trading": True,
    "live_trading": False,
}


def _as_dict(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是对象")
    return dict(value)


@dataclass(frozen=True)
class InputSpec:
    id: str
    kind: str = "artifact"
    source: Any = None
    selector: str = "latest"
    required: bool = False
    label: str = ""
    max_chars: int | None = None
    as_of: str = "run.clock"
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, input_id: str, raw: Any) -> "InputSpec":
        data = _as_dict(raw, f"输入 {input_id}")
        source = data.get("source", data.get("from"))
        known = {"kind", "source", "from", "selector", "required", "label",
                 "max_chars", "as_of", "trade_date", "limit"}
        config = {k: v for k, v in data.items() if k not in known}
        if "trade_date" in data:
            config["trade_date"] = data["trade_date"]
        if "limit" in data:
            config["limit"] = data["limit"]
        return cls(
            id=input_id,
            kind=str(data.get("kind", "artifact")),
            source=source,
            selector=str(data.get("selector", "latest")),
            required=bool(data.get("required", False)),
            label=str(data.get("label", "")),
            max_chars=int(data["max_chars"]) if data.get("max_chars") is not None else None,
            as_of=str(data.get("as_of", "run.clock")),
            config=config,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "selector": self.selector,
            "required": self.required,
            "as_of": self.as_of,
        }
        if self.source is not None:
            data["source"] = self.source
            # Keep the editor/API alias while clients migrate to ``source``.
            # The engine reads the canonical source value above.
            if self.kind == "artifact" and isinstance(self.source, str):
                data["from"] = self.source
        if self.label:
            data["label"] = self.label
        if self.max_chars is not None:
            data["max_chars"] = self.max_chars
        data.update(self.config)
        return data


@dataclass(frozen=True)
class OutputSpec:
    id: str
    kind: str = "artifact"
    required: bool = False
    capture: str = "final"
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, output_id: str, raw: Any) -> "OutputSpec":
        data = _as_dict(raw, f"输出 {output_id}")
        # ``document`` was the old storage kind; it now means an artifact.
        kind = str(data.get("kind", "artifact"))
        if kind == "document":
            kind = "artifact"
        known = {"kind", "required", "capture"}
        config = {k: v for k, v in data.items() if k not in known}
        return cls(
            id=output_id,
            kind=kind,
            required=bool(data.get("required", False)),
            capture=str(data.get("capture", "final")),
            config=config,
        )

    def to_dict(self) -> dict[str, Any]:
        data = {"kind": self.kind, "required": self.required, "capture": self.capture}
        data.update(self.config)
        return data


@dataclass(frozen=True)
class ExecutionSpec:
    mode: str = "single"
    interval: int | None = None
    window: str = ""
    skip_lunch: bool = False
    request_limit: int = 200
    max_rounds: int | None = None
    retry_limit: int = 3
    on_failure: str = "retry"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExecutionSpec":
        execution = _as_dict(raw.get("execution"), "execution")
        mode = str(execution.get("mode", raw.get("kind", "single")))
        interval = execution.get("interval", raw.get("interval"))
        return cls(
            mode=mode,
            interval=int(interval) if interval is not None else None,
            window=str(execution.get("window", raw.get("window", ""))),
            skip_lunch=bool(execution.get("skip_lunch", raw.get("skip_lunch", False))),
            request_limit=int(execution.get("request_limit", raw.get("request_limit", 200))),
            max_rounds=(int(execution["max_rounds"])
                        if execution.get("max_rounds") is not None else None),
            retry_limit=int(execution.get("retry_limit", 3)),
            on_failure=str(execution.get("on_failure", "retry")),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "mode": self.mode,
            "request_limit": self.request_limit,
            "retry_limit": self.retry_limit,
            "on_failure": self.on_failure,
        }
        if self.interval is not None:
            data["interval"] = self.interval
        if self.window:
            data["window"] = self.window
        if self.skip_lunch:
            data["skip_lunch"] = True
        if self.max_rounds is not None:
            data["max_rounds"] = self.max_rounds
        return data


@dataclass(frozen=True)
class StageSpec:
    id: str
    prompt: str
    inputs: dict[str, InputSpec] = field(default_factory=dict)
    outputs: dict[str, OutputSpec] = field(default_factory=dict)
    execution: ExecutionSpec = field(default_factory=ExecutionSpec)
    vars: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, stage_id: str, raw: Any) -> "StageSpec":
        data = _as_dict(raw, f"阶段 {stage_id}")
        inputs_raw = _as_dict(data.get("inputs"), f"阶段 {stage_id}.inputs")
        outputs_raw = _as_dict(data.get("outputs"), f"阶段 {stage_id}.outputs")
        known = {"prompt", "inputs", "outputs", "capabilities", "execution",
                 "kind", "interval", "window", "skip_lunch", "request_limit",
                 "max_rounds", "retry_limit", "on_failure", "vars"}
        return cls(
            id=stage_id,
            prompt=str(data.get("prompt", "")),
            inputs={k: InputSpec.from_dict(k, v) for k, v in inputs_raw.items()},
            outputs={k: OutputSpec.from_dict(k, v) for k, v in outputs_raw.items()},
            execution=ExecutionSpec.from_dict(data),
            vars=tuple(str(x) for x in (data.get("vars") or [])),
            metadata={k: v for k, v in data.items() if k not in known},
        )

    def contract(self) -> dict[str, Any]:
        """Return the immutable, user-facing contract snapshot for a Run."""
        return {
            "version": CONTRACT_VERSION,
            "stage": self.id,
            "prompt": self.prompt,
            "inputs": {k: v.to_dict() for k, v in self.inputs.items()},
            "outputs": {k: v.to_dict() for k, v in self.outputs.items()},
            "execution": self.execution.to_dict(),
            "vars": list(self.vars),
        }


def stage_spec(stage_id: str, raw: dict[str, Any]) -> StageSpec:
    """Public constructor used by API and engine boundaries."""
    return StageSpec.from_dict(stage_id, raw)


def normalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Normalize a manifest without changing its public JSON shape.

    The normalized manifest keeps legacy top-level execution keys for now, but
    adds a contract version and canonical nested execution block.  This makes
    the migration explicit while allowing callers that still render the old
    editor fields to continue reading the manifest.
    """
    if not isinstance(manifest, dict):
        raise ValueError("manifest 必须是对象")
    out = dict(manifest)
    raw_policy = manifest.get("policy")
    if raw_policy is not None and not isinstance(raw_policy, dict):
        raise ValueError("policy 必须是对象")
    policy = dict(raw_policy or {})
    if "web_search" not in policy and "web_search" in manifest:
        policy["web_search"] = manifest["web_search"]
    unknown_policy = set(policy) - set(POLICY_DEFAULTS)
    if unknown_policy:
        raise ValueError(f"policy 包含未知字段: {', '.join(sorted(unknown_policy))}")
    for key, default in POLICY_DEFAULTS.items():
        value = policy.get(key, default)
        if not isinstance(value, bool):
            raise ValueError(f"policy.{key} 必须是布尔值")
        policy[key] = value
    out["policy"] = policy
    out.pop("web_search", None)
    raw_stages = manifest.get("stages") or {}
    if not isinstance(raw_stages, dict):
        raise ValueError("stages 必须是对象")
    stages: dict[str, Any] = {}
    for name, raw in raw_stages.items():
        spec = StageSpec.from_dict(name, raw)
        errors = validate_stage_spec(spec, manifest)
        if errors:
            raise ValueError("; ".join(errors))
        data = dict(raw)
        data["inputs"] = {k: v.to_dict() for k, v in spec.inputs.items()}
        data["outputs"] = {k: v.to_dict() for k, v in spec.outputs.items()}
        # Stage capabilities and platform variables are intentionally not part
        # of the user contract.  They are derived from the system policy and
        # runtime envelope respectively.
        data.pop("capabilities", None)
        data["execution"] = spec.execution.to_dict()
        data["contract_version"] = CONTRACT_VERSION
        stages[name] = data
    out["stages"] = stages
    out["contract_version"] = CONTRACT_VERSION
    return out


def validate_stage_spec(spec: StageSpec, manifest: dict[str, Any]) -> list[str]:
    """Validate semantic fields that are independent of persistence."""
    errors: list[str] = []
    if not spec.prompt.strip():
        errors.append(f"{spec.id}:必须指定 Prompt")
    if spec.execution.mode not in EXECUTION_MODES:
        errors.append(f"{spec.id}:执行方式必须是 single 或 loop")
    if spec.execution.request_limit < 1:
        errors.append(f"{spec.id}:request_limit 必须是正整数")
    if spec.execution.retry_limit < 0:
        errors.append(f"{spec.id}:retry_limit 不能为负数")
    if spec.execution.mode == "loop" and spec.execution.interval is not None \
            and spec.execution.interval < 1:
        errors.append(f"{spec.id}:interval 必须是正整数")
    for input_id, item in spec.inputs.items():
        if item.kind not in INPUT_KINDS:
            errors.append(f"{spec.id}.{input_id}:阶段输入只能引用阶段产物")
        if item.selector not in SELECTORS:
            errors.append(f"{spec.id}.{input_id}:未知选择器 {item.selector}")
        if item.max_chars is not None and item.max_chars < 1000:
            errors.append(f"{spec.id}.{input_id}:max_chars 必须是至少 1000 的整数")
    for output_id, item in spec.outputs.items():
        if item.kind not in OUTPUT_KINDS:
            errors.append(f"{spec.id}.{output_id}:未知输出类型 {item.kind}")
        if item.capture not in ("final", "tool", "explicit"):
            errors.append(f"{spec.id}.{output_id}:未知捕获方式 {item.capture}")
    return errors
