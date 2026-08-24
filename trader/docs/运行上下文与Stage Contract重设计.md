# 运行上下文与 Stage Contract 重设计

> 状态：已落地的设计基线
>
> 本文先回答一个边界问题：一个交易系统运行时，哪些内容由平台自动提供，哪些内容由用户在 System / Stage 中配置，哪些内容应该由 Prompt 作者负责。
>
> 本文不直接规定数据库表结构，先确定概念和职责边界。概念确定后，再据此重做 manifest、Stage Contract 和 Context Assembly。

## 1. 为什么现在要重新设计

当前的 Stage Contract 主要解决“阶段之间如何传递文档”：

```json
{
  "inputs": {
    "opening_plan": {
      "from": "premarket.plan",
      "selector": "latest"
    }
  },
  "outputs": {
    "decision": {
      "kind": "document",
      "doc_type": "watch_live"
    }
  }
}
```

它可以表达：

```text
live 启动前读取 premarket.plan
live 结束后保存一篇 watch_live 文档
```

但它还不能完整表达一个阶段的运行要求：

- 哪些输入是必需的，缺失时是否允许继续；
- 阶段以单次还是循环方式执行；
- 阶段可以产生哪些阶段产物；
- 运行过程中哪些输入、工具返回和输出需要冻结留证。

因此，当前的 Stage Contract 更像“文档衔接配置”，还不是完整的“运行契约”。

## 2. 设计目标

目标是让一个 Stage 的运行边界清晰、可校验、可复现：

```text
这个阶段需要什么输入？
这些输入由谁提供？
这些输入在什么时间点有效？
阶段可以主动做什么？
阶段必须产生什么结果？
平台如何记录这次运行？
```

同时保持一个重要原则：

> Prompt 描述交易方法，平台负责运行协议。

## 3. 四类职责

### 3.1 平台自动提供的运行 Context

这部分由引擎负责生成，Prompt 作者不需要每次声明，也不应该通过 Prompt 自己拼接。

典型内容包括（模型只看到其中的业务运行部分）：

```text
实时还是回放
交易日期和当前时钟
当前轮次
当前运行模式和数据边界

用户身份、组合身份和 Run ID 只保存在运行证据，不注入 Prompt。
```

平台 Context 的特点：

1. 平台能够确定生成；
2. 每次运行都应遵循统一格式；
3. 所有时间敏感数据必须绑定运行时钟；
4. 内容应写入运行证据，支持事后复现；
5. Prompt 不负责查询、命名或拼装底层存储对象。

例如 replay 在 `10:35` 运行时，平台生成的行情快照不能包含 `10:35` 之后的数据。

### 3.2 用户在 System / Stage 创建时配置的声明

这部分描述“系统如何运行”，属于结构化配置，不是具体交易方法。

System 层可以配置：

```text
系统名称
系统级 Prompt
系统有哪些 Stage
联网、自选组写入、模拟交易、实盘交易等高风险策略
```

Stage 层可以配置：

```text
Stage 使用哪个 Prompt
Stage 是 single 还是 loop
运行时间窗和轮间隔
需要哪些上游阶段产物
每个输入是否必需
可以产生哪些输出
请求预算和停止策略
```

示意：

```json
{
  "id": "live",
  "prompt": "market_observer",
  "inputs": [
    {"id": "opening_plan", "kind": "artifact", "required": false}
  ],
  "outputs": [
    {"id": "decision", "kind": "artifact", "required": true},
    {"id": "trade", "kind": "action", "required": false}
  ],
  "execution": {
    "mode": "loop",
    "interval": 5,
    "window": "09:35-15:05"
  }
}
```

### 3.3 用户发起 Run 时提供的本次任务

这部分描述“这一次具体要解决什么”，生命周期只属于一次 Run：

```text
分析沪电股份（002463）今天走势的原因
分析 PCB 板块未来一周强弱
复核某个候选股是否满足系统的买入规则
```

它既不是 Stage 声明，也不是 Prompt 方法论。Stage 可以反复运行，Prompt 可以长期复用，
而每次运行的分析对象可以完全不同。平台在启动时接收该文本，将其冻结到 Run，并在每轮调用
LLM 时以独立的“本次运行请求”段落注入，避免模型从持仓、自选组或历史内容中猜目标。

### 3.4 Prompt 作者负责的内容

Prompt 是交易方法本身，负责描述如何思考和决策：

```text
哪些信号重要
如何判断催化是否兑现
什么情况下买入
什么情况下卖出
如何处理冲突信息
如何表达不确定性
如何解释决策依据
```

Prompt 不应该负责以下平台协议：

