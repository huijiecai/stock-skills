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

# 工具注册表:文件 → 工具名(和 agent.py 注册的一致)
TOOLS = {
    "market": ["get_quotes", "get_indices", "get_kline", "get_block_rank",
               "get_block_members", "get_candidates", "get_limit_up",
               "get_market_summary", "get_top_amount"],
    "watch": ["scan_market"],
    "account": ["get_positions", "get_account"],
    "trading": ["execute"],
    "knowledge": ["get_expectations", "get_pool", "add_expectation",
                  "add_pool_member", "remove_pool_member", "update_expectation"],
    "docs": ["save_doc", "get_doc", "list_docs"],
}


def _load(name: str):
    for mod, names in TOOLS.items():
        if name in names:
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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="列出所有工具(按文件分组)")
    c = sub.add_parser("call", help="调用某工具(不经 LLM)")
    c.add_argument("name", help="工具名")
    c.add_argument("kv", nargs="*", help="参数 key=value(逗号分隔表示列表)")

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
