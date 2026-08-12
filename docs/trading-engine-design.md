# Trading Engine - AI 交易引擎设计

> 状态：Phase 0-4 已完成；Phase 5 精简重构已完成（删 tools/watch，行情统一走 astock，context 全量留存 + LLM 推理链）
> 定位：trader 是有记忆、有规则、无大脑的工具网关；brain 从外部插入，通过 CLI 调用工具做交易判断

---

## 一、这是什么

一个 AI 交易引擎。**AI 是投资者**（做分析和决策），**astock 是眼睛**（行情），**trader 是记忆和手**（状态 + 执行 + 规则）。

```
brain (可插拔)              两个独立入口
┌──────────┐        ┌──────────────────────────────┐
│ Qoder    │──CLI──->│ astock：实时/历史行情         │
│ LLM API  │        │ trader：状态/审计/模拟执行    │
│ Shadow   │        └──────────────────────────────┘
└──────────┘
```

brain 直接调用 astock 获取行情，调用 trader 读取 SQLite 状态并通过 PaperBroker 执行交易。

三种 brain 可以互换，使用同一组 astock 行情命令和 `trader` 状态命令：

| Brain | 场景 | 循环方式 |
|-------|------|---------|
| Qoder | 开发/日常看盘 | 用户说"继续"触发每轮 |
| LLM API | 全自动看盘 | 编排器 `while market_open` |
| Shadow | 测试 | 确定性占位 |

---

## 二、为什么这么设计

### 问题诊断

原来用 Qoder Skill（Markdown 规范）驱动 AI 看盘，反复出错：

```
AI读规则md -> 理解偏差 -> 走错分支 -> 事后发现 -> 改md -> 下次又理解错
```

五个根因：

| 根因 | 表现 |
|------|------|
| 流程分支靠 AI 选择 | AI 读 md 后自行决定走哪条路，上下文一长就漂移 |
| 规则散落在 6+ 个 md 文件 | AI 跨文件索引理解，每次都有偏差 |
| 规则是建议性的 | "应该走 §3.3"但 AI 可以不走，没有程序性约束 |
| 一个 AI 全做 | 快扫/深析/决策/执行全在一个 session，上下文越来越长 |
| 上下文一次性全量组装 | 每轮把所有数据打包给 AI，但 AI 大部分时间只需要扫一眼 |

### 解决方案

**trader 是有记忆、有规则、无大脑的工具网关。brain 从外部插入，通过 CLI 调用工具做交易判断。**

**核心原则**：

1. **所有数据从 astock 调用** -- trader 不存独立行情表，不做行情代理
2. **所有 AI 思考的输入和结论都留存** -- context 是完整快照（行情+状态+推理+结论），可回溯
3. **查询回归资源命令** -- 不单独拆 tools 命令族，每个资源有自己的命令
4. **行情不单独存表** -- watch 命令已删除，行情数据保存在 context_json 中

---

## 三、架构

### 三层分离

```
┌──────────────────────────────────────────────────┐
│              brain (可插拔判断层)                  │
│                                                  │
│  Qoder / LLM API / Shadow / 任何 agent            │
│  读 brief -> 按需调 astock/trader -> 思考 -> 决策   │
└─────────────┬──────────────────┬─────────────────┘
              │ 行情             │ 状态/执行
              ↓                  ↓
┌──────────────────────┐  ┌─────────────────────────┐
│ astock               │  │ trader                  │
│ 实时/历史/回放行情    │  │ SQLite 状态与审计       │
│ 文本或 JSON 输出      │  │ PaperBroker 硬规则      │
└──────────────────────┘  └─────────────────────────┘
```

### 核心原则

1. trader 是有记忆、有规则、无大脑的工具网关；brain 从外部插入。
2. 硬规则（T+1、主板、100 股等）在 PaperBroker 代码层拦死，brain 无法绕过。
3. brain 直接调用 `astock` 获取行情，调用 `trader` 读取交易状态和执行交易。
4. SQLite 保存状态和审计；Markdown 作为面向人的报告。
5. astock 是唯一行情入口；trader 不重复代理行情命令。
6. 模拟回放在任意时点只能使用该时点之前可获得的数据，禁止未来数据泄漏。
7. **所有 AI 思考的输入和结论都留存** -- context 是完整决策快照，包含行情数据、账户状态、推理链和最终结论，方便回溯"看看历史看盘的记录，知道哪里做错了"。

