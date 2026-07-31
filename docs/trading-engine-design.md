# Trading Engine — AI 交易引擎设计

> 状态：Phase 0-4 已完成；Phase 5 Step 1 已完成（含 astock replay 分钟级回放架构）
> 定位：trader 是有记忆、有规则、无大脑的工具网关；brain 从外部插入，通过 CLI 调用工具做交易判断

---

## 一、这是什么

一个 AI 交易引擎。**AI 是投资者**（做分析和决策），**trader 是 AI 的眼睛和手**（拿数据 + 执行交易 + 拦规则）。

```
brain (可插拔)           trader (工具网关)           底层
┌──────────┐           ┌─────────────────┐         ┌──────────┐
│ Qoder    │──CLI──→   │ 包装 astock     │──→      │ astock   │
│ LLM API  │           │ SQLite 记忆     │         │ (行情)   │
│ Shadow   │           │ PaperBroker 规则 │         │ SQLite   │
└──────────┘           └─────────────────┘         └──────────┘
```

brain 只跟 trader 说话。trader 内部路由到 astock（数据）、SQLite（状态）、PaperBroker（规则）。

三种 brain 可以互换，同一组 `trader tools` 命令：

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
AI读规则md → 理解偏差 → 走错分支 → 事后发现 → 改md → 下次又理解错
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

与之前方案的区别：

| 维度 | 旧方案 (Qoder Skill) | LangGraph v0.2 | 本方案 (工具调用 v1.0) |
|------|---------------------|----------------|----------------------|
| 判断主体 | AI | AI | AI（不变） |
| 数据获取 | AI 调 Bash | 代码预组装给 AI | brain 调 trader tools 按需取 |
| 上下文 | 一个 session 越跑越长 | 每节点独立 | 每轮工具调用独立 |
| 流程 | AI 自觉走 | 状态机强制骨架 | brain 自主决定 |
| 规则 | AI 读 md 自觉遵守 | 代码 if-else 路由 | PaperBroker 代码拦死 |
| 数据量 | 全量 | 全量 | 渐进式（brain 决定看什么） |
| brain 可插拔 | 否 | 否 | 是（CLI 统一接口） |

放弃 LangGraph 状态机的原因：状态机预设了流程路径（route_after_ai），仍是代码决定"走哪条路"。工具调用从根本上不同——**brain 自己决定调什么工具、什么顺序、什么时候停**，trader 不预设路径。

---

## 三、架构

### 三层分离

```
┌──────────────────────────────────────────────────┐
│              brain (可插拔判断层)                  │
│                                                  │
│  Qoder / LLM API / Shadow / 任何 agent            │
│  读 brief → 调 trader tools → 思考 → 决策         │
└──────────────────┬───────────────────────────────┘
                   │ 只调 trader CLI
                   ↓
┌──────────────────────────────────────────────────┐
│           trader (工具网关，headless)              │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐      │
│  │ astock   │  │ SQLite   │  │ PaperBroker│      │
│  │ (行情)   │  │ (状态)   │  │ (硬规则)    │      │
│  │          │  │          │  │            │      │
│  │行情数据   │  │账户/持仓  │  │T+1/主板/   │      │
│  │板块排名   │  │预期/池    │  │100股/仓位/ │      │
│  │涨停/分时  │  │证据/风险  │  │冷却/重复/  │      │
│  │          │  │预案/成交  │  │敞口/截止   │      │
│  └──────────┘  └──────────┘  └────────────┘      │
│                                                  │
│  校验 + 审计 + 回放支持                            │
└──────────────────────────────────────────────────┘
```

trader 包装 astock 不是多余转发，而是在中间做了：

| 增值 | 说明 |
|------|------|
| 校验 | 检查缺失代码、零价格、涨跌幅不匹配 |
| 审计 | 每次工具调用记 SQLite，brain 调了什么、返回了什么 |
| 回放 | ReplayMarketData 是 LiveMarketData 的透明替换，brain 不用改代码 |
| 统一格式 | 所有工具同一出口、同一种 JSON、同一套错误处理 |

### 核心原则

1. trader 是有记忆、有规则、无大脑的工具网关；brain 从外部插入。
2. 渐进式取数：brain 自己决定看什么数据，trader 不预组装全量上下文。
3. 硬规则（T+1、主板、100 股等）在 PaperBroker 代码层拦死，brain 无法绕过。
4. 同一组 `trader tools` CLI 对所有 brain 实现统一可用；切换 brain 不需要改 trader。
5. SQLite 保存状态和审计；Markdown 作为面向人的报告。
6. trader 完全独立，不读取或要求存在原 trading-system Skill。
7. trader 只通过 astock CLI 获取行情，不直接访问 ClickHouse 或 TDX。
8. 模拟回放在任意时点只能使用该时点之前可获得的数据，禁止未来数据泄漏。

---

## 四、工具清单