```text
去哪里找文档
doc_type 叫什么
文档存什么名字
当前第几轮
如何拼接日期
如何关联 run_id
如何调用底层 save_doc / save_watchlist
```

Prompt 可以提出业务要求，例如“需要关注持仓的失效标志”，但不应负责通过底层存储 API 找到持仓或保存结果。

## 4. 不能混淆的运行时业务资源

除上述四类职责外，实现层还需要单独识别“运行时业务资源”。

典型资源包括：

```text
自选组
预期库
黑名单
基准组合
风险参数
当前持仓
行情快照
历史轮日志
```

它们既不是平台固定常量，也不是 Stage 定义本身，更不是 Prompt 代码。

更准确的处理方式是：

```text
Prompt 描述需要关注的资源
→ 模型调用领域工具
→ 工具在当前运行时钟和组合上下文中返回
→ 平台记录工具调用和返回证据
```

例如：

```text
Prompt：说明需要关注某个自选组
模型：调用 `get_watchlist` 或 `get_watchlist_quotes`
平台运行时：以当前运行时钟和组合上下文执行工具
LLM 看到：工具返回的具体股票和业务标注
```

这里需要区分：

| 对象 | 说明 |
|---|---|
| Resource | 跨运行存活、有业务身份的对象，例如自选组、黑名单 |
| Observation | 工具在某个时钟点返回的客观投影，例如成员行情、持仓快照 |
| Artifact | 某次运行产生的内容，例如计划、判断、复盘报告 |
| Setting | 系统实例的配置，例如最大仓位、关注市场 |

对用户可以把它们统称为“平台自动带上的运行数据”，但平台内部不能把它们和固定运行元数据混为一谈。

## 5. LLM 最终看到的 Context 结构

每次调用 LLM 时，平台统一组装以下内容：

```text
[平台运行信封]
日期、时钟、轮次、运行模式

[本次运行请求]
用户启动这次 Run 时填写的具体任务或分析对象

[声明输入]
上游阶段产物

[用户 Prompt]
交易方法、判断逻辑、决策规则
```

最终的 Context 可以由以下公式表达：

```text
LLM Context = Runtime Envelope + Run Input + Resolved Artifacts + User Prompt + 按需工具返回
```

这些内容的来源不同，但最终都应在 transcript 中留下清晰边界，避免事后无法判断某段信息是平台注入、单次请求、用户配置还是 Prompt 内容。

## 6. 新 Stage Contract 应该描述什么

Stage Contract 只描述用户需要决定的运行边界：

```text
Inputs       这个 Stage 需要什么输入
Resolution   每个输入从哪里来、何时解析、是否必需
Outputs      这个 Stage 可以或必须产生什么
Execution    这个 Stage 如何被调度
Evidence     由平台统一记录，不需用户配置
Failure      由平台统一重试和封场
```

示意结构：

```json
{
  "id": "live",
  "inputs": [
    {
      "id": "opening_plan",
      "kind": "artifact",
      "source": {"stage": "premarket", "output": "plan"},
      "selector": "latest",
      "required": false
    },
  ],
  "outputs": [
    {
      "id": "decision",
      "kind": "artifact",
      "required": true
    },
    {
      "id": "trade",
      "kind": "action",
      "required": false
    }
  ],
  "execution": {
    "mode": "loop",
    "interval": 5,
    "window": "09:35-15:05"
  }
}
```

## 7. 一次运行的责任边界

有了新的契约后，一次 Stage 运行应由平台完成以下步骤：

```text
1. 读取并冻结系统、Stage、Prompt 版本和本次 Run Input
2. 解析 Stage 声明的输入
3. 生成运行信封，并绑定工具使用的时钟和组合
4. 校验必需输入是否齐全
5. 按系统策略开放领域能力
6. 调用 LLM 执行 Prompt
7. 记录实际读取的输入版本
8. 记录实际调用过的工具及返回值
9. 校验并发布声明的输出
10. 记录交易动作和运行结果
```

Prompt 的职责则收敛为：

```text
理解输入
执行分析方法
根据规则决策
通过业务语义描述输出
```

## 8. 一个实际对比

### 当前模式

```text
Prompt 自己调用 get_positions()
Prompt 自己调用 list_docs()
Prompt 自己猜测要读哪份盘前计划
Prompt 自己调用 save_doc(doc_type="watch_live")
```

问题是：

- Prompt 可能忘记读某项关键数据；
- 不同系统必须模仿 expectation 的命名约定；
- 运行前无法校验输入是否齐全；
- 事后只能推测 LLM 当时实际看到了什么。

### 目标模式

```text
平台提前解析盘前计划
平台注入本次运行请求
模型按 Prompt 需要读取持仓和行情
平台按 System Policy 和运行模式限制工具权限
LLM 只负责分析和决策
平台接收 decision / trade 等结构化输出
平台统一保存和留证
```

