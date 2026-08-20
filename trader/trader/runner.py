"""运行器:CLI 薄壳(实现设计 §9)。

旧五命令 = expectation 系统对应阶段的兼容别名(守护脚本/README 用法不变);
通用命令 run <system> <stage> 跑任何系统。全部逻辑在 core.engine。
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="看盘循环运行器(平台版)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="通用:跑某系统某阶段(任何注册的系统)")
    r.add_argument("system", help="系统名(systems 表,如 expectation)")
    r.add_argument("stage", help="阶段名(如 premarket/live/replay/close/research)")
    r.add_argument("--date", default="", help="交易日 YYYYMMDD(loop/single 通用)")
    r.add_argument("--topic", default="", help="research 主题")
    r.add_argument("--user", default="", help="用户邮箱或 id(默认 user 0=所有者)")

    p = sub.add_parser("replay", help="模拟看盘(一场一袋,开局三模式)")
    p.add_argument("date", help="回放日期 YYYYMMDD(需已同步行情)")
    p.add_argument("--interval", type=int, default=5, help="每轮步进分钟(默认 5)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")
    p.add_argument("--user", default="", help="用户邮箱或 id(默认 user 0=所有者)")
    p.add_argument("--resume", action="store_true", help="接续该日最近一场回放")
    p.add_argument("--tag", default="", help="场次命名(同日同名拒绝;缺省用时间戳)")
    p.add_argument("--opening", choices=["fresh", "fork", "fork-as-of", "custom"],
                   default="fresh", help="开局模式(实现设计 §6,默认 fresh)")
    p.add_argument("--as-of", default="", help="fork-as-of 的截至日 YYYYMMDD")
    p.add_argument("--custom", default="", help="custom 开局的 JSON 文件路径")

    p2 = sub.add_parser("replay-rm", help="删除某场回放(袋子整体销毁,显式操作)")
    p2.add_argument("name", help="场次名(replay-ls 查看)")
    p2.add_argument("--user", default="", help="用户邮箱或 id(默认 user 0=所有者)")

    p3 = sub.add_parser("replay-ls", help="列出回放场次")
    p3.add_argument("--date", default="", help="按日期过滤 YYYYMMDD")
    p3.add_argument("--user", default="", help="用户邮箱或 id(默认 user 0=所有者)")

    p = sub.add_parser("premarket", help="盘前分析(八维催化→预期更新→场景推演→预案)")
    p.add_argument("date", help="目标交易日 YYYYMMDD")
    p.add_argument("prev_date", nargs="?", default=None, help="上一交易日(自动推算)")
    p.add_argument("--user", default="", help="用户邮箱或 id(默认 user 0=所有者)")

    p = sub.add_parser("close", help="盘后总结(预期更新+逐股扫描+复盘+合规)")
    p.add_argument("--user", default="", help="用户邮箱或 id(默认 user 0=所有者)")
    p.add_argument("date", help="交易日 YYYYMMDD")

    p = sub.add_parser("research", help="预期研究(联网归因→写入预期库)")
    p.add_argument("topic", help="研究主题")
    p.add_argument("--user", default="", help="用户邮箱或 id(默认 user 0=所有者)")

    p = sub.add_parser("live", help="实时看盘")
    p.add_argument("--sleep", type=int, default=0, help="轮间等待秒(默认 0)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")

    args = parser.parse_args()
    from trader.core import engine
    from trader.core.identity import resolve_user
    uid = resolve_user(getattr(args, "user", None))

    if args.cmd == "run":
        if args.stage in ("live", "replay"):
            (engine.run_live if args.stage == "live" else engine.run_replay)(
                args.system, user_id=uid,
                **({"date": args.date} if args.date else {}))  # type: ignore[arg-type]
        else:
            engine.run_single(args.system, args.stage, user_id=uid,
                              date=args.date, topic=args.topic)
    elif args.cmd == "replay":
        engine.run_replay("expectation", args.date, interval=args.interval,
                          max_rounds=args.max_rounds, resume=args.resume, tag=args.tag,
                          opening=args.opening, custom_file=args.custom, as_of=args.as_of,
                          user_id=uid)
    elif args.cmd == "replay-rm":
        from trader.core.runs import default_runs
        n = default_runs().delete(args.name, user_id=uid)
        print(f"已删除场次 {args.name}(组合整体销毁)" if n else f"没有这个场次:{args.name}")
    elif args.cmd == "replay-ls":
        from tabulate import tabulate
        from trader.core.runs import default_runs
        rows = default_runs().list(kind="replay", trade_date=args.date or None, user_id=uid)
        print(tabulate([[r["id"], r["slug"], r["status"], r.get("portfolio_id"),
                         (r.get("fingerprint") or "")[:8],
                         (r["prompt_versions"] or "")[:40], r["created_at"][:16]] for r in rows],
                       headers=["#", "场次", "状态", "组合", "指纹", "prompt版本", "建档"],
                       tablefmt="plain") if rows else "(没有回放场次)")
    elif args.cmd == "premarket":
        engine.run_single("expectation", "premarket", user_id=uid,
                          date=args.date, prev=args.prev_date)
    elif args.cmd == "close":
        engine.run_single("expectation", "close", user_id=uid, date=args.date)
    elif args.cmd == "research":
        engine.run_single("expectation", "research", user_id=uid, topic=args.topic)
    else:
        engine.run_live("expectation", sleep_seconds=args.sleep,
                        max_rounds=args.max_rounds, user_id=uid)


if __name__ == "__main__":
    main()
