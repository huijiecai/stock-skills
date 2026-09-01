"""api·认证端点:注册/登录/登出/我(多用户设计 §3.1)。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.api.schemas import Envelope, LoginOut, LogoutOut, OkOut, RegisterOut, UserOut
from trader.core.identity import default_identity

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/register", response_model=Envelope[RegisterOut])
def register(body: RegisterIn):
    try:
        u = default_identity().create_user(body.email, body.password, body.display_name)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(409, str(e))
    return Envelope(data={"id": u["id"], "email": u["email"], "display_name": u["display_name"]})


@router.post("/login", response_model=Envelope[LoginOut])
def login(body: LoginIn):
    u = default_identity().verify_login(body.email, body.password)
    if u is None:
        from fastapi import HTTPException
        raise HTTPException(401, "邮箱或密码错误")
    token = default_identity().open_session(u["id"], days=30)
    return Envelope(data={"token": token, "user": {"id": u["id"], "email": u["email"],
                                                    "display_name": u["display_name"],
                                                    "is_admin": u["is_admin"]}})


@router.get("/me", response_model=Envelope[UserOut])
def me(who: dict = Depends(require_user)):
    return Envelope(data=who["user"])


@router.post("/logout", response_model=Envelope[LogoutOut])
def logout(who: dict = Depends(require_user)):
    # 会话吊销由前端携带原 token 调用;sk- Key 不在此管理
    return Envelope(data={"ok": True, "note": "会话吊销请用 /auth/logout-token(带原 token)"})


@router.post("/logout-token", response_model=Envelope[OkOut])
def logout_token(body: dict, who: dict = Depends(require_user)):
    default_identity().revoke_session(body.get("token", ""))
    return Envelope(data={"ok": True})