> 全部命令默认输出 JSON（brain 友好）。`fetch-*` 走 astock 实时拉数据（秒级），`get-*` 读 SQLite 本地状态（毫秒级）。

### 4.1 开局

#### `trader brief`

**作用**：每轮开始时给 brain 的最小信息——不预取行情数据。brain 拿到后知道"我有什么、我在关注什么"，然后自己决定调什么工具。

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

### 4.2 行情数据（包装 astock，加校验 + 审计 + 回放）

#### `trader tools fetch-index`

**作用**：拉六大指数行情。默认实时，传 `--replay-date` 从指数分钟线重建报价。返回上证、深证、创业板指、上证50、沪深300、中证1000 的价格/涨跌幅/成交额。

Replay 模式下传 `--replay-time HH:MM` 可精确到分钟：trader 调 `astock replay index <date> <time>` 从 ClickHouse 分钟线重建到该时间点的指数报价。不传则返回全天收盘。

```bash
trader tools fetch-index                                          # 实时（默认）
trader tools fetch-index --replay-date 20260730                  # 历史全天收盘
trader tools fetch-index --replay-date 20260730 --replay-time 10:30  # 历史 10:30 指数价
```

```json
[
  {"code": "000001", "name": "上证指数", "price": 3832.26, "pre_close": 3804.69, "change_pct": 0.72, "amount": 1187681533952},
  {"code": "399001", "name": "深证成指", "price": 13578.93, "change_pct": 2.21},
  {"code": "399006", "name": "创业板指", "price": 3343.96, "change_pct": 3.06},
  {"code": "000016", "name": "上证50", "price": 2922.97, "change_pct": -0.12},
  {"code": "000300", "name": "沪深300", "price": 4588.20, "change_pct": 0.85},
  {"code": "000852", "name": "中证1000", "price": 7075.51, "change_pct": 2.53}
]
```

brain 用途：判断今日大盘强弱、风格轮转（大票强还是小票强）。

#### `trader tools fetch-block-rank`

**作用**：拉板块涨幅排名。默认实时，传 `--replay-date` 拉历史板块排名。返回概念板块+风格板块，按涨幅降序，带涨停家数。

Replay 模式下传 `--replay-time HH:MM` 可精确到分钟：trader 调 `astock replay block rank <date> <time>` 从板块分钟线重建到该时间点的排名（10:30 的板块排名和 15:00 收盘排名完全不同）。不传则返回收盘终值排名。

```bash
trader tools fetch-block-rank --limit 10                      # 实时前10
trader tools fetch-block-rank --limit 50                       # 实时前50（快扫全覆盖）
trader tools fetch-block-rank --replay-date 20260730 --limit 50  # 历史收盘排名
trader tools fetch-block-rank --replay-date 20260730 --replay-time 10:30 --limit 50  # 历史 10:30 板块排名
```

```json
[
  {"code": "880958", "name": "AI营销", "block_type": "concept", "change_pct": 8.66, "amount": 45035692032, "limit_up_count": 13},
  {"code": "880579", "name": "智谱AI", "change_pct": 7.35, "limit_up_count": 8},
  {"code": "880654", "name": "ChatGPT", "change_pct": 6.44, "limit_up_count": 16}
]
```

brain 用途：快扫第一层——发现今日最强方向。`limit_up_count` 判断板块集体爆发程度。

#### `trader tools fetch-stock-quote`

**作用**：查个股报价。默认实时，传 `--replay-date` 从分钟线重建历史报价。返回价格/涨跌幅/开高低/量额。带代码校验（拒绝不匹配、拒绝零价格）。

Replay 模式下传 `--replay-time HH:MM` 可精确到分钟：trader 调 `astock replay quote <codes> <date> <time>` 从分钟线重建到该时间点的报价。不传则返回全天收盘。

```bash
trader tools fetch-stock-quote 000021 603127                              # 实时多只
trader tools fetch-stock-quote 000021                                       # 实时一只
trader tools fetch-stock-quote 000021 --replay-date 20260730 --replay-time 10:30  # 历史 10:30 报价
trader tools fetch-stock-quote 000021 --replay-date 20260730                # 历史全天收盘
```

```json
[
  {"code": "000021", "price": 37.23, "pre_close": 36.42, "change_pct": 2.22, "volume": 1574028, "amount": 6071401472, "open": 39.5, "high": 39.51, "low": 37.21},
  {"code": "603127", "price": 41.54, "pre_close": 40.05, "change_pct": 3.72, "volume": 467933, "amount": 1974018560, "open": 40.1, "high": 43.5, "low": 40.09}
]
```

brain 用途：查持仓股最新价、查预案目标股是否到买点。

#### `trader tools fetch-block-members`

**作用**：查板块成分股清单 + 个股行情。传6位板块代码，返回成分股按涨幅降序排列，含 close/change_pct/amount/turnover/limit_status。

