"""M1 一次性迁移:多租户骨架落库(多用户设计 §4)。

幂等,可重复跑。步骤:
1. 新表创建(identity/bags/ledgers + 全部约束重建由各 store 的 _init_db 自愈)
2. user 0 = 平台所有者(邮箱取 TRADER_OWNER_EMAIL,缺省 owner@trader.local;
   密码随机生成并打印一次——M1.5 登录端点上线即用,可用 reset_password 重置)
3. bag 0 → user 0 的 live 账本「主账本」
4. 存量数据全部归 user 0(列默认值即 0,显式 UPDATE 保险)
5. (可选)RLS 策略:--rls 时启用,为 M1.5 API 服务用受限角色做准备
"""
import os
import secrets
import sys

sys.path.insert(0, ".")

from trader.core.db import _connect
from trader.core.identity import Identity, hash_password
from trader.core.ledger import Bags, Ledgers


def migrate(enable_rls: bool = False) -> None:
    # ① 新表(各 store 的 _init_db 幂等建表 + 重建 user 维度唯一约束)
    from trader.core.documents import Documents
    from trader.core.ledger import Account
    from trader.core.promptver import PromptVersions
    from trader.core.runs import Runs
    from trader.core.systems import Systems
    from trader.core.watchlist import Watchlists
    Identity(); Bags(); Ledgers(); Runs(); Systems(); PromptVersions(); Account(); Documents(); Watchlists()
    print("① 新表与命名空间约束就绪")

    # ② user 0 = 所有者
    email = os.environ.get("TRADER_OWNER_EMAIL", "owner@trader.local")
    password = secrets.token_urlsafe(12)
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM users WHERE id=0").fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users(id, email, display_name, is_admin, created_at)"
                " VALUES(0, %s, '所有者', TRUE, '2026-08-18 00:00:00')", (email,))
            conn.execute(
                "INSERT INTO identities(user_id, provider, identifier, credential_hash, created_at)"
                " VALUES(0, 'password', %s, %s, '2026-08-18 00:00:00')",
                (email, hash_password(password)))
            print(f"② user 0 已建:邮箱 {email},初始密码(只显示一次,请改):{password}")
        else:
            print(f"② user 0 已存在({email}),跳过")

    # ③ bag 0 → user 0 的 live 账本
    with _connect() as conn:
        conn.execute(
            "INSERT INTO ledgers(user_id, name, kind, bag_id, created_at)"
            " VALUES(0, '主账本', 'live', 0, '2026-08-18 00:00:00')"
            " ON CONFLICT (user_id, name) DO NOTHING")
        print("③ bag 0 = user 0 的 live 账本「主账本」")

    # ④ 存量归 user 0(默认值覆盖,显式保险)
    with _connect() as conn:
        for tbl in ("documents", "watchlists", "watchlist_members", "versions",
                    "positions", "fills", "wallets", "runs", "systems", "prompt_versions"):
            n = conn.execute(f"UPDATE {tbl} SET user_id=0 WHERE user_id=0").rowcount
        print("④ 存量数据归属 user 0(user_id=0)")

    if enable_rls:
        _enable_rls()
    print("\n✓ M1 迁移完成")


def _enable_rls() -> None:
    """RLS 纵深加固(D10):策略按 app.user_id 匹配;应用连接受限角色时强制生效。

    本机开发连接(postgres 超级用户)按 PG 规则跳过 RLS——策略先就位,
    M1.5 的 API 服务用 trader_app 角色连接时即获得数据库级隔离。
    """
    from trader.core.db import DATABASE_URL
    import psycopg
    tables = ("documents", "watchlists", "watchlist_members", "versions",
              "positions", "fills", "wallets", "runs", "systems", "prompt_versions")
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='trader_app') THEN"
                     " CREATE ROLE trader_app LOGIN PASSWORD 'trader_app' NOSUPERUSER; END IF; END $$")
        conn.execute("GRANT USAGE ON SCHEMA public TO trader_app")
        for t in tables:
            conn.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{t} TO trader_app")
            conn.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY")
            conn.execute(f"ALTER TABLE public.{t} FORCE ROW LEVEL SECURITY")
            conn.execute(f"DROP POLICY IF EXISTS tenant_user ON public.{t}")
            conn.execute(f"CREATE POLICY tenant_user ON public.{t}"
                         " USING (user_id = current_setting('app.user_id', true)::int)"
                         " WITH CHECK (user_id = current_setting('app.user_id', true)::int)")
    print("⑤ RLS 策略已启用(受限角色 trader_app 连接时强制隔离)")


if __name__ == "__main__":
    migrate(enable_rls="--rls" in sys.argv)
