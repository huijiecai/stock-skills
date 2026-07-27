# Trading Engine 分阶段实施路线

> 状态：Phase 3 进行中
> 创建日期：2026-07-24
> 路线调整：2026-07-27切换为真实看盘优先；历史回放保留为确定性测试基座。
> 目标：以实时影子看盘为主线构建可观察、可恢复的独立交易引擎，并用历史回放做回归验证。
> 相关设计：`docs/2026-07-14-langgraph-trading-engine-design.md`

## 一、总体原则

1. 真实看盘是产品主线；历史回放是开发和回归测试基座。
2. 每个 Phase 都必须能够独立运行、测试和验收。
3. `trading_engine` 只能通过 `astock` CLI 获取行情，不直接访问 ClickHouse 或 TDX。
4. AI 负责市场理解、预期归因和交易判断；代码负责数据边界、状态、硬约束、执行和持久化。
5. 模拟回放在任意时点只能使用该时点之前可获得的数据，禁止未来数据泄漏。
6. 先实现普通 Python 节点；节点边界稳定后再引入 LangGraph 编排。
7. SQLite 保存少量运行状态、账户、订单和决策事件；Markdown 作为面向人的报告。
8. AI判断先在实时影子模式运行，不修改账户；同一节点必须能够使用历史回放数据测试。
9. `trading_engine`是完全独立的新Agent；不读取、不写入、也不要求存在原`trading-system` Skill。旧Skill只作为设计阶段的规则参考。

## 二、目标目录

```text
stock/
├── astock/
└── trading_engine/
    ├── pyproject.toml
    ├── src/trading_engine/
    ├── tests/
    └── data/                 # 本地运行数据，不提交 Git
```

`trading_engine`自行负责规则、上下文、状态和执行。运行时业务依赖只包括`astock`行情接口和自己的SQLite数据库。

## 三、阶段总览

| Phase | 名称 | 核心结果 | 状态 |
|------|------|---------|------|
| 0 | 工程骨架 | 可安装、可测试的 `trader` CLI | 已完成 |
| 1 | 可控历史回放 | 按模拟时钟读取历史数据并断点恢复 | 已完成 |
| 2 | 实时影子数据 | 获取、校验、展示并保存真实持仓快照 | 已完成 |
| 3 | 只读 AI 判断 | 基于真实快照产生结构化提案，不修改账户 | 进行中 |
| 4 | 模拟交易闭环 | 风险校验、模拟成交、账户和报告闭环 | 未开始 |
| 5 | 完整研究工作流 | 归因、预期研究、三维确认和账户级排序 | 未开始 |
| 6 | 虚拟账户实时执行 | 实时更新虚拟账户，仍不连接真实券商 | 未开始 |

状态只使用：`未开始`、`进行中`、`已完成`、`阻塞`。

## 四、Phase 0：工程骨架

### 范围

- 创建独立的 `trading_engine` Python 项目。
- 使用 Typer 提供 `trader` CLI。
- 使用 Pydantic 定义配置和基础数据模型。
- 封装 `astock` 命令调用和 JSON 解析。
- 建立日志、异常类型、配置加载和 pytest 测试结构。
- 定义 `MarketDataProvider`、`TradingClock`、`ExecutionBroker` 接口。

### 交付物

- `trading_engine/pyproject.toml`
- `trader --help`
- `trader config show`
- `trader astock check`
- 基础接口和单元测试

### 验收条件

- 在仓库根目录能够执行 `trader --help`。
- `trader astock check` 能调用现有 astock 并报告可用性。
- 测试不依赖开盘时间和外部 LLM。
- `trading_engine` 不直接访问 ClickHouse。

### 本阶段不做

- 不引入 LangGraph。
- 不调用 LLM。
- 不实现交易和账户更新。
- 不接入实时行情循环。

### 验收记录

完成日期：2026-07-24

```bash
./trader --version
./trader --help
./trader config show
./trader astock check
uv run --project trading_engine pytest trading_engine/tests
```

