"""core·身份与访问(平台通用件):三层认证的表与操作(多用户设计 §3.1)。

① identities 登录凭据:password(邮箱+scrypt)起步,GitHub/手机号=加 provider 行
② sessions 登录态:M1.5 登录端点上线时启用
③ api_keys 程序通行证:sk- 前缀,哈希存储,可命名/吊销/配额

密码用 stdlib 的 scrypt(不引新依赖);格式 "scrypt$<salt-hex>$<hash-hex>"。
一切"证明你是你"最终归结为:查表得到 user_id。
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from trader.core.db import _connect, ensure_once

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password: str, salt: str | None = None) -> str:
    """scrypt 哈希;格式 scrypt$salt$hash(盐随机生成,存进串里自包含)。"""
    salt = salt or secrets.token_hex(16)
    h = hashlib.scrypt(password.encode(), salt=salt.encode(),
                       n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
    return f"scrypt${salt}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$", 2)
        return secrets.compare_digest(hash_password(password, salt), stored)
    except Exception:  # noqa: BLE001 —— 格式坏=校验失败
        return False


def new_api_key() -> tuple[str, str]:
    """生成一把平台 key:返回 (明文, 只显示这一次, 哈希)。"""
    plain = "sk-" + secrets.token_urlsafe(32)
    return plain, _key_hash(plain)


def _key_hash(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


class Identity:
    """users / identities / sessions / api_keys 四表与配套操作。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        ensure_once(f"identity:{schema}", self._init_db)

    # ── 用户与登录凭据 ────────────────────────────────

    def create_user(self, email: str, password: str, display_name: str = "",
                    is_admin: bool = False) -> dict:
        """注册:邮箱即用户名(D9);密码 scrypt 哈希。邮箱已存在→ValueError。"""
        import psycopg
        now = datetime.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            try:
                u = conn.execute(
                    "INSERT INTO users(email, display_name, is_admin, created_at)"
                    " VALUES(%s,%s,%s,%s) RETURNING *",
                    (email.strip().lower(), display_name or email.split("@")[0],
                     is_admin, now)).fetchone()
            except psycopg.errors.UniqueViolation as e:
                raise ValueError(f"邮箱已注册:{email}") from e
            conn.execute(
                "INSERT INTO identities(user_id, provider, identifier, credential_hash, created_at)"
                " VALUES(%s,'password',%s,%s,%s)",
                (u["id"], email.strip().lower(), hash_password(password), now))
        return u

    def get_user(self, email: str) -> dict | None:
        with _connect(self.schema) as conn:
            return conn.execute("SELECT * FROM users WHERE email=%s",
                                (email.strip().lower(),)).fetchone()

    def get_user_by_id(self, user_id: int) -> dict | None:
        with _connect(self.schema) as conn:
            return conn.execute("SELECT * FROM users WHERE id=%s",
                                (user_id,)).fetchone()

    def verify_login(self, email: str, password: str) -> dict | None:
        """密码登录:成功返回用户行,失败 None(密码错与用户不存在同响应)。"""
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT credential_hash FROM identities"
                " WHERE provider='password' AND identifier=%s",
                (email.strip().lower(),)).fetchone()
        if row and verify_password(password, row["credential_hash"]):
            return self.get_user(email)
        return None

    def link_identity(self, user_id: int, provider: str, identifier: str,
                      credential_hash: str = "") -> None:
        """给已有用户加一种登录方式(GitHub/手机号=加行;同 provider+identifier 唯一)。"""
        import psycopg
        now = datetime.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            try:
                conn.execute(
                    "INSERT INTO identities(user_id, provider, identifier, credential_hash, created_at)"
                    " VALUES(%s,%s,%s,%s,%s)",
                    (user_id, provider, identifier, credential_hash, now))
            except psycopg.errors.UniqueViolation as e:
                raise ValueError(f"该 {provider} 身份已被绑定") from e

    # ── 会话(M1.5 登录端点启用;表和发/验逻辑现在就位)────

    def open_session(self, user_id: int, days: int = 30) -> str:
        """登录成功后签发会话 token(明文只返回一次,库存哈希)。"""
        token = secrets.token_urlsafe(32)
        with _connect(self.schema) as conn:
            conn.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at, created_at)"
                " VALUES(%s,%s,%s,%s)",
                (_key_hash(token), user_id,
                 (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds"),
                 datetime.now().isoformat(timespec="seconds")))
        return token

    def resolve_session(self, token: str) -> dict | None:
        """会话 token → 用户行;过期/吊销=None。"""
        with _connect(self.schema) as conn:
            s = conn.execute(
                "SELECT s.user_id, u.email FROM sessions s JOIN users u ON u.id=s.user_id"
                " WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at > %s",
                (_key_hash(token), datetime.now().isoformat(timespec="seconds"))).fetchone()
        return s

    def revoke_session(self, token: str) -> None:
        with _connect(self.schema) as conn:
            conn.execute("UPDATE sessions SET revoked_at=%s WHERE token_hash=%s",
                         (datetime.now().isoformat(timespec="seconds"), _key_hash(token)))

    # ── API Key(程序通行证)──────────────────────────

    def issue_api_key(self, user_id: int, name: str = "", scope: str = "write",
                      days: int | None = None) -> str:
        """签发平台 key:明文只返回这一次(库里哈希);scope=read/write。"""
        expires = ((datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
                   if days else None)
        plain, kh = new_api_key()
        with _connect(self.schema) as conn:
            conn.execute(
                "INSERT INTO api_keys(user_id, key_hash, name, scope, expires_at, created_at)"
                " VALUES(%s,%s,%s,%s,%s,%s)",
                (user_id, kh, name, scope, expires,
                 datetime.now().isoformat(timespec="seconds")))
        return plain

    def resolve_api_key(self, plain: str) -> dict | None:
        """key → {user_id, scope, key_id};无效/吊销/过期=None,顺手记 last_used。"""
        with _connect(self.schema) as conn:
            k = conn.execute(
                "SELECT id, user_id, scope FROM api_keys WHERE key_hash=%s"
                " AND revoked_at IS NULL"
                " AND (expires_at IS NULL OR expires_at > %s)",
                (_key_hash(plain), datetime.now().isoformat(timespec="seconds"))).fetchone()
            if k:
                conn.execute("UPDATE api_keys SET last_used_at=%s WHERE id=%s",
                             (datetime.now().isoformat(timespec="seconds"), k["id"]))
        return k

    def revoke_api_key(self, user_id: int, name: str) -> int:
        """按名字吊销用户的一把 key(自助管理)。返回吊销数。"""
        with _connect(self.schema) as conn:
            return conn.execute(
                "UPDATE api_keys SET revoked_at=%s WHERE user_id=%s AND name=%s"
                " AND revoked_at IS NULL",
                (datetime.now().isoformat(timespec="seconds"), user_id, name)).rowcount

    def list_api_keys(self, user_id: int) -> list[dict]:
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT name, scope, expires_at, revoked_at, last_used_at, created_at"
                " FROM api_keys WHERE user_id=%s ORDER BY id", (user_id,)).fetchall()

    # ── 内部 ──────────────────────────────────────────

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TEXT NOT NULL
                )""")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS identities (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    provider TEXT NOT NULL,
                    identifier TEXT NOT NULL,
                    credential_hash TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE (provider, identifier)
                )""")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL
                )""")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    key_hash TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL DEFAULT '',
                    scope TEXT NOT NULL DEFAULT 'write',
                    expires_at TEXT,
                    revoked_at TEXT,
                    last_used_at TEXT,
                    created_at TEXT NOT NULL
                )""")


_identity: Identity | None = None


def default_identity() -> Identity:
    global _identity
    if _identity is None:
        _identity = Identity()
    return _identity


def resolve_user(email_or_id: str | int) -> int:
    """CLI/入口解析用户:邮箱 → user_id;数字串直接当 id;空 → 0(创始用户)。"""
    if email_or_id in (None, "", 0, "0"):
        return 0
    if isinstance(email_or_id, int) or email_or_id.isdigit():
        return int(email_or_id)
    u = default_identity().get_user(email_or_id)
    if u is None:
        raise RuntimeError(f"用户不存在:{email_or_id}(先注册或用 user 0)")
    return u["id"]