三种模式：
- **Live**：调 `live block members`，实时 TDX 报价。
- **Replay 无 time**：调 `query block members <date>`，日线收盘数据。
- **Replay 有 time**：调 `replay block members <date> <time>`，从个股分钟线重建指定时间点的价格。涨停股有分钟数据（data_source="minute"），非涨停股回退到日线收盘价（data_source="daily"）。

```bash
trader tools fetch-block-members 880904                                      # 实时成分股涨幅榜
trader tools fetch-block-members 880904 --replay-date 20260730                # 收盘成分股涨幅榜
trader tools fetch-block-members 880904 --replay-date 20260730 --replay-time 10:30  # 10:30 成分股涨幅榜
```

```json
[
  {"code": "300290", "name": "ST荣科", "close": 4.88, "pre_close": 4.07, "change_pct": 19.9, "amount": 325412288, "turnover": 10.87, "limit_status": "-", "data_source": "minute"},
  {"code": "002212", "name": "天融信", "close": 6.0, "change_pct": 10.09, "limit_status": "涨停", "data_source": "daily"}
]
```

brain 用途：快扫第二层——发现具体板块里哪只票领涨、哪只涨停了。板块代码从 `fetch-block-rank` 的返回值获取。

#### `trader tools fetch-limit-list`

**作用**：查涨停/跌停清单。基于日线数据，带连板数+概念标签。支持指定日期复盘、排除ST、看跌停。

Replay 模式下传 `--replay-time HH:MM` 可精确到分钟：trader 调 `astock replay limit list <date> <time>` 返回分钟级涨停状态——每只票标注 sealed（封板中）/broken（炸板）/pending（尚未涨停），并带 first_seal_time（首封时间）。不传则返回日线终值涨停清单。

```bash
trader tools fetch-limit-list                     # 最近交易日涨停
trader tools fetch-limit-list --side down         # 跌停清单
trader tools fetch-limit-list --exclude-st         # 排除ST
trader tools fetch-limit-list --date 20260731      # 指定日期复盘
trader tools fetch-limit-list --replay-date 20260730  # 同 --date，replay 模式
trader tools fetch-limit-list --replay-date 20260730 --replay-time 10:30  # 10:30 涨停状态
```

```json
[
  {"code": "000533", "name": "顺纳股份", "board": "main", "close": 11.56, "limit_price": 11.56, "change_pct": 9.99, "amount": 2148432128, "consecutive_days": 4, "concepts": ["临界发电", "可控核变", "百度概念"]},
  {"code": "002195", "name": "岩山科技", "close": 6.83, "consecutive_days": 1, "concepts": ["云游戏", "AI手机PC", "短剧游戏"]}
]
```

brain 用途：快扫第三层+盘后复盘——看哪些票涨停了、连板几天、属于哪些概念。

#### `trader tools fetch-limit-ladder`

**作用**：连板天梯。还封涨停的票按连板天数排序，5连板在最前面。默认最近交易日，传 `--replay-date` 查历史。

Replay 模式下传 `--replay-time HH:MM` 可精确到分钟：trader 调 `astock replay limit ladder <date> <time>` 仅统计当时仍封板的票（sealed 状态），排除已炸板的。不传则返回日线终值连板天梯。

```bash
trader tools fetch-limit-ladder                          # 最近交易日
trader tools fetch-limit-ladder --replay-date 20260730  # 指定日期
trader tools fetch-limit-ladder --replay-date 20260730 --replay-time 10:30  # 10:30 连板天梯
```

```json
[
  {"code": "603221", "name": "爱丽家居", "consecutive_days": 5, "close": 16.94, "change_pct": 10.0},
  {"code": "000533", "name": "顺纳股份", "consecutive_days": 4, "concepts": ["临界发电", "可控核变"]},
  {"code": "002388", "name": "新亚制程", "consecutive_days": 3}
]
```

brain 用途：判断市场情绪温度——连板天数越高说明赚钱效应越强。

#### `trader tools fetch-market-scan`

**作用**：全市场扫描。默认实时扫全市场3000+只票，返回异动候选（涨停/急涨/大额）+ 成交额榜。传 `--replay-date` 返回历史市场全景（涨跌家数+涨停数+成交额排行）。和 `fetch-limit-list` 的区别：这个是全市场扫描异动候选，`limit-list` 是基于日线终值的完整涨停清单。

Replay 模式下传 `--replay-time HH:MM` 可精确到分钟：trader 调 `astock replay market <date> <time>` 从分钟线重建到该时间点的涨跌家数和涨停数（仅覆盖已同步分钟线的股票，通常为涨停股+持仓股）。不传则返回日线终值全景。

```bash
trader tools fetch-market-scan                          # 实时全市场扫描
trader tools fetch-market-scan --replay-date 20260730  # 历史收盘全景
trader tools fetch-market-scan --replay-date 20260730 --replay-time 10:30  # 历史 10:30 全景
```

