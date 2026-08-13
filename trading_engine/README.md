# Trading Engine

> 用自然语言写交易策略,AI 自己看盘决策下单,引擎保证合规。

## 一、定位

**策略 = prompt + 工具**。你写交易系统的判断规则(自然语言 prompt),引擎提供看数据/下单的能力(工具),AI(DeepSeek)自主调工具、做决策、下单。引擎强制 A 股硬规则(T+1/整手/主板/14:50/风险预算),AI 碰不到钱。

与旧 `skills/trading-system` 完全独立:不读写旧 Skill 文件,旧 Skill 仅作设计参考。

## 二、三层架构

```
┌─ 策略层(可换 — 换策略不动引擎)──────────────────────────┐
│  strategies/expectation_driven/strategy.py               │
│    SYSTEM_PROMPT   判断规则(三维确认/双出口/分歧≠结束) │
│    register_tools  策略工具(get_heartbeat/probe_pool)   │
├─ 引擎层(通用 — 所有策略共用,稳定)──────────────────────┤
│  agent.py    Agent 大脑:PydanticAI 循环 + 对话记忆      │
│  watch.py    看盘命令 + 心跳渲染                         │
│  paper.py    模拟下单 + A股规则校验                      │
├─ 数据层(基础)──────────────────────────────────────────┤
│  live.py     实时行情(TDX 直连)                        │
│  replay.py   历史回放(ClickHouse 重建)                 │
│  storage.py  SQLite 存储(账户/持仓/预期/池/成交)       │
└──────────────────────────────────────────────────────────┘
```

**引擎不认识"预期""池""心跳格式"** — 它只跑循环、提供工具、强制规则。所有"怎么看盘、怎么判断"都在策略层。

## 三、一次看盘的完整链路

```
trader watch run --date 20260813 --live

  开盘: 加载策略包 → system_prompt = 预期管理规则(2021字)
  每轮: runtime 唤醒 AI("新的一轮 11:30")
        ↓
        AI 自己决定调什么工具:
          get_heartbeat()      → 看市场快照(指数/持仓/池X-Y/涨停)
          probe_pool("创新药") → 深析池成员明细
          probe_stock("000636")→ 看个股分钟路径
          trade("SELL",...)    → 下单(paper.py 规则校验)
        ↓
        AI 输出结论 → 对话历史累积 → 推进下一轮
  收盘: 输出总结(现金/持仓/轮数)
```

**两种模式**:
- `--live`:实时看盘(TDX),持续循环,一轮结束马上下一轮(像真人盯盘)
- `--date YYYYMMDD`:历史回放(ClickHouse),按时间步进(每5分钟一个观察点)

## 四、快速上手

### 实时看盘(盘中)
```bash
# 启动 ClickHouse(live market/block rank 需要)
cd astock && docker compose up -d && cd ..

# AI 自主看盘(live 模式,持续循环)
TRADER_LLM_API_KEY=sk-xxx ANTHROPIC_API_KEY=sk-xxx \
  ./trader watch run --date 20260813 --live --max-rounds 5
```

### 历史回放(盘后/测试)
```bash
# 同步某天分钟数据(回放需要)
for code in 000636 603127; do ./astock/astock sync kline --code $code --freq 1m; done

# AI 回放看盘
TRADER_LLM_API_KEY=sk-xxx ANTHROPIC_API_KEY=sk-xxx \
  ./trader watch run --date 20260811 --max-rounds 5

# 看成交/持仓
./trader paper fills
./trader position list
```

### 调试:看发给 AI 的完整 prompt
```bash
./trader watch run --date 20260813 --live --max-rounds 2 --verbose
```
`--verbose` 每轮打印完整消息序列(system + 历史 + 当前),你能看到 LLM 是无状态的(每轮带全部历史)。

## 五、CLI 命令清单

| 命令 | 用途 | 给谁用 |
|---|---|---|
| `watch run` | **AI 自主看盘**(主路径) | AI agent |
| `watch open` | 开盘加载会话上下文 | 人/AI |
| `watch heartbeat` | 单轮心跳(看市场快照) | 人/AI |
| `watch probe` | 深析(池明细/个股路径) | 人/AI |
| `paper execute` | 模拟下单(规则校验) | 命令/agent trade 工具 |
| `paper fills/orders/audit` | 成交/订单/审计查询 | 人 |
| `account init/show/update` | 账户管理 | 人(配置) |
| `position set/list` | 持仓管理 | 人(配置) |
| `thesis set/list/link` | 预期管理 | 人(策略知识) |
| `pool set/member/show` | 主题池管理 | 人(策略知识) |
| `plan set/list` | 盘前预案 | 人(策略知识) |
| `risk set/list/link` | 风险因子 | 人(策略知识) |
| `evidence add/list` | 催化证据 | 人(策略知识) |
| `context capture/replay/show` | 决策上下文(审计) | 旧路径/审计 |
| `analyze latest` | LLM 判断(旧无状态路径) | 兜底 |
| `brief` | 状态摘要 | 人/AI 启动 |
| `replay` | 历史回放引擎 | 测试 |

## 六、模块结构

