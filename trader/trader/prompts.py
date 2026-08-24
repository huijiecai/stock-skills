"""指令管理:PG 版本库是平台唯一正本。

- load(slug, system_id, **vars):读该系统命名空间的最新版并替换 {var} 占位
- CLI versions/diff:查看 expectation 系统的指令版本和版本差异
"""

import argparse
import difflib


def _expectation_system_id() -> int:
    """返回公共 expectation 系统 id，供版本查询 CLI 使用。"""
    from trader.core.systems import default_systems

    row = default_systems().get("expectation", user_id=0)
    if row is None:
        from trader.core.systems import ensure_expectation_system
        row = ensure_expectation_system(user_id=0)
    return row["id"]


def load(slug: str, system_id: int, user_id: int = 0,
         prompt_version: int | None = None, **variables: str) -> str:
    """读指令:PG 版本库该系统命名空间的最新版(或指定版)。
    {var} 占位用 variables 替换;占位符缺变量时明确报错。
    PG 是唯一正本。"""
    from trader.core.promptver import default_prompt_versions

    pv = default_prompt_versions()
    pg_text = (pv.get(system_id, slug, prompt_version, user_id=user_id)
               if prompt_version is not None
               else pv.latest(system_id, slug, user_id=user_id))
    if pg_text is None:
        suffix = f" v{prompt_version}" if prompt_version is not None else ""
        raise RuntimeError(f"指令 '{slug}'{suffix} 不存在")
    if not variables:
        return pg_text
    try:
        return pg_text.format(**variables)
    except KeyError as e:
        raise RuntimeError(
            f"指令 '{slug}' 有占位符 {e} 但调用方没传"
            f"(传了:{sorted(variables)})——先停进程再改 prompt,或补齐调用方参数"
        ) from None


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("versions", help="版本列表(slug 省略=expectation 全部指令各显最新版)")
    v.add_argument("slug", nargs="?", default="")
    d = sub.add_parser("diff", help="两版对比")
    d.add_argument("slug")
    d.add_argument("v1", type=int)
    d.add_argument("v2", type=int)
    args = parser.parse_args()

    from trader.core.promptver import default_prompt_versions

    pv = default_prompt_versions()
    system_id = _expectation_system_id()
    if args.cmd == "versions":
        from tabulate import tabulate
        rows = pv.versions(system_id, args.slug) if args.slug else [
            r for s in pv.list_prompts(system_id)
            for r in pv.versions(system_id, s["slug"])]
        if not rows:
            print("无版本")
            return
        print(tabulate([[r["version"], r["size"], r["created_at"][:16]] for r in rows],
                       headers=["版本", "字数", "时间"], tablefmt="plain"))
    else:
        a = pv.get(system_id, args.slug, args.v1)
        b = pv.get(system_id, args.slug, args.v2)
        if a is None or b is None:
            print("版本不存在")
            return
        diff = difflib.unified_diff(a.splitlines(), b.splitlines(),
                                    lineterm="", n=1,
                                    fromfile=f"{args.slug} v{args.v1}",
                                    tofile=f"{args.slug} v{args.v2}")
        print("\n".join(diff) or "(两版内容一致)")


if __name__ == "__main__":
    _main()