```json
{
  "coverage_mode": "full_market",
  "universe_count": 3009,
  "scanned_count": 2998,
  "missing_quote_count": 11,
  "candidate_codes": ["002281", "002384", "002463", "600183", "600667", "601138"],
  "limit_up_codes": ["600667"],
  "candidates": [
    {"code": "002384", "name": "东山精密", "price": 171.48, "change_pct": 5.98, "amount": 21468493824, "low": 170.32}
  ],
  "top_amount": [...]
}
```

brain 用途：发现全市场异动票——不局限于特定板块，看哪些票在放量急涨。

### 4.3 状态记忆（从 SQLite，brain 的记忆）

#### `trader tools get-account`

**作用**：查账户状态。返回余额、初始资金、冷却标志。

```bash
trader tools get-account --account paper
```

```json
{"id": "ba7f...", "name": "paper", "initial_cash": "100000", "cash": "20229.4", "cooldown": false}
```

brain 用途：知道自己有多少钱可以买。`cooldown=true` 表示触发冷静期，不能买入。

#### `trader tools get-positions`

**作用**：查持仓明细。返回每只票的代码/名称/数量/可卖数量/成本/买入日期。

```bash
trader tools get-positions --account paper
```

```json
[
  {"code": "000021", "name": "深科技", "quantity": 400, "sellable_quantity": 400, "average_cost": "38.73", "bought_on": "2026-07-22"},
  {"code": "000636", "name": "风华高科", "quantity": 500, "sellable_quantity": 0, "average_cost": "43.3", "bought_on": "2026-07-27"}
]
```

brain 用途：知道持有什么、可卖多少（T+1限制）。`sellable_quantity=0` 说明是今天买的不能卖。

#### `trader tools get-theses`

**作用**：查预期列表。返回所有投资预期（active/watch/archived）。`--active-only` 只返回活跃的。

```bash
trader tools get-theses                       # 全部预期
trader tools get-theses --active-only         # 只看活跃的
```

```json
[
  {"key": "memory_chip", "title": "存储芯片", "status": "active", "summary": "长链直接受益", "realization_condition": "价格拐点确认", "invalidation_condition": "价格创新低"}
]
```

brain 用途：知道自己在跟踪什么方向、什么条件算确认/失效。

#### `trader tools get-pools`

**作用**：查观察池。返回每个池的成员股、关联预期、监控状态。`--status active` 只看活跃池。输出含每个池的 members 子列表。

```bash
trader tools get-pools                        # 全部池
trader tools get-pools --status active        # 只看活跃池
```

```json
[
  {"key": "memory_pool", "name": "存储池", "thesis_key": "memory_chip", "status": "active", "members": [
    {"code": "000021", "name": "深科技"},
    {"code": "000636", "name": "风华高科"}
  ]}
]
```

brain 用途：知道每个方向的轮转池里有哪些票在监控。

#### `trader tools get-evidence`

**作用**：查证据记录。返回支撑/反驳预期的市场证据。`--thesis` 按预期过滤。

```bash
trader tools get-evidence                     # 全部证据
trader tools get-evidence --thesis memory_chip  # 只看存储芯片的证据
```

```json
[
  {"thesis_id": "8128...", "thesis_key": "memory_chip", "kind": "market", "source_name": "2026-07-27收盘审计", "stance": "supports", "reliability": "medium", "summary": "长篇直接池5/6上涨且深科技收涨4.67%结构确认保留"}
]
```

brain 用途：回顾某个预期有哪些已经确认的证据，支撑还是反驳。

#### `trader tools get-risk`

**作用**：查风险因子。返回主题风险做口上限（如“创新药风险30%”限制该方向最大仓位）。

```bash
trader tools get-risk
```

```json
[
  {"key": "innovation_risk", "name": "创新药主题风险", "max_exposure_pct": "30", "active": true},
  {"key": "tech_hardware", "name": "科技硬件共同风险", "max_exposure_pct": "60", "active": true}
]
```

brain 用途：买入前检查仓位上不超标。

#### `trader tools get-plans`

**作用**：查今日预案。盘前制定的买入/卖出计划，含目标股/数量/触发条件/优先级。`--date` 指定日期。

```bash
trader tools get-plans                        # 今天的预案
trader tools get-plans --date 2026-07-31      # 指定日期
```

```json
[]
```

brain 用途：看盘前制定的计划，盘中判断是否触发条件。

#### `trader tools get-history`

**作用**：查交易历史。返回 paper 账户的订单和成交流水。

```bash
trader tools get-history --account paper
```

```json
[]
```

brain 用途：回顾最近做了什么交易，盘后复盘用。

### 4.4 审计

#### `trader tools audit`

**作用**：对账。检查订单数=成交数，数据一致性。brain 执行交易后用这个验证没出错。

```bash
trader tools audit --account paper
```

