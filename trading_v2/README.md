# Trading V2

从零构建的 A 股看盘交易 agent(PydanticAI + DeepSeek)。方法论:预期管理——预期库是真相源,买入前提是"研究过",卖出对照"兑现/失效标志"。

## 目录结构

```
trading_v2/
├── trader/
│   ├── tools/            ← AI 工具(22 个,AI 能调的全在这)
│   │   ├── market.py     ← 行情:get_quotes / get_indices / get_kline / get_block_* / get_candidates / get_limit_up / get_market_summary / get_top_amount
│   │   ├── watch.py      ← scan_market 快扫(指数+持仓+板块+异动,一屏)
│   │   ├── account.py    ← get_positions / get_account
│   │   ├── trading.py    ← execute 下单(整手/主板校验 + 实时价成交)
│   │   ├── knowledge.py  ← 预期库读写:get/add/update_expectations, get_pool, add/remove_pool_member
│   │   └── docs.py       ← 文档库:save_doc / get_doc / list_docs(盘前报告/研究过程)
│   ├── store.py          ← SQLite:账户 + 预期库 + 文档库(documents 通用 md 存储)
│   ├── agent.py          ← 大脑:22 工具 + 原生联网搜索(NativeTool WebSearchTool)
│   └── runner.py         ← 盘前分析 / 预期研究 / 看盘循环入口
├── prompts/              ← prompt(md 文件,反复迭代期;稳定后迁 SQLite)
│   ├── system.md         ← AI 角色
│   ├── premarket.md      ← 盘前分析(八维催化→场景推演→预案)
│   ├── research.md       ← 预期研究(双模式:新建 + 重新研究更新)
│   └── round_replay.md / round_live.md  ← 看盘每轮指令
├── tests/                ← 53 个测试(45 passed + 8 live 盘中自动跑)
├── data/account.db       ← SQLite 真相源(账户+预期+文档)
└── .env                  ← 配置(LLM_API_KEY / LLM_MODEL / LLM_BASE_URL,不进 git)
```

## 常用命令(cd trading_v2)

```bash
# ── 盘前分析(八维催化→预期更新→场景推演→预案,报告落库)──
uv run python -m trader.runner premarket 20260817        # 上一交易日自动推算

# ── 看报告/文档库 ───────────────────────────────────────
uv run python -m trader.tools call list_docs                              # 文档列表
uv run python -m trader.tools call get_doc doc_type=premarket trade_date=20260817  # 报告全文

# ── 预期库 ──────────────────────────────────────────────
uv run python -m trader.tools call get_expectations       # 总览
uv run python -m trader.tools call get_pool expectation_id=2   # 详情(逻辑/兑现/失效/池)

# ── 测试单个工具(免费秒出)─────────────────────────────
uv run python -m trader.tools list                        # 列出全部工具+签名
uv run python -m trader.tools call get_market_summary date=20260814
# 注意:参数用 key=value 空格分隔,逗号=列表(codes=000021,000636)

# ── 自动回归测试 ────────────────────────────────────────
uv run pytest                     # 安静模式
uv run pytest -s                  # 显示每步数据(-v 加测试名)

# ── LLM 端到端(AI 自己组合工具)─────────────────────────
uv run python -m trader.runner research "光纤涨价"   # 预期研究(新建/更新自动判断)
uv run python -m trader.runner replay 20260812 --interval 5   # 模拟看盘(回放,会读盘前预案)
uv run python -m trader.runner replay 20260812 --max-rounds 3 # 调试 3 轮
uv run python -m trader.runner live --sleep 0        # 实时看盘(默认连续,Ctrl+C 停)
```

## 环境

- **.env**:`cp .env.example .env` 后填 DeepSeek key(联网搜索复用同一 key)
- **ClickHouse**:replay/query 数据依赖 Docker 里的 `astock-clickhouse` 容器,跑之前确认 Docker 起着(`docker ps` 看到 healthy)
- live 类命令(板块排名/异动榜)盘中专用,盘后自动拒绝并提示用 replay

## 测试三层

| 层 | 命令 | 成本 | 用途 |
|---|---|---|---|
| 单工具 | `python -m trader.tools call ...` | 免费 | 开发调试 |
| 回归 | `pytest` | 免费 | 改动后护栏 |
| 端到端 | `runner` / `agent` | 花 token | 验证 AI 行为 |
