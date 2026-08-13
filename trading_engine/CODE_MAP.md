# trading_engine 代码地图

> 一句话:**用自然语言写交易策略,AI 自己看盘决策下单,引擎保证合规。**
> 这份地图只讲"每个模块干什么、数据怎么流、改东西改哪里",不讲实现细节。

---

## 一、整体架构:三层分离

```
┌─────────────────────────────────────────────────────────┐
│  策略层(可换 — 换策略不动引擎)                          │
│  strategies/expectation_driven/                         │
│    "怎么判断、怎么看盘、用什么工具"                      │
├─────────────────────────────────────────────────────────┤
│  引擎层(通用 — 所有策略共用,稳定不动)                 │
│  agent.py / watch.py                                    │
│    "跑 agent 循环、提供工具、强制市场规则"              │
├─────────────────────────────────────────────────────────┤
│  数据层(基础设施)                                      │
│  astock.py / live.py / replay.py / storage.py           │
│    "取行情、存状态、回放历史"                            │
└─────────────────────────────────────────────────────────┘
```

**核心理解**:引擎不认识"预期""池""心跳格式"——它只负责跑循环+提供工具+强制A股规则(T+1/整手/主板)。所有"怎么看盘、怎么判断"都在策略层。

---

## 二、文件清单(每个一句话)

### 策略层(1 个文件,你改策略主要动这里)
| 文件 | 干什么 |
|---|---|
| `strategies/expectation_driven/strategy.py` | **预期管理策略**:SYSTEM_PROMPT(判断规则)+ 注册策略工具(get_heartbeat/get_open_context/probe_pool) |

### 引擎层(4 个核心文件)
| 文件 | 干什么 |
|---|---|
| `agent.py` | **Agent 大脑**:用 PydanticAI 跑循环(每轮唤醒 AI → AI 调工具 → 决策),持续累积对话记忆 |
| `watch.py` | **看盘命令 + 渲染**:`watch open/heartbeat/probe/run` 命令;渲染心跳文本(指数/持仓/池/涨停) |
| `paper.py` | **模拟下单 + 规则校验**:T+1/整手/主板/14:50/风险预算/duplicate_signal——所有交易必须过这里 |
| `llm_provider.py` | **旧版判断**(无状态 API 模式):给 `analyze` 命令用,已被 agent.py 替代,保留兜底 |

### 数据层(取数 + 存状态)
| 文件 | 干什么 |
|---|---|
| `astock.py` | 调 astock 二进制的 Python 封装 |
| `live.py` | **实时数据**(TDX 直连):`live quote/index/market/block rank` |
| `replay.py` | **回放数据**(ClickHouse 历史):重建某天某时刻的行情快照 |
| `context.py` | **决策上下文构建**:把行情+持仓+预期+池+历史拼成完整 context |
| `storage.py` | **SQLite 存储层**:账户/持仓/预期/池/预案/判断/成交 全在这(最大文件,1600行) |

### CLI 入口 + 辅助
| 文件 | 干什么 |
|---|---|
| `cli.py` | 主命令入口(account/position/thesis/pool/plan/risk/replay/analyze/brief) |
| `context_cli.py` | `context` 命令组(capture/replay/show/evidence/reasoning/tool-call) |
| `paper_cli.py` | `paper` 命令组(execute/fills/orders/audit/history/report) |
| `models.py` / `context_models.py` / `paper_models.py` | Pydantic 数据模型定义 |
| `*_store.py` | 各存储层的 SQLite 操作 |
| `brief.py` | 开盘状态摘要(给 brain 启动用) |
| `config.py` / `dates.py` / `errors.py` | 配置/日期解析/异常 |

---

## 三、一次看盘的完整链路(端到端)