---

## 四、命令清单

### 4.1 开局

#### `trader brief`

**作用**：每轮开始时给 brain 的最小信息--不预取行情数据。brain 拿到后知道"我有什么、我在关注什么"，然后自己决定调什么工具。

```bash
trader brief
trader brief --account paper
```

返回示例：

```json
{
  "timestamp": "2026-07-31 14:30:00 CST",
  "market_phase": "intraday_afternoon",
  "account": {
    "name": "paper", "cash": "20229.4", "initial_cash": "100000", "cooldown": false },
  "positions": [
    {"code": "000021", "name": "深科技", "quantity": 400, "sellable_quantity": 400, "average_cost": "38.73"},
    {"code": "000636", "name": "风华高科", "quantity": 500, "sellable_quantity": 0, "average_cost": "43.3"}
  ],
  "active_theses": [{"key": "memory_chip", "title": "存储芯片", "status": "active"}],
  "active_pools": [{"key": "memory_pool", "name": "存储池", "status": "active", "member_count": 6}],
  "today_plans": [],
  "recent_trades": []
}
```

### 4.2 行情数据（直接使用 astock）

trader 不提供行情代理命令。brain 按需直接调用 astock，默认输出供人和 agent 阅读的文本，需要机器格式时加 `--json`。例如：

```bash
astock live index 000001 399001 000688 399006
astock live block rank --limit 50
astock live quote 000021 603127
astock live block members 880904
astock live minute 000021
astock live tick 000021
astock live market --sort change --order desc --limit 50
astock live market --sort amount --order desc --limit 50
astock live market --state limits --sort amount --limit 100

astock replay index 20260730 10:30
astock replay block rank 20260730 10:30 --limit 50
astock replay quote 000021 20260730 10:30
```

行情能力、格式、校验和回放语义只在 astock 维护一份。

### 4.3 状态记忆（资源命令）

查询不再单独拆 tools 命令族，而是回归各自的资源命令：

| 资源 | 命令 | 说明 |
|------|------|------|
| 账户 | `trader account show --account paper` | 查账户状态（余额、初始资金、冷却标志） |
| 持仓 | `trader position list --account paper` | 查持仓明细（代码/名称/数量/可卖/成本） |
| 预期 | `trader thesis list [--active-only]` | 查预期列表，`--active-only` 只看活跃的 |
| 观察池 | `trader pool list [--status active]` | 列出全部池+成员，`--status` 过滤 |
| 观察池 | `trader pool show --key <key>` | 查看单个池详情 |
| 证据 | `trader evidence list [--thesis <key>]` | 查证据记录，`--thesis` 按预期过滤 |
| 证据 | `trader evidence add --thesis ... --kind ...` | 添加证据 |
| 风险 | `trader risk list` | 查风险因子 |
| 预案 | `trader plan list [--date YYYYMMDD]` | 查今日预案 |
| 交易历史 | `trader paper history --account paper` | 查交易历史 |
| 对账 | `trader paper audit --account paper` | 检查数据一致性 |

### 4.4 决策上下文（context）

#### `trader context capture`

**作用**：从 astock 实时获取行情 + 从 SQLite 读取状态，构建一个完整决策上下文快照并持久化。行情数据直接保存在 `context_json` 中，不存独立行情表。

```bash
trader context capture --account paper
```

每一轮 context 都有唯一标识（fingerprint = sha256 of context content），记录下相关信息，方便回溯。

#### `trader context replay`

**作用**：从 astock 回放数据构建同样的 context 契约，用于模拟看盘。

```bash
trader context replay --date 20260730 --until 10:30 --account paper
```

#### `trader context show`

**作用**：查看最新持久化的 context，不重新构建。

```bash
trader context show --account paper
```

#### `trader context reasoning add`

**作用**：为某轮 context 追加一条 LLM 推理链。推理链是结构化的四段式：观察→假设→验证→结论。

```bash
trader context reasoning add \
  --context <context_id> \
  --observed "PCB板块排名第3，5只涨停" \
  --hypothesis "AI硬件需求拉动PCB放量" \
  --verified "沪电领涨8.5%，深南盘中跟进" \
  --conclusion "三维确认，BUY 沪电 100股"
```

#### `trader context reasoning list`

