"""api·工具目录与试运行:prompt 作者的"API 文档 + 调试台"(设计:docs/Prompt编辑器IDE化设计讨论.md)。

- GET /tools:自省注册表出目录(签名/说明/写操作标记)+ 测试账号名下组合
- POST /tools/{name}/call:试运行——一律挂测试账号上下文(owner/登录用户的数据物理不可达),
  登录用户是谁无关紧要;写工具也只写测试账号组合
"""
import inspect
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core.context import set_context
from trader.core.db import _connect
from trader.core.portfolios import default_portfolios
from trader.core.registry import TOOLS, TOOL_GROUPS, WRITE_TOOLS

router = APIRouter(prefix="/tools", tags=["tools"])

TEST_USER_ENV = "TOOL_TEST_USER"   # 试运行测试账号(默认 3=api-test@test.io,数据最全)
_OUTPUT_CAP = 8000                 # 返回截断长度(完整返回落 transcript,调试够用)


def _test_user_id() -> int:
    return int(os.environ.get(TEST_USER_ENV, "3"))


def _group_of(name: str) -> str:
    return next((g for g, names in TOOL_GROUPS.items() if name in names), "other")


def _params_of(fn) -> list[dict]:
    sig = inspect.signature(fn)
    out = []
    for pname, p in sig.parameters.items():
        if pname == "ctx":          # pydantic_ai 占位参数,LLM/作者都不需要
            continue
        out.append({
            "name": pname,
            "type": str(p.annotation) if p.annotation is not inspect.Parameter.empty else "str",
            "required": p.default is inspect.Parameter.empty,
            "default": None if p.default is inspect.Parameter.empty else p.default,
        })
    return out


def _coerce(pname: str, val, ann: str):
    """JSON 值按参数注解矫正(表单传来常是字符串;list 接受数组或逗号分隔)。"""
    try:
        if "list" in ann:
            if isinstance(val, list):
                return val
            return [x for x in str(val).split(",") if x]
        if "int" in ann:
            return int(val)
        if "float" in ann:
            return float(val)
        if "bool" in ann:
            return val if isinstance(val, bool) else str(val).lower() in ("1", "true", "yes")
        return str(val)
    except (TypeError, ValueError):
        raise HTTPException(400, f"参数 {pname} 类型不符(期望 {ann}):{val!r}")


def _test_portfolios(uid: int) -> list[dict]:
    """测试账号名下组合(+有无持仓,试运行默认挑一个有数据的)。"""
    ports = default_portfolios().list(uid)
    ids = [p["id"] for p in ports]
    held: dict[int, int] = {}
    if ids:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT portfolio_id, count(*) AS n FROM positions"
                " WHERE quantity > 0 AND portfolio_id = ANY(%s) GROUP BY portfolio_id",
                (ids,)).fetchall()
        held = {r["portfolio_id"]: r["n"] for r in rows}
    for p in ports:
        p["has_positions"] = held.get(p["id"], 0) > 0
    return ports


class CallIn(BaseModel):
    args: dict = {}
    portfolio_id: int | None = None


@router.get("")
def tools_catalog(who: dict = Depends(require_user)):
    """工具目录:注册表自省(签名+docstring 即 LLM 看到的工具说明)。"""
    tools = []
    for name, fn in TOOLS.items():
        doc = inspect.getdoc(fn) or ""
        tools.append({
            "name": name, "group": _group_of(name), "write": name in WRITE_TOOLS,
            "desc": doc.splitlines()[0] if doc else "",
            "doc": doc,
            "params": _params_of(fn),
        })
    tools.sort(key=lambda t: (t["group"], t["name"]))
    uid = _test_user_id()
    with _connect() as conn:
        user = conn.execute("SELECT id, display_name FROM users WHERE id=%s",
                            (uid,)).fetchone()
    return {"tools": tools,
            "portfolios": _test_portfolios(uid),
            "test_user": {"id": uid,
                          "display_name": (user or {}).get("display_name") or f"#{uid}"}}


@router.post("/{name}/call")
def tool_call(name: str, body: CallIn, who: dict = Depends(require_user)):
    """工具试运行:不经 LLM 直调函数,返回就是 LLM 会看到的字符串。
    强制挂测试账号(TOOL_TEST_USER,默认 3);登录用户/owner 的组合不可达。"""
    fn = TOOLS.get(name)
    if fn is None:
        raise HTTPException(404, f"未知工具:{name}(GET /tools 查看目录)")
    params = {p["name"]: p for p in _params_of(fn)}
    unknown = [k for k in body.args if k not in params]
    if unknown:
        raise HTTPException(400, f"参数不存在:{unknown}(签名:{list(params)})")
    missing = [n for n, p in params.items() if p["required"] and n not in body.args]
    if missing:
        raise HTTPException(400, f"缺少必填参数:{missing}")
    args = {k: _coerce(k, v, params[k]["type"]) for k, v in body.args.items()}

    uid = _test_user_id()
    ports = _test_portfolios(uid)
    owned = {p["id"] for p in ports}
    if body.portfolio_id is not None and body.portfolio_id not in owned:
        raise HTTPException(403, f"组合 #{body.portfolio_id} 不属于测试账号(#{uid}),不可用于试运行")
    portfolio_id = body.portfolio_id or next(
        (p["id"] for p in ports if p["has_positions"]),
        default_portfolios().default_for(uid))
    set_context(portfolio_id, None, uid)

    output = fn(ctx=None, **args)
    truncated = len(output) > _OUTPUT_CAP
    return {
        "name": name, "args": args, "portfolio": portfolio_id,
        "output": output[:_OUTPUT_CAP] + ("\n…(截断,共 %d 字)" % len(output) if truncated else ""),
        "truncated": truncated,
        "write_warning": (f"写操作已落在测试账号组合 #{portfolio_id},不影响任何真实账户"
                          if name in WRITE_TOOLS else None),
    }