```json
{"account_id": "ba7f...", "account_name": "paper", "orders": 0, "fills": 0, "valid": true, "issues": []}
```

brain 用途：交易后验证数据完整性。`valid=false` 说明有数据不一致。

### 4.5 执行（Phase 5 Step 2，尚未实现）

以下命令在设计中但尚未实现。PaperBroker 的 `execute_judgment()` 当前需要 JudgmentRecord + DecisionContext，需要拆出直接执行路径。

```bash
trader tools submit-buy 603127 100            # → 9 条硬规则检查 → 成交
trader tools submit-sell 603127 100           # → 4 条硬规则检查 → 成交
```

### 4.6 两类数据的核心区别

| 维度 | fetch-*（行情） | get-*（记忆） |
|------|----------------|---------------|
| 数据源 | astock 实时拉取 | SQLite 本地查询 |
| 速度 | 秒级 | 毫秒级 |
| 用途 | 看市场发生了什么 | 看自己有什么、关注什么 |
| 典型用法 | 每轮快扫调 | brief 后补充查细节 |

### 4.7 Live 模式 vs Replay 模式

所有 fetch-* 命令支持两种模式，brain 调同一个命令，trader 内部路由到不同数据源：

| 模式 | 触发方式 | 数据源 | 用途 |
|------|---------|-------|------|
| Live（默认） | 不传 --replay-date | `astock live ...` 实时 | 真实看盘 |
| Replay | `--replay-date YYYYMMDD` | `astock replay ...` 从 ClickHouse 重建 | 模拟看盘 |

Replay 模式下所有命令都支持 `--replay-time HH:MM` 精确到分钟。trader 调 `astock replay <command> <date> [time]`，astock 从 ClickHouse 分钟线重建到该时间点的行情。不传 `--replay-time` 则返回日线终值。

每个命令在 replay 模式下的 astock 路由：

| 命令 | Live | Replay（无 time） | Replay（有 time） |
|------|------|-------------------|-------------------|
| `fetch-index` | `live index` | `replay index <date>` | `replay index <date> <time>` |
| `fetch-block-rank` | `live block rank` | `replay block rank <date>` | `replay block rank <date> <time>` |
| `fetch-stock-quote` | `live quote` | `replay quote <codes> <date>` | `replay quote <codes> <date> <time>` |
| `fetch-block-members` | `live block members` | `query block members <date>` | `replay block members <date> <time>` |
| `fetch-limit-list` | `query limit` | `query limit <date>` | `replay limit list <date> <time>` |
| `fetch-limit-ladder` | `query limit ladder` | `query limit ladder <date>` | `replay limit ladder <date> <time>` |
| `fetch-market-scan` | `live market` | `replay market <date>` | `replay market <date> <time>` |

**数据准备**：Replay 模式需要先同步分钟线数据。运行 `astock replay prepare <date>` 一次性同步当日所需全部数据（指数/板块 daily+1m、全市场股票 daily、涨停股 1m）。运行 `astock replay check <date>` 检查数据完整性。

用法示例：

```bash
# Live 模式（真实看盘）
trader tools fetch-index
trader tools fetch-stock-quote 000021

# Replay 模式（模拟看盘）
astock replay prepare 20260730        # 先同步数据
trader tools fetch-index --replay-date 20260730 --replay-time 10:30
trader tools fetch-block-rank --replay-date 20260730 --replay-time 10:30 --limit 10
trader tools fetch-stock-quote 000021 --replay-date 20260730 --replay-time 10:30
trader tools fetch-limit-list --replay-date 20260730 --replay-time 10:30
trader tools fetch-limit-ladder --replay-date 20260730 --replay-time 10:30
trader tools fetch-market-scan --replay-date 20260730 --replay-time 10:30
```

### 4.8 brain 典型调用流程

**Live 模式（真实看盘）：**

```
brief → 知道状态
  → fetch-index → 看大盘
  → fetch-block-rank → 看板块（发现PCB强）
  → fetch-limit-ladder → 看连板天梯（市场情绪）
  → fetch-block-members 880904 → 看PCB具体哪些票涨
  → fetch-stock-quote 000021 000636 → 看持仓股最新价
  → get-theses --active-only → 看活跃预期
  → get-evidence --thesis memory_chip → 看已有证据
  → [思考: 三维齐 → 买]
  → submit-buy 000021 100 → PaperBroker 9条规则检查 → 成交
  → audit → 验证数据一致性
```

**Replay 模式（模拟看盘）：**