这样，如果 `portfolio_snapshot` 是必需输入，平台就必须保证：

- 模型一定收到持仓快照；
- 快照对应明确的运行时钟；
- 快照内容被保存进本次 Run 的证据；
- 无法生成时，阶段明确失败或进入预定义的缺失处理流程。

## 9. 设计原则

### 9.1 Prompt 不直接依赖存储协议

Prompt 面向业务语义：

```text
读取盘前计划
发布本轮判断
更新候选集合
```

平台负责把这些语义映射到文档、资源、快照和版本表。

### 9.2 输入和能力必须分开

```text
Input：平台保证在调用 Prompt 前已经提供
Capability：模型可以选择调用，也可能不调用
```

上游计划等必须稳定提供的阶段产物适合作为 Input。持仓、市场基线、分钟 K 线、公告搜索、
个股深析等运行时业务数据由 Prompt 按需调用 Capability，Stage 不配置具体行情对象。

### 9.3 配置和状态必须分开

```text
Stage 配置：需要一个 focus_set
用户状态：focus_set 当前绑定到哪个自选组
运行快照：本次运行时该自选组有哪些成员
```

不能把这三件事都塞进 manifest，也不能让 Prompt 自己解析。

### 9.4 所有时间敏感输入都必须绑定 Run Clock

尤其是 replay：

```text
历史日期 + 当前回放时钟
```

不是只传一个 `date` 就足够。行情、持仓估值、板块排名、工具返回都必须遵守这个时钟。

### 9.5 契约先声明，实际使用再留证

Stage Contract 描述“允许和要求什么”；Run Evidence 记录“实际上发生了什么”。

两者不能混为一谈：

```text
声明可以调用 kline.read
不代表本轮真的调用过 kline.read
```

## 10. 对现有代码的影响

这不是在现有 `stageio.py` 上简单增加几个字段，而是需要先重新确定模型：

```text
现有 stageio
  主要负责文档输入选择和文档输出保存

目标 Context Assembly
  负责平台信封、资源解析、观察快照、能力边界和输出留证
```

后续可能需要重新拆分的职责包括：

- `stageio.py`：从文档 I/O 扩展为契约校验和输入输出解析；
- `context.py`：从进程级上下文扩展为 Run Context / Stage Context；
- `engine.py`：负责按契约组装 Context 和能力边界；
- `registry.py`：工具注册信息增加能力分类和权限元数据；
- `runs.py`：冻结实际输入、输出和运行时观察；
- `documents.py / watchlist.py / ledger.py`：提供统一的资源和快照解析接口。

在模型没有定稿前，不建议继续向 Stage Contract 里堆叠更多 `doc_type`、`watchlist` 或 Prompt 专用字段。

## 11. 待拍板问题

以下问题需要在进入实现前明确：

1. 哪些内容属于所有 Stage 必须自动注入的 Runtime Envelope？
2. 持仓、市场基线、自选组快照分别属于必需 Input 还是可选 Capability？
3. Resource 的绑定放在 System、System Instance 还是 Portfolio？
4. 输出是只允许结构化发布，还是继续兼容 Prompt 自己调用保存工具？
5. required 输入缺失时，阶段是阻止运行、等待上游，还是允许用户临时豁免？
6. 工具返回是否全部保存，还是只保存摘要和哈希？
7. 交易动作是否作为 Stage Output，还是作为独立的 Action Capability？
8. 实盘、模拟盘、回放是否使用同一套 Context 结构，只更换 Clock 和执行能力？

## 12. 建议的下一步

先不要立刻改代码，按以下顺序定稿：

```text
1. 列出 Runtime Envelope 的固定字段
2. 列出 Stage 可声明的 Input / Capability / Output 类型
3. 明确 Resource、Observation、Artifact、Setting 的边界
4. 选 expectation 的 live 阶段写一份目标契约
5. 选一个全新的玩具系统验证“只靠 Prompt + manifest”
6. 再根据目标契约重做代码模型和迁移方案
```

最终希望收敛成：

```text
Prompt       = 方法论：怎么判断
Stage        = 声明：需要什么、能做什么、产出什么
Run Input    = 请求：这一次具体分析谁、解决什么
Engine       = 组装：把输入和能力交给 LLM
Run          = 证据：冻结实际发生了什么
```

Run 完成后的“继续讨论”仍属于该证据边界：平台恢复冻结 Prompt 和原始 transcript，让原 Stage
Agent 澄清结论，但不修改原 Run。面向 Prompt 优化的教练对话属于 System 级元分析，应使用独立
Coach 人格和显式 Run 引用，不能与 Stage 续聊共用角色。