**作用**：列出 LLM 推理链，可按 context 过滤。

```bash
trader context reasoning list                    # 全部
trader context reasoning list --context <id>    # 某轮 context 的推理链
```

### 4.5 判断与执行

#### `trader analyze latest`

**作用**：对最新 context 生成只读提案（不执行交易）。从 `latest_context()` 读最新 context，调 ReadOnlyAnalyzer 生成 JudgmentReport。

```bash
trader analyze latest --account paper
```

#### `trader analyze context`

**作用**：对指定 context 生成只读提案。

```bash
trader analyze context --context <id>
```

#### `trader paper execute`

**作用**：执行某个判断，通过 PaperBroker 硬规则检查后成交。

```bash
trader paper execute --judgment <id> --account paper
```

执行时会通过 `_assert_core_context_fresh` 检测 staleness -- 比对当前 SQLite 账户/持仓状态与 context 捕获时的状态，防止用过期 context 执行交易。

### 4.6 两个 CLI 的职责

| 入口 | 数据源 | 用途 |
|------|--------|------|
| `astock` | 实时行情、ClickHouse 历史行情 | 看市场发生了什么 |
| `trader` | SQLite、PaperBroker | 看自己的状态、构建上下文、执行并审计交易 |

### 4.7 Live 模式 vs Replay 模式

行情的 Live 和 Replay 模式都由 astock 直接提供：

| 模式 | 触发方式 | 数据源 | 用途 |
|------|---------|-------|------|
| Live | `astock live ...` | 实时源 | 真实看盘 |
| Replay | `astock replay ...` | ClickHouse 历史数据 | 模拟看盘 |

Replay 命令可传 `HH:MM` 精确到分钟；不传时间时返回日线终值。首次回放前运行 `astock replay prepare <date>` 准备数据，再用 `astock replay check <date>` 检查完整性。

### 4.8 brain 典型调用流程

**Live 模式（真实看盘）：**

```
trader brief -> 知道状态
  -> astock live index ... -> 看大盘
  -> astock live block rank -> 看板块（发现PCB强）
  -> astock live block members 880904 -> 看PCB具体哪些票涨
  -> astock live quote 000021 000636 -> 看持仓股最新价
  -> trader thesis list --active-only -> 看活跃预期
  -> trader evidence list --thesis memory_chip -> 看已有证据
  -> trader context capture -> 构建完整决策上下文（行情+状态，存 SQLite）
  -> trader context reasoning add -> 记录推理链（观察→假设→验证→结论）
  -> trader analyze latest -> 生成只读提案
  -> trader paper execute -> PaperBroker 规则检查 -> 成交
  -> trader paper audit -> 验证数据一致性
```

---

## 五、审计链

所有 AI 思考的输入和结论都留存，形成完整可回溯的审计链：

```
context_snapshots (完整决策快照: 行情+状态)
  ├── reasoning_records (LLM 推理链: 观察→假设→验证→结论)
  ├── judgments (只读提案: ConservativeShadowProvider 或外部 LLM)
  └── paper_executions / paper_orders (执行结果: PaperBroker 硬规则检查后成交)
```

每一轮看盘的完整记录：
1. **context capture** -- 行情 + 账户状态 + 持仓 + 预期 + 池 + 证据 + 历史观察，冻结成一个 `DecisionContext`，sha256 指纹去重
2. **reasoning add** -- LLM 的推理过程，结构化四段式（observed/hypothesis/verified/conclusion）
3. **analyze** -- 基于 context 生成只读提案（BUY/SELL/WAIT/RESEARCH）
4. **paper execute** -- 提案经 PaperBroker 13 条硬规则检查后成交

回溯时可以查看："这一轮看到了什么、想到了什么、验证了什么、最终结论是什么、执行了什么"。

---

## 六、一个完整交易日