验收结果：`trader 0.1.0` 可从仓库根目录启动；配置和 astock 二进制检查通过；6 个测试全部通过。

## 五、Phase 1：可控历史回放

### 范围

- 实现 `ReplayClock` 和 `ReplayMarketData`。
- 按交易日和分钟推进模拟时钟。
- 所有行情查询带有明确的截止时间。
- 使用 SQLite 保存 run 和 checkpoint。
- 支持启动、运行到指定时间、暂停和恢复。
- 复用现有 `replay_minute_signals.py` 中可验证的逻辑，但不直接耦合其输出格式。

### 交付物

```bash
trader replay --date 20260723 --code 603127 --until 10:30
trader replay resume
trader status
```

### 验收条件

- 同一日期和参数重复运行产生一致结果。
- 回放至 `10:30` 时无法访问 `10:30` 之后的数据。
- 中断后可从最近 checkpoint 恢复。
- 恢复不会重复处理已完成时间片。
- 无需等待真实开盘即可完成全部测试。

### 本阶段不做

- 不调用 LLM。
- 不判断买卖。
- 不维护虚拟账户。
- 不搜索实时网页新闻。

### 数据契约与验收记录

完成日期：2026-07-24

- 测试标的：昭衍新药 `603127`
- 测试日期：2026-07-23
- astock返回240根分钟K线。
- 分钟时间为K线结束时刻：`09:31-11:30`、`13:01-15:00`。
- `09:30`是回放初始化时刻，不对应分钟K线；第一步推进到`09:31`。
- 日K提供回放计算所需的`pre_close`。
- Phase 1 查询始终携带`--no-sync`，缺失数据直接失败，不在回放中修改行情仓库。

验收流程：

```bash
./trader replay --date 20260723 --code 603127 --until 10:30
./trader status
./trader replay resume --until 10:31
./trader replay resume --until 15:00
```

验收结果：

- `10:30` checkpoint只包含前60根K线。
- 恢复到`10:31`后包含61根K线，没有重复处理`10:30`。
- 收盘状态为`completed`，包含240根K线。
- 全日共241个唯一checkpoint：1个初始化checkpoint和240个分钟checkpoint。
- SQLite事务同时写入checkpoint并更新run进度，重复时间会被唯一约束拒绝。
- 12个`trading_engine`测试全部通过。

## 六、Phase 2：实时影子数据

### 范围

- 实现 `LiveMarketData`，通过当前 `astock/astock` 获取批量股票实时报价。
- 强制校验请求代码与返回代码集合一致、代码不重复、价格和昨收大于零。
- 重新计算涨跌幅并与astock输出交叉验证。
- 将实时影子快照存入SQLite，并提供可读表格和JSON输出。
- 保持只读影子模式，不修改账户、持仓或交易记录。
- 保留 `ReplayMarketData` 作为同一市场快照接口的测试实现。

### 交付物

```bash
./trader watch --code 603127 --code 000021 --code 002281
./trader watch latest
./trader watch latest --json
```

### 验收条件

- 错位、缺失、重复或零价格报价必须拒绝，不得进入后续AI节点。
- 快照必须包含抓取时间、数据源、代码、现价、昨收、涨跌幅、成交量和成交额。
- `watch latest` 能从SQLite恢复最后一次快照。
- 输出明确标记“只读影子，不执行交易”。

### 本阶段不做

- 不调用LLM。
- 不连续轮询。
- 不做买卖判断。
- 不读取或修改虚拟账户。

### 数据契约与验收记录

完成日期：2026-07-27

- 默认astock路径由旧的`astock/build/astock`修正为当前`astock/astock`；旧二进制不自动回退，缺失时直接失败。
- 旧二进制实测会将`000021`错误解析为指数价格，并将`000636`错配为`600839`零报价；新二进制修复后数据与午盘账户快照一致。
- 11:59对五只实际持仓完成实时影子快照：`603127`、`000021`、`002281`、`601606`、`000636`。
- 快照成功写入SQLite并由`watch latest`完整恢复。
- 18个`trading_engine`测试全部通过。

