"""阶段输入输出契约:manifest 声明关系,engine 负责解析和持久化。

这里只管理阶段产物(计划、轮次判断、复盘报告)的衔接。预期文档、自选组等
业务知识仍由各系统通过通用工具按需读写,不强行纳入阶段依赖。
"""
from __future__ import annotations

import re
from string import Formatter

from trader.core.documents import Documents, default_documents


def validate_stage_contracts(manifest: dict) -> list[str]:
    """校验 manifest 中的阶段 I/O 引用；供 API 保存边界和其他客户端复用。"""
    errors: list[str] = []
    stages = manifest.get("stages") or {}
    if not isinstance(stages, dict):
        return ["stages 必须是对象"]
    for stage_name, stage in stages.items():
        if not isinstance(stage_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", stage_name):
            errors.append(f"{stage_name}:阶段标识格式无效")
        if not isinstance(stage, dict):
            errors.append(f"{stage_name}:阶段定义必须是对象")
            continue
        if not str(stage.get("prompt") or "").strip():
            errors.append(f"{stage_name}:必须指定 Prompt")
        if stage.get("kind", "single") not in ("single", "loop"):
            errors.append(f"{stage_name}:执行方式必须是 single 或 loop")
        outputs = stage.get("outputs") or {}
        if not isinstance(outputs, dict):
            errors.append(f"{stage_name}:outputs 必须是对象")
            outputs = {}
        for output_id, spec in outputs.items():
            if not isinstance(output_id, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", output_id):
                errors.append(f"{stage_name}.{output_id}:输出标识格式无效")
            if not isinstance(spec, dict):
                errors.append(f"{stage_name}.{output_id}:输出定义必须是对象")
                continue
            if spec.get("kind", "document") != "document":
                errors.append(f"{stage_name}.{output_id}:目前只支持文档输出")
            if not str(spec.get("doc_type") or "").strip():
                errors.append(f"{stage_name}.{output_id}:必须填写 doc_type")
        inputs = stage.get("inputs") or {}
        if not isinstance(inputs, dict):
            errors.append(f"{stage_name}:inputs 必须是对象")
            continue
        for input_id, spec in inputs.items():
            if not isinstance(input_id, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", input_id):
                errors.append(f"{stage_name}.{input_id}:输入标识格式无效")
            if not isinstance(spec, dict):
                errors.append(f"{stage_name}.{input_id}:输入定义必须是对象")
                continue
            try:
                _source_output(manifest, input_id, spec)
            except RuntimeError as e:
                errors.append(f"{stage_name}.{input_id}:{e}")
            selector = spec.get("selector", "latest")
            if selector not in ("latest", "previous", "recent", "all"):
                errors.append(f"{stage_name}.{input_id}:未知选择器 {selector}")
            if selector in ("previous", "recent"):
                try:
                    if int(spec.get("limit", 1)) < 1:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(f"{stage_name}.{input_id}:limit 必须是正整数")
            try:
                if spec.get("max_chars") is not None and int(spec["max_chars"]) < 1000:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"{stage_name}.{input_id}:max_chars 必须是至少 1000 的整数")
    return errors


def stage_contract(stage_name: str, stage: dict) -> dict:
    """生成可冻结到 Run 封面的最小契约快照。"""
    return {
        "stage": stage_name,
        "inputs": dict(stage.get("inputs") or {}),
        "outputs": dict(stage.get("outputs") or {}),
    }


def primary_output(stage: dict) -> tuple[str, dict] | None:
    """返回第一个自动捕获最终回答的文档输出。"""
    for output_id, spec in (stage.get("outputs") or {}).items():
        if spec.get("kind", "document") == "document" and spec.get("capture", "final") == "final":
            return output_id, spec
    return None


def loop_output_type(stage: dict, fallback: str) -> str:
    """循环断点使用声明输出的存储类型;旧 manifest 继续认 log_type。"""
    out = primary_output(stage)
    return out[1].get("doc_type", fallback) if out else stage.get("log_type", fallback)


def load_stage_inputs(manifest: dict, stage_name: str, variables: dict,
                      docs: Documents | None = None) -> str:
    """解析 Stage 的声明输入,记录精确文档边并生成模型上下文。

    required 缺失直接阻止执行;optional 缺失会显式告诉模型,避免模型假装读过。
    """
    docs = docs or default_documents()
    stage = (manifest.get("stages") or {}).get(stage_name) or {}
    blocks: list[str] = []
    for input_id, spec in (stage.get("inputs") or {}).items():
        source_stage, output_id, output = _source_output(manifest, input_id, spec)
        entries = _select_entries(docs, output, spec, variables)
        if not entries:
            if spec.get("required", False):
                raise RuntimeError(
                    f"阶段 {stage_name} 缺少必需输入 {input_id}"
                    f"(来源 {source_stage}.{output_id})"
                )
            blocks.append(_input_header(input_id, spec, source_stage, output_id)
                          + "\n(未找到可用内容)")
            continue

        parts = []
        for entry in entries:
            docs.link_run(entry["id"], "input", stage=stage_name, slot=input_id,
                          source_stage=source_stage, source_output=output_id)
            tag = entry.get("name") or entry.get("trade_date") or f"文档 {entry['id']}"
            parts.append(f"#### {tag}\n{entry['content']}")
        content = "\n\n".join(parts)
        max_chars = int(spec.get("max_chars", 24000))
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n(内容超过阶段输入上限,已截断)"
        blocks.append(_input_header(input_id, spec, source_stage, output_id)
                      + "\n" + content)

    if not blocks:
        return ""
    return "## 平台提供的阶段上下文\n\n" + "\n\n".join(blocks)


def publish_stage_outputs(stage_name: str, stage: dict, variables: dict, content: str,
                          docs: Documents | None = None) -> list[dict]:
    """把模型最终回答发布到声明的文档输出,并记录 Stage/Output 血缘。"""
    docs = docs or default_documents()
    published = []
    for output_id, spec in (stage.get("outputs") or {}).items():
        if spec.get("kind", "document") != "document" or spec.get("capture", "final") != "final":
            continue
        doc_type = _required_render(spec, "doc_type", variables, output_id)
        name = _render(spec.get("name", ""), variables)
        trade_date = _render(spec.get("trade_date", ""), variables) or None
        existing = docs.resolve(doc_type, name=name, trade_date=trade_date or "")
        if existing and docs.linked_in_current_round(existing["id"], "output"):
            # 钉住的旧 Prompt 可能已用 save_doc 写了完整正文;只补契约身份,不拿
            # 模型最后的简短回复覆盖它。
            doc_id = existing["id"]
        else:
            doc_id = docs.save(
                doc_type,
                str(content),
                name=name,
                trade_date=trade_date,
                meta={"stage": stage_name, "output": output_id},
            )
        docs.link_run(doc_id, "output", stage=stage_name, slot=output_id)
        published.append({"id": doc_id, "output": output_id, "doc_type": doc_type,
                          "name": name, "trade_date": trade_date})
    return published


def inject_stage_context(prompt: str, context: str) -> str:
    """上下文放在本轮指令前,边界清楚且会随 transcript 留证。"""
    if not context:
        return prompt
    return context + "\n\n---\n\n" + prompt


def _source_output(manifest: dict, input_id: str, spec: dict) -> tuple[str, str, dict]:
    source = spec.get("from") or {}
    if isinstance(source, str):
        if "." not in source:
            raise RuntimeError(f"输入 {input_id} 的 from 必须是 stage.output")
        source_stage, output_id = source.split(".", 1)
    else:
        source_stage, output_id = source.get("stage", ""), source.get("output", "")
    stages = manifest.get("stages") or {}
    output = ((stages.get(source_stage) or {}).get("outputs") or {}).get(output_id)
    if not source_stage or not output_id or output is None:
        raise RuntimeError(f"输入 {input_id} 引用了不存在的阶段输出 {source_stage}.{output_id}")
    if output.get("kind", "document") != "document":
        raise RuntimeError(f"输入 {input_id} 暂不支持非文档输出 {source_stage}.{output_id}")
    return source_stage, output_id, output


def _select_entries(docs: Documents, output: dict, input_spec: dict,
                    variables: dict) -> list[dict]:
    doc_type = _required_render(output, "doc_type", variables, "source")
    trade_date = _render(input_spec.get("trade_date", output.get("trade_date", "")), variables)
    name_template = output.get("name", "")
    rows = docs.list(doc_type, trade_date or None)
    rows = [r for r in rows if _name_matches(r.get("name") or "", name_template, variables)]
    rows.sort(key=_entry_order, reverse=True)

    selector = input_spec.get("selector", "latest")
    if selector in ("recent", "previous"):
        rows = rows[:max(1, int(input_spec.get("limit", 1)))]
        rows.reverse()  # 注入时按时间正序,便于模型恢复演进过程
    elif selector == "all":
        rows.reverse()
    elif selector == "latest":
        rows = rows[:1]
    else:
        raise RuntimeError(f"未知输入选择器:{selector}")

    out = []
    for row in rows:
        entry = docs.resolve_id(row["id"])
        if entry:
            out.append(entry)
    return out


def _entry_order(row: dict) -> tuple[int, str, int]:
    name = row.get("name") or ""
    round_no = int(name[1:]) if name.startswith("r") and name[1:].isdigit() else -1
    return round_no, row.get("updated_at") or "", int(row.get("id") or 0)


def _name_matches(name: str, template: str, variables: dict) -> bool:
    fields = [field for _, field, _, _ in Formatter().parse(template) if field]
    if not fields:
        return name == _render(template, variables)
    pattern = ""
    for literal, field, _, _ in Formatter().parse(template):
        pattern += re.escape(literal)
        if field:
            pattern += r".+"
    return re.fullmatch(pattern, name) is not None


def _input_header(input_id: str, spec: dict, source_stage: str, output_id: str) -> str:
    label = spec.get("label") or input_id
    required = "必需" if spec.get("required", False) else "可选"
    return f"### {label} (`{input_id}`, {required})\n来源:`{source_stage}.{output_id}`"


def _required_render(spec: dict, key: str, variables: dict, output_id: str) -> str:
    value = _render(spec.get(key, ""), variables)
    if not value:
        raise RuntimeError(f"阶段输出 {output_id} 缺少 {key}")
    return value


def _render(value, variables: dict) -> str:
    if value is None:
        return ""
    try:
        return str(value).format(**variables)
    except KeyError as e:
        raise RuntimeError(f"阶段契约占位符 {e} 没有运行时变量") from None
