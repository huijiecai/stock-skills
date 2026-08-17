"""文档工具(AI 调用):save_doc / get_doc / list_docs。

通用 md 内容存储:盘前报告(premarket)/研究过程(research,ref_id 挂预期)/盘后总结(close)/笔记(note)。
prompt 不走这里(用 prompts/ 文件,稳定后再迁)。
"""

from pydantic_ai import RunContext
from tabulate import tabulate

from trader.store import default_documents


def save_doc(ctx: RunContext[None], doc_type: str, content: str, name: str = "",
             trade_date: str = "", ref_id: int = 0) -> str:
    """保存/更新文档(同 doc_type+name+trade_date 覆盖)。
    doc_type: premarket(盘前报告,配 trade_date)/ research(研究过程,配 ref_id 挂预期)/
    close(盘后总结,配 trade_date)/ watch_live 或 watch_replay(盘中轮日志,
    name='r轮号' 如 r7,配 trade_date)/ note(笔记,配 name)。content 是 md 全文。
    """
    doc_id = default_documents().save(
        doc_type, content, name=name, trade_date=trade_date or None, ref_id=ref_id or None
    )
    label = "/".join(x for x in [doc_type, name or None, trade_date or None] if x)
    return f"已保存文档 #{doc_id}({label},{len(content)}字)"


def get_doc(ctx: RunContext[None], doc_type: str, name: str = "", trade_date: str = "") -> str:
    """读文档全文。无则明确提示。"""
    content = default_documents().get(doc_type, name=name, trade_date=trade_date)
    if content is None:
        if doc_type == "premarket":
            return (f"⚠ 当日({trade_date or '今日'})**没有盘前预案**——今天按方法论自主决策,"
                    f"禁止引用其他日期的预案,禁止编造'预案里说过'。")
        return f"无 {doc_type} 文档(name={name or '-'}, date={trade_date or '-'})"
    return content


def list_docs(ctx: RunContext[None], doc_type: str = "", trade_date: str = "") -> str:
    """列出文档概览(id/类型/名称/日期/字数/更新时间);doc_type/trade_date 可过滤。
    看"今天看到第几轮"用: list_docs(doc_type='watch_live', trade_date='20260817')"""
    data = default_documents().list(doc_type or None, trade_date or None)
    if not data:
        return "文档库为空"
    rows = [[d["id"], d["doc_type"], d["name"] or "-", d["trade_date"] or "-",
             d["ref_id"] or "-", d["size"], d["updated_at"][:16]] for d in data]
    return tabulate(rows, headers=["id", "类型", "名称", "日期", "ref", "字数", "更新"],
                    tablefmt="plain")