## 七、Phase 3：只读 AI 判断

### Phase 3A进度：结构化只读判断节点

完成日期：2026-07-27

- 新增标准`JudgmentContext`、`JudgmentProposal`、`JudgmentReport`和`JudgmentRecord`模型。
- 新增`trader analyze latest`，消费最近真实快照并生成逐股结构化提案。
- 新增`trader analyze show`，只读取最近一次判断，不重复运行判断节点。
- 默认使用确定性的`shadow-rules/conservative-v1`保守节点：大幅波动输出`RESEARCH`，其余输出`WAIT`，不会仅凭价格输出`BUY/SELL`。
- SQLite完整保存输入快照、输出、provider、model、尝试次数、失败原因和时间。
- 严格校验输出的快照ID、时间、provider/model和股票集合；缺码、重复码或元数据错配均记录为失败。
- 判断节点失败可重试，最终失败不会修改或删除原始实时快照，CLI以非零状态退出。
- 已使用五只实际持仓的13:42真实快照完成端到端分析和审计记录恢复。
- 24个`trading_engine`测试和4个旧回放信号测试全部通过。

### Phase 3B-1进度：独立账户与持仓

完成日期：2026-07-27

- SQLite新增`accounts`和`positions`表，完全由新Agent独立维护。
- 金额统一以整数分保存，CLI使用字符串转`Decimal`，禁止浮点金额和超过两位小数的输入。
- 持仓显式保存总数量、可卖数量、平均成本和最近变动日期；可卖数量不得超过总数量。
- 新增`trader account init/show/update`和`trader position set/list`命令。
- 账户和持仓均不从旧Skill自动导入；初始化必须通过新CLI明确完成。
- 仓库根目录发现由`astock + trading_engine`确定，不再要求存在`skills/`目录。
- 29个`trading_engine`测试和4个旧回放信号测试全部通过。

### Phase 3B-2进度：独立研究状态

完成日期：2026-07-27

- SQLite新增`theses`、`watch_pools`、`watch_pool_members`和`risk_factors`表。
- 新增持仓与预期、持仓与风险因子的多对多关联表；关联目标不存在时严格失败。
- 预期使用稳定ASCII key和明确状态，保存摘要、兑现条件与失效条件。
- 固定池成员区分`direct`和`research`；`research`成员由模型和SQLite双重约束为不可交易。
- 风险上限以基点保存，限制在0%至100%且最多两位小数。
- 新增`trader thesis set/list/link`、`trader pool set/member/show`和`trader risk set/list/link`命令。
- 所有研究状态均由新Agent独立创建，不导入或引用旧Skill文件。
- 32个`trading_engine`测试和4个旧回放信号测试全部通过。

Phase 3尚未完成。剩余工作：

- 在自身SQLite中建立带来源和观察时间的催化证据。
- 将独立账户、研究状态和行情组合成带时间边界的上下文快照。
- 将同一判断节点接到Phase 1历史快照，完成无未来数据的回归验证。
- 最后接入单个外部LLM provider，并使用同一Pydantic输出契约。

### 范围

- 定义标准AI输入上下文，先消费Phase 2的真实持仓快照。
- 接入单个LLM判断节点。
- AI输出`WAIT`、`RESEARCH`、`BUY`、`SELL`等结构化提案。
- 使用Pydantic严格校验提案。
- 保存AI输入、输出、模型信息、失败和重试记录。
- 使用Phase 1历史快照对同一节点做确定性回归测试。

### 验收条件

- AI输出无法通过校验时不会触发任何交易动作。
- 同一轮输入和输出可以被完整审计。
- 模型调用失败可以重试或跳过，不破坏实时快照和回放进度。
- 输出直接展示每只持仓的判断和需要补充的证据。

