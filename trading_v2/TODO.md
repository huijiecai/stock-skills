# Trading V2 — 构建清单

> 让 AI 像真正的投资者那样,基于**预期管理**看盘交易。
> 先完善工具(地基),再写 prompt(装修)。每做完一块打钩。

## 设计原则(最重要,先读)

1. **工具只提供"客观数据"和"执行动作"。所有判断(三维确认、出口A/B评估、归因、账户排序)都是 LLM 的脑力活,不写进工具。** —— 这是"预期管理"不是"规则引擎"的根本区别
2. **文件即数据库**:state.md(持仓/账户/预案)、pools.json(主题池)、expectations/*.md(预期)、lessons.md(教训)是真相源。账户数字必须来自 audit 精算,禁止 AI 手算
3. **原子工具**(查一类数据)按能力域分文件;**组合工具**(拼心跳/深析)在 watch.py,调原子
4. **astock 是唯一行情入口**;心跳/深析封装在组合工具里,不裸调 astock
5. **先通用工具,deps 后置**:工具 `RunContext[None]` + 参数(`get_indices(mode, date, time)`),任何 agent 能复用。deps(运行环境)是**交易系统阶段**才引入的应用层,现在不绑。live/replay 在通用场景由 AI 传 mode 参数,在交易系统场景由 deps 注入
6. 每块做完:能跑 + 你能读懂 + 打钩 + 更新 README。不提前写 prompt,不提前拆文件

## 目录结构(按能力域,8 个文件)

```
trader/
├── config.py        ← 配置出口(LLM_ 三件套,无默认值,缺失报错)
├── deps.py          ← 运行时状态:Deps(mode/at/account/can_trade),注入每个工具
├── agent.py         ← 大脑:建 Agent + 注册工具 + 组装 toolset
├── market.py        ← 行情原子:报价/指数/异动候选/板块/分钟 + 底层 _fetch(live/replay 统一)
├── account.py       ← 账户状态原子:持仓/账户/预案/预期追踪(读 state.md)
├── knowledge.py     ← 知识库原子:池成员/预期文件/教训(读 pools.json/expectations)
├── trading.py       ← 交易动作:execute(下单+规则校验)/ 留痕 / 信号账本
├── watch.py         ← 组合工具:open_context / heartbeat / probe_*(调原子)
└── main.py          ← 入口:建 Deps → 跑心跳循环 + message_history 记忆
```

**为什么需要 account.py 和 knowledge.py**:光有行情和交易工具,agent 不知道"自己持有什么、为什么买、池里是谁、历史上踩过什么坑"。预期管理要求 agent 有完整的自我认知和知识储备。

## 分层原则

```
原子工具(market/account/knowledge)  → 一个函数查一类数据,客观数据
   ↓ 通过
数据访问层(_fetch + Deps)           → live/replay 切换,看 deps.mode 调对应 astock 命令
   ↓ 调
astock live / replay / query
   ↓ 组合
组合工具(watch)                     → 拼成决策视图(open_context/heartbeat/probe)
   ↓ 组装
toolset(agent)                      → 看盘面 = 行情+账户+知识+组合;交易面 = trading;14:50 后 filtered
```

## 积木清单(按交易系统循环组织)

### 阶段一:通用工具(地基,不绑 deps)

- [x] **A0 底层取数**(`market.py`):纯函数,不绑 RunContext/Deps,任何场景复用 ✅
  - `_astock` / `_fetch_indices` / `_fetch_quotes` / `_fetch_kline` / `_fetch_block_rank` / `_fetch_block_members` / `_fmt_amount` / `_format_quotes`(全字段表格,三工具共用)
- [x] **A1 通用行情工具**(`market.py`):`RunContext[None]` + 参数,任何 agent 能用 ✅
  - [x] `get_indices` — 指数快照(live/replay,全字段表格)
  - [x] `get_quotes` — 个股/多股报价(live/replay,全字段)
  - [x] `get_kline` — 序列:个股/指数/板块 × 日线/分钟线(`ktype=auto` 自动判 type)
  - [x] `get_block_rank` — 板块涨幅排名(去现价/昨收,留涨跌/成交额/涨停/涨跌平/中位涨跌)
  - [x] `get_block_members` — 板块成分股(复用 `_format_quotes` 全字段)
  - [x] `get_candidates` — 全市场异动候选(live market 涨幅/成交额/涨速榜,新方向发现)
  - ~~`get_market_breadth`~~ — 砍掉:涨停数无直接接口、全市场扫描量大;异动看 `get_candidates` + 板块涨停数足够
- [ ] **A2 账户状态原子**(`account.py`):`get_positions`(持仓+买入预期+T+1可卖)/ `get_account`(现金+总资产+冷静期)
  - 读 `skills/trading-system/data/state.md`
- [ ] **A3 知识库原子**(`knowledge.py`):`get_pool`(池成员清单)/ `get_expectation`(预期文件)
  - 读 `data/research/pools.json` + `data/research/expectations/*.md`

### 阶段二:看盘循环(组合工具,调原子)

- [ ] **B1 开盘上下文**(`watch.py:get_open_context`):一次性加载 持仓+账户+池+预案+预期追踪
- [ ] **B2 心跳**(`watch.py:get_heartbeat`):指数 + 持仓报价(±2%触发标) + 池健康度X/Y + 异动候选 + 板块排名
  - 对应交易系统的 `op_scan_live.sh`,每轮首先调用,≤30行一眼扫完
- [ ] **B3 深析**(`watch.py:probe_pool` / `probe_stock` / `search_news`):池全量报价+龙头分钟路径+归因搜索
  - 信号触发才调,不是每轮

### 阶段三:决策执行(动作域)

- [ ] **C1 下单**(`trading.py:execute`):带规则校验 T+1 / 整手 / 主板(禁300/301/688)/ 14:50 / 冷静期 / 仓位上限
- [ ] **C2 留痕+信号**(`trading.py:record_decision` + `register_signal`):决策留痕(不留痕不许动账户)/ 信号账本防重复

### 阶段四:智能体化(把上面串成会跑的 agent)

- [ ] **D0 引入 Deps(交易系统化)**(`deps.py`):session 运行环境(mode/account/can_trade)。
  用 prepared 或薄包装把通用工具适配到 deps——AI 不再传 mode,从 deps 取(live/replay 固定、AI 改不了)
- [ ] **D1 循环+记忆**(`main.py`):心跳循环 + `message_history` 累积记忆 + Deps 注入
- [ ] **D2 prompt.md**(`prompts/`):交易规则,告诉 AI 什么时候用哪个工具 + 双出口/三维确认方法论
- [ ] **D3 toolset + filtered**(`agent.py`):看盘面 vs 交易面分离,14:50 后 `trading.filtered` 隐藏交易工具

## 构建顺序(MVP 优先,不是逐阶段)

不强求阶段一全做完才动阶段二。**先打通最小闭环**(能让 agent 看一眼盘+做一次决策):

1. **A0(数据访问层+Deps)→ A1(行情) + A2(账户) → B2(心跳) → C1(下单)**:agent 能看盘+交易,哪怕粗糙(且从第一天就 live/replay 双模)
2. A3(知识库) → B1(开盘上下文) → B3(深析):补全预期管理所需信息
3. C2(留痕) + D1(循环) + D2(prompt) + D3(toolset):智能体化

## 与交易系统循环的对应

| 交易系统循环 | 工具 |
|---|---|
| 盘前/开盘加载(state §一~四) | B1 `get_open_context` |
| 每轮心跳(op_scan_live.sh) | B2 `get_heartbeat` |
| 信号触发深析(三维确认) | B3 `probe_*` + `search_news` |
| §4.1 双出口评估 | AI 用脑(不写工具),数据靠 B2/B3 喂 |
| 决策执行(买卖规则) | C1 `execute` + C2 `record_decision` |