```
src/trading_engine/
├── 策略层
│   └── strategies/expectation_driven/strategy.py   ← 改策略主要动这里
│       SYSTEM_PROMPT(判断规则) + register_tools(工具)
│
├── 引擎层
│   ├── agent.py          Agent 循环(PydanticAI)+ 记忆 + 通用工具(probe_stock/trade)
│   ├── watch.py          watch 命令 + 心跳渲染(format_open/heartbeat/probe)
│   ├── paper.py          模拟下单 + 规则校验(T+1/整手/主板/14:50/风险)
│   ├── analysis.py       旧版判断(shadow provider,兜底)
│   └── llm_provider.py   旧版 DeepSeek provider(analyze 命令用)
│
├── 数据层
│   ├── live.py           实时行情(TDX:live quote/index/market/block rank)
│   ├── replay.py         历史回放(ClickHouse:重建某天行情快照)
│   ├── context.py        决策上下文构建(行情+持仓+预期+池→完整context)
│   ├── storage.py        SQLite 存储(最大文件,账户/持仓/预期/池/判断/成交)
│   └── astock.py         astock 二进制 Python 封装
│
├── CLI 入口
│   ├── cli.py            主命令(account/position/thesis/pool/plan/replay/analyze/brief)
│   ├── context_cli.py    context 命令组
│   └── paper_cli.py      paper 命令组
│
└── 模型/辅助
    ├── models.py         核心数据模型(MarketSnapshot/Judgment/Account/Position/Thesis...)
    ├── context_models.py 决策上下文模型(DecisionContext/PoolMetrics/PricePath...)
    ├── paper_models.py   模拟交易模型(Order/Fill/ExecutionResult...)
    ├── *_store.py        各存储层 SQLite 操作
    ├── brief.py          状态摘要生成
    ├── config.py         配置(路径/环境变量)
    └── dates.py          日期解析
```

## 七、"我想改 X,改哪里"

| 改什么 | 改哪里 | 引擎动不动 |
|---|---|---|
| 预期管理判断规则 | `strategies/.../strategy.py` SYSTEM_PROMPT | 不动 |
| 心跳看什么数据 | `strategies/.../strategy.py` get_heartbeat | 不动 |
| 加新工具给 AI | `strategies/.../strategy.py` register_tools | 不动 |
| 换策略(趋势/打板) | 新建 `strategies/trend_following/` | 不动 |
| 改 A 股规则 | `paper.py` 规则校验 | 所有策略生效 |
| 改心跳节奏 | `agent.py` run_watch_session | — |
| 加可视化 | 新文件(报告/web) | 现有逻辑不动 |

## 八、当前状态

### ✅ 已完成
- AI 自主看盘(live 实时 + 回放历史),PydanticAI agent + DeepSeek
- 策略层/引擎层分离,换策略不动引擎
- 预期管理策略包(三维确认/双出口/分歧≠结束)
- AI 主动调工具(get_heartbeat/probe_pool/probe_stock/trade)
- 模拟交易 + 全部 A 股规则(T+1/整手/主板/14:50/风险预算/duplicate_signal)
- 心跳层:指数/持仓/池健康度X-Y/涨停明细(带概念/连板)

### ❌ 已知缺口(下一步候选)
| 缺口 | 影响 |
|---|---|
| 看不到 AI 思考链路 | 决策过程散在日志,无可视化 |
| 盘前/盘后未做 | 只有盘中,缺完整交易日闭环 |
| 持仓状态不同步 | heartbeat 显示持仓 vs paper 账户实际持仓会不一致 |
| token 管理 | 对话历史无限增长,长会话可能爆 context |
| 盘前预案未录入 | plan 命令有但 AI 开盘看不到 |

## 九、开发与测试

```bash
# 安装
uv sync

# 运行测试(122 个,确定性,不依赖开盘/LLM)
uv run pytest tests

# 从仓库根目录运行
./trader --version
./trader watch --help
```

### 环境变量

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `TRADER_REPO_ROOT` | 仓库根目录 | 自动发现 |
| `TRADER_ASTOCK_BINARY` | astock 二进制路径 | `<repo_root>/astock/astock` |
| `TRADER_DATA_DIR` | 数据目录 | `<repo_root>/trading_engine/data` |
| `ANTHROPIC_API_KEY` | DeepSeek API key(PydanticAI agent 用) | 必填 |
| `TRADER_LLM_API_KEY` | DeepSeek API key(旧 analyze 路径) | 必填 |
| `TRADER_LLM_BASE_URL` | API base URL | `https://api.deepseek.com/anthropic` |
| `TRADER_LLM_MODEL` | 模型名 | `deepseek-v4-flash` |

### 技术栈
Python 3.13 + Pydantic v2 + PydanticAI(agent 框架)+ Typer(CLI)+ SQLite(存储)+ uv(依赖)+ pytest(测试)。LLM 通过 PydanticAI 接 DeepSeek(Anthropic 兼容协议),换模型改一行。

### 数据职责

| 数据 | 存储 | 说明 |
|------|------|------|
| 行情(实时) | TDX 直连 | `live quote/index/market/block rank` |
| 行情(历史) | ClickHouse | 回放重建,`docker compose up -d` 启动 |
| 运行状态 | SQLite | 账户/持仓/预期/池/预案/判断/成交 |
| 决策上下文 | SQLite (context_snapshots) | 完整决策快照,冻结去重(审计) |
| 对话记忆 | 内存(agent 运行时) | message_history 累积,会话结束消失 |
| 人类可读报告 | Markdown | 从结构化状态生成 |