```
astock replay prepare 20260730  →  同步当日全部数据（指数/板块/涨停股分钟线）
brief → 知道状态
  → fetch-index --replay-date 20260730 --replay-time 10:30 → 看当时大盘
  → fetch-block-rank --replay-date 20260730 --replay-time 10:30 → 看当时板块排名
  → fetch-block-members 880904 --replay-date 20260730 --replay-time 10:30 → 看当时板块成分股涨幅
  → fetch-stock-quote 000021 --replay-date 20260730 --replay-time 10:30 → 看当时报价
  → fetch-limit-list --replay-date 20260730 --replay-time 10:30 → 看当时涨停状态（sealed/broken/pending）
  → fetch-limit-ladder --replay-date 20260730 --replay-time 10:30 → 看当时连板天梯
  → fetch-market-scan --replay-date 20260730 --replay-time 10:30 → 看当时市场全景
```

---

## 五、Brain 协议

### 核心接口

brain 只需要做一件事：**看 brief、调工具、做判断、输出决策。**

```python
class TradingBrain(Protocol):
    def see_and_decide(self, brief: str, tools: list[ToolSchema]) -> BrainResult:
        """读 brief → 调工具 → 思考 → 输出决策"""
        ...
```

`BrainResult` 只有三种：
- `WAIT` — 无信号，继续下一轮
- `TRADE` — 买卖决策（code + action + quantity + reason）
- `RESEARCH` — 需要离线研究

### Qoder Brain（对话式）

用户在 Qoder 中说"开始看盘"，Qoder 充当 brain：

```
用户: 开始看盘
Qoder:
  → Bash: trader brief                        → 读状态
  → Bash: trader tools fetch-index            → 看指数
  → Bash: trader tools fetch-block-rank      → 看板块
  → Bash: trader tools fetch-stock-quote 603127 → 看持仓
  [思考: PCB走强, 需要深挖]
  → Bash: trader tools fetch-block-members PCB
  → Bash: trader tools fetch-stock-minute 600463
  → Bash: trader tools get-theses
  → Bash: trader tools get-evidence pcb_thesis
  [思考: 三维齐, 买]
  → Bash: trader tools submit-buy 603127 100
  → Write: 看盘.md
  "已买入603127 100股。说'继续'扫描下一轮。"
```

Qoder 的对话循环就是 brain 循环。用户说"继续"触发下一轮。

### LLM Brain（全自动）

编排器脚本做对话循环做的事，但全自动：

```python
while market_open():
    brief = run_cli("trader brief --json")
    messages = [{"role": "system", "content": RULES}, {"role": "user", "content": brief}]

    while True:
        response = llm.chat(messages, tools=TOOL_SCHEMAS)
        if response.tool_calls:
            for call in response.tool_calls:
                result = run_cli(f"trader tools {call.name} {call.args}")
                log_to_sqlite(call, result)
                messages.append(tool_result(call, result))
        else:
            log_decision(response.content)
            break

    sleep(60)
```

启动：`trader watch --brain llm --model gpt-4o --interval 60`

编排器不做任何判断，只翻译 LLM API ↔ trader CLI。

### Shadow Brain（测试）

确定性占位，调用固定工具检查固定条件：

```python
def see_and_decide(self, brief, tools):
    quotes = tools.call("fetch_stock_quote", codes=["603127"])
    if any(q.change_pct > 10 for q in quotes):
        return BrainResult(action="RESEARCH", reason="大幅波动需研究")
    return BrainResult(action="WAIT", reason="无信号")
```

### 规则怎么给 brain

硬规则（T+1、主板、100 股等）不需要给 brain——PaperBroker 在代码层拦死。brain 调 `submit-buy` 时规则自动检查，绕不过去。

软规则（三维确认、买点判断、预期归因等）在 brain 的 system prompt 或 SKILL.md 中。LLM brain 每轮 system prompt 含完整规则；Qoder brain 自带 SKILL.md 零上下文完备性。

---

## 六、一个完整交易日

```
9:00 盘前
  brain: trader brief + get-theses + get-pools + get-plans + fetch-block-rank(昨日)
  brain: "基于昨日数据和当前预期, 今日关注PCB。预案: 三维齐→BUY 603127"
  brain: 写盘前分析.md

9:30 开盘, 看盘循环
  Round 1:
    brain: trader brief → fetch-index → fetch-block-rank → fetch-stock-quote(持仓)
    brain: "无信号。写heartbeat。"

  Round 2 (10:30):
    brain: trader brief → fetch-block-rank → "PCB排第3, 3只涨停"
    brain: fetch-block-members PCB → "沪电领涨8.5%"
    brain: fetch-stock-minute 600463 → "放量突破"
    brain: get-theses → "PCB active"
    brain: get-evidence pcb_thesis → "昨夜公告催化确认"
    brain: "三维齐。submit-buy 603127 100"
    → PaperBroker: 9条规则检查 → 成交 → 记SQLite
    brain: "已买入。写heartbeat。"

  Round 3-N:
    brain: trader brief → fetch-index → fetch-stock-quote → "持仓603127涨3%, 持有。"
    ... (直到收盘)

15:00 收盘
  brain: get-history → audit → fetch-limit-list
  brain: "今日操作: 买入603127 100股。PCB方向5只涨停, 比昨日更强。"
  brain: 写复盘.md
```

