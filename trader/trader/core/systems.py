"""core·交易系统注册表(平台通用件):系统定义正本,manifest 纯数据。

一行 = 一个交易系统。engine 读它装配阶段/工具/prompt;换系统 = 换一行,不改代码。
三层身份:id(代理键,子表引用) / slug(机器名,英文唯一键) / display_name(显示名,可中文)。
manifest 只装纯数据声明;stage 级 data_mode/clock 已退役(时钟改为发起时绑定,工作台架构 §3)。
"""
import json

from trader.core.db import _connect
from trader.core.contracts import normalize_manifest

# expectation 系统的初始 manifest
EXPECTATION_MANIFEST = {
    "system_prompt": "system",
    "stages": {
        "premarket": {"kind": "single", "prompt": "premarket", "request_limit": 200,
                      "outputs": {
                          "plan": {"kind": "document", "doc_type": "premarket",
                                   "trade_date": "{date}", "label": "当日交易计划"},
                      }},
        "live": {"kind": "loop", "prompt": "round_live", "request_limit": 50,
                 "window": "09:35-15:05", "skip_lunch": True,
                 "inputs": {
                     "opening_plan": {"from": "premarket.plan", "selector": "latest",
                                      "required": False, "label": "当日盘前计划"},
                     "recent_decisions": {"from": "live.decision", "selector": "previous",
                                          "limit": 3, "required": False,
                                          "label": "最近盘中判断"},
                 },
                 "outputs": {
                     "decision": {"kind": "document", "doc_type": "watch_live",
                                  "name": "r{rounds}", "trade_date": "{date}",
                                  "label": "本轮判断"},
                 }},
        "replay": {"kind": "loop", "prompt": "round_replay", "request_limit": 50,
                   "interval": 5, "window": "09:35-15:00", "skip_lunch": True,
                   "inputs": {
                       "opening_plan": {"from": "premarket.plan", "selector": "latest",
                                        "required": False, "label": "当日盘前计划"},
                       "recent_decisions": {"from": "replay.decision", "selector": "previous",
                                            "limit": 3, "required": False,
                                            "label": "最近模拟判断"},
                   },
                   "outputs": {
                       "decision": {"kind": "document", "doc_type": "watch_replay",
                                    "name": "r{rounds}", "trade_date": "{date}",
                                    "label": "本轮判断"},
                   }},
        "close": {"kind": "single", "prompt": "close", "request_limit": 200,
                  "inputs": {
                      "opening_plan": {"from": "premarket.plan", "selector": "latest",
                                       "required": False, "label": "当日盘前计划"},
                      "intraday_decisions": {"from": "live.decision", "selector": "all",
                                             "required": False, "max_chars": 50000,
                                             "label": "当日盘中判断"},
                  },
                  "outputs": {
                      "review": {"kind": "document", "doc_type": "close",
                                 "trade_date": "{date}", "label": "盘后复盘"},
                  }},
        "research": {"kind": "single", "prompt": "research", "request_limit": 200,
                     "vars": ["topic"]},
    },
    "policy": {"web_search": True, "resource_write": True,
               "simulation_trading": True, "live_trading": True},
    # Backend-generated catalog for legacy API consumers and the advanced test
    # desk. It is not read by Stage authorization or shown in System Settings.
    "tools": [
        "get_quotes", "get_indices", "get_kline", "get_block_rank", "get_block_members",
        "get_candidates", "get_limit_up", "get_market_summary", "get_top_amount", "get_us_market",
        "get_positions", "get_account", "get_trades", "execute", "scan_market",
        "save_doc", "get_doc", "list_docs", "set_doc_meta", "save_watchlist",
        "get_watchlist", "get_watchlist_quotes", "remove_watchlist_member",
    ],
    # 文档归类(工作台架构 §3):library=跨天知识资产(进工作台"按类型");
    # ephemeral=绑场次的执行产出(挂场次,"按日期"只是索引)
    "doc_classes": {
        "library": ["expectation", "research", "note"],
        "ephemeral": ["premarket", "close"],
    },
}


def clean_manifest(m: dict) -> dict:
    """manifest 规范化:剔除已退役的 stage 级 data_mode/clock 与顶层 display_name
    (display_name 已上提为 systems 列)。幂等,供迁移与 upsert 共用。"""
    out = dict(m)
    out.pop("display_name", None)
    raw_stages = m.get("stages") or {}
    if not isinstance(raw_stages, dict):
        raise ValueError("stages 必须是对象")
    stages = {}
    for name, sdef in raw_stages.items():
        if not isinstance(sdef, dict):
            raise ValueError(f"阶段 {name} 必须是对象")
        s = {k: v for k, v in sdef.items() if k not in ("data_mode", "clock")}
        s.pop("capabilities", None)
        stages[name] = s
    out["stages"] = stages
    return out


