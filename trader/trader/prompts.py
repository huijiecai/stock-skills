"""prompt 管理:本地 md 是唯一编辑面,变更同步 PG 管版本。

- load(name, **vars):运行时读文件并替换 {var} 占位(不变)
- sync_prompts():把 prompts/*.md 的变更存入 PG prompt_versions
  (同 hash 跳过,变了存新版本)——runner 每次启动自动调,也可手动:
  uv run python -m trader.prompts sync      # 手动同步
  uv run python -m trader.prompts versions [name]  # 版本列表
  uv run python -m trader.prompts diff name v1 v2  # 两版对比
"""

import argparse
import difflib
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load(name: str, user_id: int = 0, **variables: str) -> str:
    """读 prompt:PG 版本库最新版是运行时正本(按 user 命名空间,多用户设计 §4-4)。
    本地 md 是 user 0(平台所有者)的编辑面——内容与 PG 不一致时自动入库再读
    (md 最终退役,实现设计附录 8);其他用户的 prompt 只存在于 PG。
    {var} 占位用 variables 替换;占位符缺变量时明确报错。"""
    from trader.core.promptver import default_prompt_versions

    pv = default_prompt_versions()
    pg_text = pv.latest(name, user_id)
    path = PROMPTS_DIR / f"{name}.md"
    file_text = (path.read_text(encoding="utf-8")
                 if user_id == 0 and path.exists() else None)
    if file_text is not None and file_text != pg_text:
        pv.save(name, file_text)  # 编辑面有变更 → 入库后生效
        pg_text = file_text
    if pg_text is None:
        raise RuntimeError(f"prompt '{name}' 既不在 PG 版本库,也不在 {PROMPTS_DIR}")
    if not variables:
        return pg_text
    try:
        return pg_text.format(**variables)
    except KeyError as e:
        raise RuntimeError(
            f"prompt '{name}' 有占位符 {e} 但调用方没传"
            f"(传了:{sorted(variables)})——先停进程再改 prompt,或补齐调用方参数"
        ) from None


def sync_prompts(prompts_dir: Path | None = None, pv=None) -> list[dict]:
    """把 prompts/*.md 同步进 PG 版本库。返回每个文件的同步结果。
    pv 可注入隔离实例(测试用),默认 public 版本库。"""
    from trader.core.promptver import default_prompt_versions

    pv = pv or default_prompt_versions()
    return [pv.save(f.stem, f.read_text(encoding="utf-8"))
            for f in sorted((prompts_dir or PROMPTS_DIR).glob("*.md"))]


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="手动同步本地 md → PG")
    v = sub.add_parser("versions", help="版本列表(name 省略=全部 prompt 各显最新版)")
    v.add_argument("name", nargs="?", default="")
    d = sub.add_parser("diff", help="两版对比")
    d.add_argument("name")
    d.add_argument("v1", type=int)
    d.add_argument("v2", type=int)
    args = parser.parse_args()

    from trader.core.promptver import default_prompt_versions

    pv = default_prompt_versions()
    if args.cmd == "sync":
        for r in sync_prompts():
            mark = f"→ v{r['version']} 新版本" if r["changed"] else f"v{r['version']} 未变"
            print(f"  {r['name']:14s} {mark}")
    elif args.cmd == "versions":
        from tabulate import tabulate
        rows = pv.versions(args.name or None)
        if not rows:
            print("无版本(先 sync)")
            return
        print(tabulate([[r["name"], r["version"], r["size"], r["created_at"][:16]]
                        for r in rows],
                       headers=["prompt", "最新版", "字数", "时间"], tablefmt="plain"))
    else:
        a, b = pv.get(args.name, args.v1), pv.get(args.name, args.v2)
        if a is None or b is None:
            print("版本不存在")
            return
        diff = difflib.unified_diff(a.splitlines(), b.splitlines(),
                                    lineterm="", n=1,
                                    fromfile=f"{args.name} v{args.v1}",
                                    tofile=f"{args.name} v{args.v2}")
        print("\n".join(diff) or "(两版内容一致)")


if __name__ == "__main__":
    _main()