### 两种 brain 的对比

| 维度 | Qoder 当 brain | LLM 当 brain |
|------|---------------|--------------|
| 循环 | 用户说"继续" → 一轮 | 编排器自动 `while market_open` |
| 工具调用 | Bash 调 `trader tools ...` | 编排器调 `trader tools ...` |
| 规则 | Qoder 读 SKILL.md | 规则写在 system prompt |
| 思考 | Qoder 在对话中推理 | LLM 在 API 调用中推理 |
| 上下文 | 每轮对话独立 | 每轮 API 调用独立 |
| 审计 | trader 记每次工具调用 | 编排器 + trader 双重记录 |
| 人工干预 | 天然有（对话式） | 需要 interrupt 机制 |

关键：两种 brain 用同一组 `trader tools`，同一套 PaperBroker 规则，同一个 SQLite 审计链。只是大脑换了。

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
| 5 | 工具调用架构 | trader 拆分为 headless 工具网关 + 可插拔 brain | 进行中 |
| 6 | 实时看盘循环 | brain 自主调工具看盘，PaperBroker 拦规则执行 | 未开始 |

### Phase 0-4 已完成内容

**Phase 0**（工程骨架）：Typer CLI、Pydantic 模型、astock 封装、日志异常配置、pytest 结构。

**Phase 1**（历史回放）：ReplayClock 按分钟推进、SQLite checkpoint、断点恢复、同一参数重复运行结果一致。

**Phase 2**（实时影子数据）：LiveMarketData 获取批量报价、代码校验（缺失/重复/零价格）、涨跌幅交叉验证、快照存 SQLite。

**Phase 3**（只读 AI 判断）：JudgmentContext/Proposal/Report/Record 模型、ConservativeShadowProvider 保守占位（大幅波动→RESEARCH，其余→WAIT）、输出校验（快照ID/Provider/Model/股票集合）、失败重试、SQLite 审计。独立账户/持仓/预期/观察池/风险因子/证据/完整决策上下文 v2 均已落地。68 个测试通过。

**Phase 4**（模拟交易闭环）：PaperBroker 9 条买入硬规则（冷却/重复/可交易/主板/100股/现金/单仓/总仓/截止）+ 4 条卖出硬规则（T+1/可卖/100股/持仓存在）。`BEGIN IMMEDIATE` 事务 + `(账户,判断)` 唯一约束保证幂等。订单/成交/事件审计。从 SQLite 原子生成 state.md/trades.md/日报。

### Phase 5：工具调用架构（当前）

**目标**：将 trader 从全量上下文架构重构为工具调用 + 可插拔 brain。

**背景**：Phase 0-4 的能力被包装在全量 `DecisionContextBuilder` 中——每轮给 brain 组装 20+ 字段上下文。实际使用中发现 brain 不需要这么多数据，大部分时间只需要扫一眼。需要从"全量预组装"切换为"brain 按需调工具"。

**范围**：
1. 将 `live.py` 和 `context.py` 的数据获取能力拆成独立工具函数，暴露为 `trader tools ...` CLI 命令。
2. 实现 `trader brief`，生成极简开局信息。不预取行情数据。
3. 定义 `TradingBrain` 协议，支持可插拔 brain 实现。
4. 实现 `ShadowBrain` 和 `trader watch --brain shadow`。
5. 在 Qoder 中充当 brain，端到端验证一轮真实看盘。
6. 每次工具调用记 SQLite，审计链覆盖 brain 的每一步数据获取。
7. `DecisionContextBuilder` 降为可选工具，brain 需要全量上下文时才调。

**Step 1 已完成**（工具拆分 + CLI 暴露 + `trader brief` + astock replay 分钟级回放）：
- `tools.py`：MarketDataTools（7 个 fetch-* 方法）+ BriefGenerator
- `tools_cli.py`：16 个 CLI 子命令（7 fetch-* + 8 get-* + audit）
- `trader brief` 输出 JSON 状态摘要（不预取行情）
- astock 端新增 `replay` 子命令树（8 个命令：prepare/check/index/block rank/quote/limit list/limit ladder/market）
  - 所有 replay 命令支持 `--replay-time HH:MM` 精确到分钟
  - 板块排名从分钟线重建（10:30 排名 ≠ 15:00 收盘排名）
  - 涨停状态分钟级判定：sealed（封板中）/broken（炸板）/pending（尚未涨停）
  - trader replay 方法从 ~120 行 Python 重建逻辑简化为 astock 命令调用（-70 行）
- 101 个测试全通过（原 88 + replay 测试 13）
- 端到端验证：所有命令逐个实跑通过

**Step 2 待完成**：
- `submit-buy/sell`：从 PaperBroker 拆出直接执行路径
- `ShadowBrain`：确定性 brain 端到端验证

**Step 3 待完成**：
- 在 Qoder 中充当 brain 跑一轮真实看盘
- 工具调用审计记 SQLite

