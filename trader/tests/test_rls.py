"""RLS 纵深加固测试(D10):受限角色(trader_app)连接时,数据库层强制按 user_id 隔离。

策略:user_id = current_setting('app.user_id')。超级用户(开发连接)按 PG 规则绕过——
本测试专门用受限角色连接验证"应用层就算漏了过滤,数据库也拒绝跨用户"。

docstring 统一格式:<场景>:<验证点>
"""
import psycopg

from trader.core.db import DATABASE_URL
from trader.core.documents import Documents
from trader.core.identity import Identity

TOOL = "rls"

_RLS_URL = DATABASE_URL.replace("//postgres:password@", "//trader_app:trader_app@")
_TABLE = "documents"
_SCHEMA = "t_rls_check"


def _setup():
    """超级用户建表造数+启用 RLS,给受限角色授权。"""
    Documents(schema=_SCHEMA)               # 建表
    idt = Identity(schema=_SCHEMA)           # 顺带验证 identities 表也建好
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
        c.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
        c.execute("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='trader_app') THEN"
                  " CREATE ROLE trader_app LOGIN PASSWORD 'trader_app' NOSUPERUSER; END IF; END $$")
        c.execute(f"GRANT USAGE ON SCHEMA {_SCHEMA} TO trader_app")
        c.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {_SCHEMA} TO trader_app")
        c.execute(f"ALTER TABLE {_SCHEMA}.{_TABLE} ENABLE ROW LEVEL SECURITY")
        c.execute(f"ALTER TABLE {_SCHEMA}.{_TABLE} FORCE ROW LEVEL SECURITY")
        c.execute(f"DROP POLICY IF EXISTS tenant_user ON {_SCHEMA}.{_TABLE}")
        c.execute(f"CREATE POLICY tenant_user ON {_SCHEMA}.{_TABLE}"
                  " USING (user_id = current_setting('app.user_id', true)::int)"
                  " WITH CHECK (user_id = current_setting('app.user_id', true)::int)")
    docs = Documents(schema=_SCHEMA)
    from trader.core.context import set_context
    set_context(0, None, 1)
    docs.save("note", "用户1的笔记", name="u1")
    set_context(0, None, 2)
    docs.save("note", "用户2的笔记", name="u2")


def test_rls_blocks_cross_user():
    """受限角色+RLS:只能看到自己 user_id 的行;冒写他人 user_id 被数据库拒绝。"""
    _setup()
    with psycopg.connect(_RLS_URL) as c:    # 以 trader_app 身份连接
        c.execute("SELECT set_config('search_path', %s, false)", (_SCHEMA,))
        c.execute("SELECT set_config('app.user_id', '1', false)")
        visible = [r[0] for r in c.execute(
            f"SELECT name FROM {_TABLE} WHERE doc_type='note'").fetchall()]
        assert visible == ["u1"], f"user1 应只见 u1,实际 {visible}"
        # 冒写 user_id=2 → WITH CHECK 拒绝
        import pytest
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute(f"INSERT INTO {_TABLE}(doc_type,name,content,user_id)"
                      " VALUES('note','越权','x',2)")
        c.rollback()  # 违规把事务打断了,回滚后继续验证下一分支
        # 注意:回滚会连带撤销事务里设的 session 级 GUC(search_path),重新设定
        c.execute("SELECT set_config('search_path', %s, false)", (_SCHEMA,))
        # 换成无关身份(999999)→ 看不到任何人的数据
        c.execute("SELECT set_config('app.user_id', '999999', true)")
        n = c.execute(f"SELECT COUNT(*) FROM {_SCHEMA}.{_TABLE}").fetchone()[0]
        assert n == 0
    print("  → trader_app 视角:user1 只见自己;越权写入被数据库拒绝;换身份=零可见")