```
你运行: trader watch run --date 20260813 --live

  ① 开盘
     watch.py 解析命令 → agent.py run_watch_session()
     → 加载策略包(strategies/expectation_driven)
     → 建立对话:system_prompt = 预期管理规则(2021字)

  ② 每一轮(live 持续循环 / 回放按时间步进)
     runtime push "【新的一轮 11:30】" 给 AI
     ↓
     AI(DeepSeek)收到,自己决定调什么工具:
       ├─ get_heartbeat()  → 策略工具 → watch.py 渲染心跳文本
       │                      (取 live quote/index + 算池健康度)
       ├─ probe_pool("创新药") → 策略工具 → 看池成员明细
       ├─ probe_stock("000636") → 引擎工具 → 看个股分钟路径
       └─ trade("SELL","000636",200,"出口B") → 引擎工具 → paper.py 规则校验
     ↓
     AI 综合判断,输出结论文本
     ↓
     runtime 记录对话历史(message_history),推进下一轮

  ③ 收盘
     输出总结(现金/持仓/心跳轮数)
```

**关键:AI 自己决定调什么工具**。runtime 只负责:到点唤醒、提供工具、累积记忆、强制规则。

---

## 四、数据存哪里(所有状态都在一个 SQLite)

```
trader.db
  ├── 账户/持仓        ← account/position 命令操作
  ├── 预期(thesis)     ← thesis 命令,策略知识
  ├── 主题池(pool)     ← pool 命令,策略知识
  ├── 预案(plan)       ← plan 命令,策略知识
  ├── 风险因子(risk)   ← risk 命令
  ├── 决策上下文快照    ← context capture/replay 生成(审计用)
  ├── 判断(judgment)   ← analyze 生成(旧路径)
  └── 模拟交易          ← paper execute 生成(订单/成交/事件/规则校验)
```

---

## 五、当前能做什么 / 缺什么

### ✅ 能做(已验证)
- AI 自主看盘(live 实时 / 回放历史)
- AI 主动调工具(get_heartbeat/probe/trade)
- 预期管理判断(三维确认/双出口/分歧≠结束)
- 模拟交易 + 全部 A 股规则校验(T+1/整手/主板/14:50/风险预算)
- 策略可换(引擎/策略分离)

### ❌ 缺什么(碎片化的根源)
| 缺口 | 影响 |
|---|---|
| **看不到链路** | AI 怎么思考/决策散在日志,没有可视化 |
| **盘前/盘后没做** | 只有盘中,缺完整交易日闭环 |
| **持仓状态不同步** | heartbeat 显示的持仓 vs paper 账户实际持仓会不一致 |
| **token 管理** | 对话历史无限增长,跑到第20轮可能爆 context |
| **无盘前预案录入** | plan 命令有但没人用,AI 开盘看不到预案 |
| **live 模式粗糙** | 能跑但没收盘检测/异常恢复 |

---

## 六、"我想改 X,改哪里"

| 你想改 | 改这个文件 | 不动 |
|---|---|---|
| 预期管理的判断规则 | `strategies/.../strategy.py` 的 SYSTEM_PROMPT | 引擎 |
| 心跳看什么数据 | `strategies/.../strategy.py` 的 get_heartbeat | 引擎 |
| 加新策略(趋势/打板) | 新建 `strategies/trend_following/` | 引擎 |
| 加新工具给 AI 用 | `strategies/.../strategy.py` register_tools | 引擎 |
| 改 A 股规则(如单股≤20%) | `paper.py` 规则校验 | 策略 |
| 改心跳节奏(live间隔) | `agent.py` run_watch_session | 策略 |
| 加可视化(web/报告) | 新文件 | 现有逻辑 |
| 加盘前/盘后 | 新 `strategies/.../pre_market/` + runtime | 引擎 |

---

## 七、下一步建议(恢复掌控感)

**不要再碎片化地加功能**。选一条主线做到 100% 闭环:

**主线候选**(选一个):
1. **实时看盘闭环**:live 看盘 → AI 决策 → 交易 → **界面看回放**(补"看不到链路")
2. **完整交易日**:盘前分析 → 盘中 → 盘后复盘(补"全天闭环")
3. **策略验证**:同一天跑多个策略对比收益(补"策略可评估")

选好主线后,我**先写设计**(改哪几个文件、数据怎么流)给你确认,再动手。每一块做完 commit + 你能测试。
