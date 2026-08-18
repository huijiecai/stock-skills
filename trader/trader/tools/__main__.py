"""工具手动测试 CLI(不经 LLM,直接调函数,免费秒出)。

用法:
  uv run python -m trader.tools list                          # 列出所有工具(按文件分组+参数签名)
  uv run python -m trader.tools call get_expectations         # 调用某工具(无参)
  uv run python -m trader.tools call get_pool expectation_id=2        # 带参数
  uv run python -m trader.tools call get_quotes codes=000021,000636   # 逗号分隔=列表

注意:execute 会真实下单(写账户库),测试交易逻辑请想清楚再用。
"""

import argparse
import importlib
import inspect

# 工具注册表:文件 → 工具名(和 core/registry.py 一致)
TOOLS = {
    "market": ["get_quotes", "get_indices", "get_kline", "get_block_rank",
               "get_block_members", "get_candidates", "get_limit_up",
               "get_market_summary", "get_top_amount"],
    "scan": ["scan_market"],
    "account": ["get_positions", "get_account", "get_trades"],
    "trading": ["execute"],
    "docs": ["save_doc", "get_doc", "list_docs", "set_doc_meta"],
    "watchlist": ["save_watchlist", "get_watchlist", "get_watchlist_quotes",
                  "remove_watchlist_member"],
}


def _load(name: str):
    for mod, names in TOOLS.items():
        if name in names:
            if mod in ("market",):
                from trader.core import market as m
                return getattr(m, name)
            if mod == "scan":
                from trader.core import scan as m
                return getattr(m, name)
            if mod == "watchlist":
                from trader.core import watchlist as m
                return getattr(m, name)
            m = importlib.import_module(f"trader.tools.{mod}")
            return getattr(m, name)
    return None


def _convert(raw: str, ann) -> object:
    """按参数注解把 CLI 字符串转成正确类型。"""
    ann = str(ann)
    if "int" in ann:
        return int(raw)
    if "float" in ann:
        return float(raw)
    if "bool" in ann:
        return raw.lower() in ("1", "true", "yes")
    if "list" in ann:
        return [x for x in raw.split(",") if x]
    return raw


def _show_transcript(date: str, round_no: int, mode: str, full: bool) -> None:
    """命令行看思考流:轮指令→工具调用→返回→推理,逐步打印。"""
    import json

    from trader.core.documents import default_documents

    raw = default_documents().get(f"transcript_{mode}", name=f"r{round_no}", trade_date=date)
    if not raw:
        print(f"无 {mode} r{round_no}({date})的思考流(可能早于落盘机制)")
        return
    t = json.loads(raw)
    u = t.get("usage") or {}
    limit = 10 ** 9 if full else 500
    print(f"r{round_no} · {date} {t.get('time','')} · "
          f"{u.get('requests','?')}次请求 · 输入{u.get('input_tokens',0):,}/输出{u.get('output_tokens',0):,} tokens")
    print("─" * 60)
    for msg in t.get("messages", []):
        for part in msg.get("parts", []):
            kind = part.get("part_kind", "")
            if kind == "user-prompt":
                body = str(part.get("content", ""))
                print(f"\n📋 轮指令\n{body[:limit]}{'…' if len(body) > limit else ''}")
            elif kind == "text":
                body = str(part.get("content", ""))
                print(f"\n💬 推理/输出\n{body[:limit]}{'…' if len(body) > limit else ''}")
            elif kind == "tool-call":
                print(f"\n🔧 {part.get('tool_name')}({json.dumps(part.get('args', {}), ensure_ascii=False)})")
            elif kind == "tool-return":
                c = part.get("content", "")
                body = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
                print(f"← {body[:limit]}{'…(截断,--full 看全文)' if len(body) > limit else ''}")
            elif kind == "retry-prompt":
                print(f"\n⚠ 重试:{str(part.get('content',''))[:120]}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出所有工具(按文件分组)")
    c = sub.add_parser("call", help="调用某工具(不经 LLM)")
    c.add_argument("name", help="工具名")
    c.add_argument("kv", nargs="*", help="参数 key=value(逗号分隔表示列表)")
    t = sub.add_parser("transcript", help="命令行看某轮思考流")
    t.add_argument("date", help="交易日 YYYYMMDD")
    t.add_argument("round_no", type=int, help="轮号(如 17)")
    t.add_argument("--mode", default="live", choices=["live", "replay"], help="模式(默认 live)")
    t.add_argument("--full", action="store_true", help="不截断(默认工具返回截500字)")

    args = p.parse_args()

    if args.cmd == "list":
        for mod, names in TOOLS.items():
            print(f"\n[{mod}]")
            for n in names:
                f = _load(n)
                sig = inspect.signature(f)
                params = [x for x in sig.parameters if x != "ctx"]
                req = [x for x in params
                       if sig.parameters[x].default is inspect.Parameter.empty]
                warn = "  ⚠会真实交易" if n == "execute" else ""
                print(f"  {n}({', '.join(params)})"
                      + (f"  必填:{req}" if req else "") + warn)
        print()
        return

    if args.cmd == "transcript":
        _show_transcript(args.date, args.round_no, args.mode, args.full)
        return

    func = _load(args.name)
    if func is None:
        print(f"未知工具:{args.name}(用 list 查看全部)")
        return
    sig = inspect.signature(func)
    kwargs = {}
    for kv in args.kv:
        k, v = kv.split("=", 1)
        if k not in sig.parameters:
            print(f"参数不存在:{k}(签名:{list(sig.parameters)})")
            return
        kwargs[k] = _convert(v, sig.parameters[k].annotation)
    missing = [x for x in sig.parameters
               if x != "ctx" and sig.parameters[x].default is inspect.Parameter.empty
               and x not in kwargs]
    if missing:
        print(f"缺少必填参数:{missing}")
        return
    print(f"→ {args.name}({kwargs})\n")
    print(func(ctx=None, **kwargs))


if __name__ == "__main__":
    main()