```
9:00 盘前
  brain: trader brief + trader thesis list + trader pool list + astock 历史板块排名
  brain: "基于昨日数据和当前预期, 今日关注PCB。预案: 三维齐->BUY 603127"
  brain: 写盘前分析.md

9:30 开盘, 看盘循环
  Round 1:
    brain: trader brief -> astock live index/block rank/quote(持仓)
    brain: trader context capture -> 构建上下文快照
    brain: "无信号。写heartbeat。"

  Round 2 (10:30):
    brain: trader brief -> astock live block rank -> "PCB排第3, 3只涨停"
    brain: astock live block members 880904 -> "沪电领涨8.5%"
    brain: astock live minute 600463 -> "放量突破"
    brain: trader thesis list --active-only -> "PCB active"
    brain: trader evidence list --thesis pcb_thesis -> "昨夜公告催化确认"
    brain: trader context capture -> 构建上下文快照
    brain: trader context reasoning add --context <id> \
      --observed "PCB排第3，3只涨停" \
      --hypothesis "AI硬件需求拉动PCB放量" \
      --verified "沪电领涨8.5%，深南盘中跟进" \
      --conclusion "三维确认，BUY 603127 100股"
    brain: trader analyze latest -> 生成提案
    brain: trader paper execute -> PaperBroker 9条规则检查 -> 成交 -> 记SQLite
    brain: "已买入。写heartbeat。"

  Round 3-N:
    brain: trader brief -> astock live index/quote -> "持仓603127涨3%, 持有。"
    ... (直到收盘)

15:00 收盘
  brain: trader paper history/audit -> astock 历史板块排名
  brain: "今日操作: 买入603127 100股。PCB方向5只涨停, 比昨日更强。"
  brain: 写复盘.md
```

---

## 七、实施进度

### 阶段总览

| Phase | 名称 | 核心结果 | 状态 |
|------|------|---------|------|
| 0 | 工程骨架 | 可安装、可测试的 `trader` CLI | 已完成 |
| 1 | 可控历史回放 | 按模拟时钟读取历史数据并断点恢复 | 已完成 |
| 2 | 实时影子数据 | 获取、校验、展示并保存真实持仓快照 | 已完成 |
| 3 | 只读 AI 判断 | 基于真实快照产生结构化提案，不修改账户 | 已完成 |
| 4 | 模拟交易闭环 | 风险校验、模拟成交、账户和报告闭环 | 已完成 |
| 5 | 精简重构 | 删 tools/watch，行情统一走 astock，context 全量留存 + LLM 推理链 | 已完成 |
| 6 | 实时看盘循环 | brain 自主调工具看盘，PaperBroker 拦规则执行 | 未开始 |

### Phase 0-4 已完成内容

**Phase 0**（工程骨架）：Typer CLI、Pydantic 模型、astock 封装、日志异常配置、pytest 结构。

**Phase 1**（历史回放）：ReplayClock 按分钟推进、SQLite checkpoint、断点恢复、同一参数重复运行结果一致。

**Phase 2**（实时影子数据）：LiveMarketData 获取批量报价、代码校验（缺失/重复/零价格）、涨跌幅交叉验证。

**Phase 3**（只读 AI 判断）：JudgmentContext/Proposal/Report/Record 模型、ConservativeShadowProvider 保守占位（大幅波动->RESEARCH，其余->WAIT）、输出校验（快照ID/Provider/Model/股票集合）、失败重试、SQLite 审计。独立账户/持仓/预期/观察池/风险因子/证据/完整决策上下文 v2 均已落地。

**Phase 4**（模拟交易闭环）：PaperBroker 9 条买入硬规则（冷却/重复/可交易/主板/100股/现金/单仓/总仓/截止）+ 4 条卖出硬规则（T+1/可卖/100股/持仓存在）。`BEGIN IMMEDIATE` 事务 + `(账户,判断)` 唯一约束保证幂等。订单/成交/事件审计。从 SQLite 原子生成 state.md/trades.md/日报。

### Phase 5：精简重构（已完成）

**目标**：删 tools/watch 命令族，行情统一走 astock，context 作为完整决策快照留存，加 LLM 推理链。

**完成内容**：

1. **删 tools 命令族** -- 查询回归资源命令（`account show`/`position list`/`thesis list --active-only`/`pool list`/etc.），保留 `brief`（跨资源聚合有独立价值）
2. **删 watch 命令 + live_snapshots 表** -- 行情不单独存表，brain 直接调 astock
3. **改造 context capture** -- 行情从 astock 直读，存入 `context_json`，不存独立行情表。`market_snapshot_id` 改为快照内容的 sha256（确定性，同一快照同一 ID）
4. **改造 analyze** -- `ReadOnlyAnalyzer.analyze()` 接收 `DecisionContextRecord`（行情已在 context 内），不再需要独立行情表
5. **改造 paper execute** -- staleness 检测改为 `_assert_core_context_fresh`（比对当前 SQLite 状态 vs context 捕获时状态），不依赖行情重建
6. **加 LLM reasoning** -- `reasoning_records` 表 + `ReasoningRecord` 模型 + `trader context reasoning add/list` 命令，结构化四段式推理链（observed/hypothesis/verified/conclusion）
7. **默认账户名统一为 "paper"** -- 所有资源命令默认账户从 "default" 改为 "paper"