### 本阶段不做

- 不执行模拟或真实交易。
- 不允许AI直接修改Markdown、SQLite账户表或交易记录。
- 不拆分多个Agent。

## 八、Phase 4：模拟交易闭环

### 范围

- 实现Paper Broker。
- 将账户、持仓、订单、成交和决策事件存入SQLite。
- 实现主板范围、现金、仓位、T+1、重复信号等确定性校验。
- AI只提交交易提案，代码校验通过后才能执行。
- 实现幂等性，防止恢复后重复成交。
- 从结构化数据生成`state.md`、`trades.md`和每日影子报告。

### 验收条件

- 完成“行情 -> 提案 -> 校验 -> 模拟成交 -> 账户更新 -> 报告”闭环。
- 任何成交均可追溯到行情快照、AI提案和规则校验结果。
- 程序在成交前后中断均不会产生重复订单或半写入账户。
- 账户现金、持仓和成交记录能够通过独立审计。

### 本阶段不做

- 不连接真实券商。
- 不修改当前人工维护的真实看盘账户。
- 不追求覆盖全部预期研究流程。

## 九、Phase 5：完整研究工作流

### 范围

- 迁移异动归因、直接受益池、龙头识别和三维确认。
- 迁移预期研究Mode A和Mode B。
- 迁移账户级机会排序和买卖规则。
- 为历史新闻和催化建立带时间戳的证据接口或固定测试数据。
- 在普通Python节点稳定后接入LangGraph。
- 使用checkpoint支持节点级恢复、重试和人工中断。

### 验收条件

- 关键路径均有结构化输入输出和独立测试。
- 已归档、活跃和新方向的路由由结构化状态约束。
- AI不能跳过硬性校验节点直接成交。
- 回放不使用事后新闻、收盘数据或未来预期文件内容。
- 实时模式不补写中断期间的观察和判断。

## 十、Phase 6：虚拟账户实时执行

### 范围

- 增加连续轮询、真实交易时钟和收盘退出。
- 允许经过校验的实时提案更新独立虚拟账户。
- 保留停止开关、人工中断和完整审计链路。
- 每日收盘自动生成账户、交易和复盘报告。

### 验收条件

- 实时账户更新具备幂等性和事务性。
- 任意交易均可回放当时的输入、判断、校验和成交过程。
- 连续运行稳定后再评估是否需要真实券商接口。

### 本阶段不做

- 默认不连接真实券商。
- 不在缺少额外权限、安全设计和人工确认的情况下扩展到实盘。

## 十一、数据职责

| 数据 | 唯一入口或存储 | 说明 |
|------|---------------|------|
| 行情 | astock CLI | `trading_engine` 不感知 ClickHouse 或 TDX |
| Agent运行状态 | SQLite | run、checkpoint、错误和恢复位置 |
| 实时影子快照 | SQLite | 经过代码、价格和涨跌幅校验的只读行情 |
| 独立账户 | SQLite（Phase 3B起） | 现金、持仓和上下文基础状态 |
| 订单和成交 | SQLite（Phase 4起） | 经过规则校验的模拟执行记录 |
| 决策审计 | SQLite | 输入摘要、AI提案、规则校验和执行结果 |
| 研究知识 | SQLite（Phase 3B起） | 独立维护预期、固定池、催化和风险因子 |
| 人类可读报告 | Markdown | 从结构化状态生成或引用结构化记录 |
| 密钥和凭证 | 环境变量或系统密钥存储 | 禁止写入 SQLite 和 Git |

## 十二、当前下一步

Phase 0、Phase 1和Phase 2已完成，Phase 3A、Phase 3B-1和Phase 3B-2已完成。下一步继续Phase 3B-3，建立催化证据和带时间边界的综合上下文快照，不提前接入LLM或实现Phase 4。

Phase 3完成并验收后，在本文中将其状态改为`已完成`，记录验收命令和结果，再开始Phase 4。