**验收**：
- `trader brief` 输出 JSON，不含行情数据。✅
- 每个 `trader tools ...` 独立可调，返回 JSON。✅
- 所有 replay 命令支持分钟级回放（`--replay-time`）。✅
- `trader watch --brain shadow` 能跑完整循环，工具调用记 SQLite。⏳
- 在 Qoder 中说"开始看盘"能调 trader 工具完成一轮扫描。⏳
- Phase 0-4 的测试仍通过。✅（101 个全通过）

### Phase 6：实时看盘循环（下一步）

**目标**：LLM API 全自动看盘。

**范围**：
- 实现 LLM Brain + 编排器：`trader watch --brain llm --model gpt-4o --interval 60`。
- 定义工具 JSON schema，支持 LLM function calling。
- 编排器自动循环：brief → LLM → tool calls → trader → result → LLM → decision → sleep → repeat。
- 收盘自动退出，生成每日报告。
- 支持人工中断和恢复。

---

## 八、项目结构

```text
trading_engine/
├── pyproject.toml
├── src/trading_engine/
│   ├── storage.py              # SQLite 状态管理（已有，不动）
│   ├── paper.py                # PaperBroker 硬规则（已有，不动）
│   ├── paper_store.py          # 成交审计（已有，不动）
│   ├── context_store.py        # 证据/上下文存储（已有，不动）
│   ├── models.py               # 数据模型（已有，不动）
│   ├── live.py                 # LiveMarketData（已有，被 tools.py 复用）
│   ├── astock.py               # AstockClient 封装（已有，不动）
│   ├── tools.py                # ✅ MarketDataTools + BriefGenerator（新）
│   ├── tools_cli.py            # ✅ 16 个 tools 子命令 + brief（新）
│   ├── cli.py                   # ✅ 注册 tools_app + brief 命令（改）
│   └── protocols.py            # TradingBrain 协议（待实现）
│
├── brain/                      # 可插拔 brain 实现（待创建）
│   ├── shadow.py               # 确定性测试 brain
│   ├── llm.py                  # LLM API brain + 编排器
│   └── agent.py                # 外部 agent brain（Qoder）
│
├── tests/
│   ├── test_tools.py           # ✅ 工具单元测试（20 个）
│   ├── test_paper.py           # PaperBroker 测试（已有）
│   └── test_brain_shadow.py    # Shadow brain 端到端测试（待实现）
│
└── data/
    └── trader.db               # SQLite
```

### 现有代码改造

| 文件 | 动作 | 说明 |
|------|------|------|
| `storage.py` | 不动 | SQLite 状态管理已完成 |
| `paper.py` | 不动 | 硬规则护栏已完成 |
| `paper_store.py` | 不动 | 成交审计已完成 |
| `models.py` | 不动 | 数据模型已完成 |
| `live.py` | 拆 | 拆成独立工具函数 |
| `context.py` | 降级 | DecisionContextBuilder 降为可选工具 |
| `analysis.py` | 移出 | brain 实现移到 brain/ 目录 |
| `cli.py` | 加命令 | 加 trader brief + trader tools ... |

---

## 九、数据职责

| 数据 | 唯一入口或存储 | 说明 |
|------|---------------|------|
| 行情 | astock CLI（trader 包装） | trader 加校验+审计+回放；brain 不直接调 astock |
| Agent 运行状态 | SQLite | run、checkpoint、错误和恢复位置 |
| 实时影子快照 | SQLite | 经过代码、价格和涨跌幅校验的只读行情 |
| 独立账户 | SQLite | 现金、持仓和上下文基础状态 |
| 订单和成交 | SQLite | 经过规则校验的模拟执行记录 |
| 决策审计 | SQLite | 输入摘要、AI提案、规则校验和执行结果 |
| 工具调用审计 | SQLite（Phase 5起） | brain 每次调了什么工具、参数、返回结果 |
| 研究知识 | SQLite | 独立维护预期、固定池、催化和风险因子 |
| 人类可读报告 | Markdown | 从结构化状态生成或引用结构化记录 |
| 密钥和凭证 | 环境变量 | 禁止写入 SQLite 和 Git |

---

## 十、下一步

Phase 0-4 已完成。Phase 5 分三步，Step 1 已完成（含 astock replay 分钟级回放架构）：

1. ✅ **工具拆分 + CLI 暴露 + `trader brief` + astock replay** — 16 个 `trader tools` 命令 + 8 个 `astock replay` 命令全部可用，101 个测试通过
2. ⏳ **submit-buy/sell + ShadowBrain** — 从 PaperBroker 拆出直接执行路径，确定性 brain 跑通完整链路
3. ⏳ **Qoder 充当 brain 跑一轮真实看盘** — 端到端验证

Phase 5 完成后进入 Phase 6：接入 LLM API 实现全自动看盘循环。