class Systems:
    """交易系统注册表:manifest 按 slug 登记,engine 启动时读取装配。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        from trader.core.db import ensure_once
        ensure_once(f"systems:{schema}", self._init_db)

    def upsert(self, slug: str, manifest: dict, status: str = "active",
               user_id: int = 0, display_name: str = "") -> dict:
        """写入/更新一个系统定义(按 user+slug 覆盖)。返回该行。"""
        from datetime import datetime as _dt

        manifest = clean_manifest(manifest)
        manifest = normalize_manifest(manifest)
        display_name = display_name or (manifest.get("display_name") or slug)
        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            row = conn.execute(
                "INSERT INTO systems(user_id, slug, display_name, manifest, status,"
                " created_at, updated_at)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s)"
                " ON CONFLICT (user_id, slug) DO UPDATE SET manifest=excluded.manifest,"
                " display_name=excluded.display_name, status=excluded.status,"
                " updated_at=excluded.updated_at"
                " RETURNING *",
                (user_id, slug, display_name, json.dumps(manifest, ensure_ascii=False),
                 status, now, now),
            ).fetchone()
        return row

    def get(self, slug: str, user_id: int = 0) -> dict | None:
        """取某系统(manifest 已解析为 dict)。无则 None。"""
        with _connect(self.schema) as conn:
            row = conn.execute("SELECT * FROM systems WHERE user_id=%s AND slug=%s",
                               (user_id, slug)).fetchone()
        if row:
            row = dict(row)
            if isinstance(row["manifest"], str):  # JSONB 驱动已解析,兼容手插的字符串
                row["manifest"] = json.loads(row["manifest"])
        return row

    def get_by_id(self, system_id: int) -> dict | None:
        with _connect(self.schema) as conn:
            row = conn.execute("SELECT * FROM systems WHERE id=%s", (system_id,)).fetchone()
        if row:
            row = dict(row)
            if isinstance(row["manifest"], str):
                row["manifest"] = json.loads(row["manifest"])
        return row

    def list(self, user_id: int | None = None) -> list[dict]:
        where, args = ("", []) if user_id is None else ("WHERE user_id=%s", [user_id])
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT id, user_id, slug, display_name, manifest, status,"
                " created_at, updated_at FROM systems"
                f" {where} ORDER BY id", args
            ).fetchall()

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS systems (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    slug TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    manifest JSONB NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','archived')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            # 多租户命名空间:user 维度唯一(slug 机器名)
            conn.execute("ALTER TABLE systems ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE systems DROP CONSTRAINT IF EXISTS systems_name_key")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS systems_user_slug ON systems(user_id, slug)")
            self._migrate_expectation_stage_contracts(conn)

    @staticmethod
    def _migrate_expectation_stage_contracts(conn) -> None:
        """给存量内置预期系统补 Stage I/O,不覆盖用户已经编辑的契约。

        这里是一次性兼容迁移;运行引擎本身只认 manifest,不知道 premarket/live。
        """
        rows = conn.execute(
            "SELECT id,manifest FROM systems WHERE slug='expectation'"
        ).fetchall()
        for row in rows:
            manifest = dict(row["manifest"] or {})
            stages = dict(manifest.get("stages") or {})
            changed = False
            for stage_name, default_stage in EXPECTATION_MANIFEST["stages"].items():
                current = stages.get(stage_name)
                if not current or current.get("prompt") != default_stage.get("prompt"):
                    continue
                current = dict(current)
                for key in ("inputs", "outputs"):
                    if key in default_stage and key not in current:
                        current[key] = default_stage[key]
                        changed = True
                stages[stage_name] = current
            if changed:
                manifest["stages"] = stages
                conn.execute("UPDATE systems SET manifest=%s WHERE id=%s",
                             (json.dumps(manifest, ensure_ascii=False), row["id"]))


_systems: Systems | None = None


def default_systems() -> Systems:
    global _systems
    if _systems is None:
        _systems = Systems()
    return _systems


def ensure_expectation_system(user_id: int = 0) -> dict:
    """确保 expectation 系统已登记(幂等,manifest 以代码里的初始定义为准)。"""
    return default_systems().upsert("expectation", EXPECTATION_MANIFEST,
                                    user_id=user_id, display_name="预期管理")
