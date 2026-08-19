"""api·认证依赖:平台 API 的守门人(服务化设计 §2 铁律)。

一切端点挂 require_user——token(session 或 sk- API Key)→ user,查不到 401。
顺手把袋子上下文切到该用户的默认账本,下游 store 调用自动隔离。
"""
from fastapi import Depends, HTTPException, Request

from trader.core.context import set_context
from trader.core.identity import default_identity
from trader.core.ledger import default_ledgers


def _bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "缺少 Bearer token")
    return auth.removeprefix("Bearer ").strip()


def require_user(request: Request) -> dict:
    """token(session 优先,其次 sk- Key)→ 用户行;失败 401。"""
    idt = default_identity()
    token = _bearer(request)
    who = idt.resolve_session(token) or {}
    user = idt.get_user(who.get("email", "")) if who else None
    scope = "write"
    if user is None:
        key = idt.resolve_api_key(token)
        if key is None:
            raise HTTPException(401, "token 无效或已吊销")
        scope = key["scope"]
        from trader.core.db import _connect
        with _connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE id=%s", (key["user_id"],)).fetchone()
    # 切上下文到该用户默认账本(下游读写自动带上 user+bag)
    set_context(default_ledgers().default_bag(user["id"]), None, user["id"])
    return {"user": dict(user), "scope": scope}


def require_admin(who: dict = Depends(require_user)) -> dict:
    if not who["user"].get("is_admin"):
        raise HTTPException(403, "仅管理员")
    return who