**删除的命令**：
- `trader watch` / `trader watch latest` -- 行情不单独存表
- `trader tools get-*` / `trader tools audit` -- 查询回归资源命令
- `trader context build` -- 行情不再持久化，无法用旧快照重建

78 个测试通过。

### Phase 6：实时看盘循环（下一步）

**目标**：LLM API 全自动看盘。

**范围**：
- 实现 LLM Brain + 编排器。
- 定义工具 JSON schema，支持 LLM function calling。
- 编排器自动循环：brief -> LLM -> tool calls -> trader -> result -> LLM -> decision -> sleep -> repeat。
- 收盘自动退出，生成每日报告。
- 支持人工中断和恢复。

---

## 八、项目结构

```text
trading_engine/
├── pyproject.toml
├── src/trading_engine/
│   ├── storage.py              # SQLite 状态管理
│   ├── paper.py                # PaperBroker 硬规则
│   ├── paper_store.py          # 成交审计
│   ├── context_store.py        # 证据/上下文/推理链存储
│   ├── context_models.py       # DecisionContext + ReasoningRecord 等模型
│   ├── context.py             # DecisionContextBuilder
│   ├── context_cli.py          # context capture/replay/show + reasoning add/list
│   ├── analysis.py             # ReadOnlyAnalyzer + ConservativeShadowProvider
│   ├── models.py              # 数据模型
│   ├── live.py                # LiveMarketData（组合快照流程保留）
│   ├── astock.py              # AstockClient 封装
│   ├── brief.py               # BriefGenerator（跨资源聚合）
│   ├── cli.py                 # 命令注册
│   └── protocols.py           # TradingBrain 协议（待实现）
│
├── brain/                      # 可插拔 brain 实现（待创建）
│   ├── shadow.py               # 确定性测试 brain
│   ├── llm.py                  # LLM API brain + 编排器
│   └── agent.py                # 外部 agent brain（Qoder）
│
├── tests/
│   ├── test_brief.py           # brief 逻辑测试
│   ├── test_context.py         # context 构建测试
│   ├── test_analysis.py        # analyzer 测试
│   ├── test_paper.py           # PaperBroker 测试
│   ├── test_reasoning.py       # LLM 推理链测试
│   ├── test_storage.py         # SQLite 存储测试
│   ├── test_cli.py            # CLI 集成测试
│   └── test_skill_regression_20260727.py  # 全链路回归测试
│
└── data/
    └── trader.db               # SQLite
```

---

## 九、数据职责

| 数据 | 唯一入口或存储 | 说明 |
|------|---------------|------|
| 行情 | astock CLI | brain 直接调用；trader 不做行情代理 |
| Agent 运行状态 | SQLite | run、checkpoint、错误和恢复位置 |
| 独立账户 | SQLite | 现金、持仓和上下文基础状态 |
| 订单和成交 | SQLite | 经过规则校验的模拟执行记录 |
| 决策上下文 | SQLite (context_snapshots) | 完整决策快照：行情+状态+证据+历史，冻结去重 |
| LLM 推理链 | SQLite (reasoning_records) | 每轮 context 的观察→假设→验证→结论 |
| 决策审计 | SQLite | 输入摘要、AI提案、规则校验和执行结果 |
| 研究知识 | SQLite | 独立维护预期、固定池、催化和风险因子 |
| 人类可读报告 | Markdown | 从结构化状态生成或引用结构化记录 |
| 密钥和凭证 | 环境变量 | 禁止写入 SQLite 和 Git |

---

## 十、下一步

Phase 0-5 已完成。Phase 6 接入 LLM API 实现全自动看盘循环：

1. 实现 LLM Brain + 编排器
2. 定义工具 JSON schema
3. 编排器自动循环：brief -> LLM -> tool calls -> context capture -> reasoning -> analyze -> execute -> sleep -> repeat
4. 收盘自动退出，生成每日报告
