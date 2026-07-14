# 交易引擎状态机设计 — LangGraph 架构方案

> 状态：草案 v0.2
> 目的：用状态机约束流程路由 + 护栏拦截硬性违规，AI 仍是交易决策者，从结构上防止"走错路"
> 背景：当前 SKILL 体系中，AI 反复理解错误规则（如已归档方向再异动应走 §3.3 而非 Mode A），根因是"该走哪条路靠 AI 读 md 自行判断"
> 定位：AI 是投资者（做分析和决策），代码是护栏（防走错路 + 防遗漏硬约束），不是量化系统

---

## 一、问题诊断

### 1.1 反复出错的模式

```
AI读规则md → 理解偏差 → 走错分支 → 事后发现 → 改md → 下次又理解错
```

典型案例（2026-07-14）：

| 事件 | 正确路径 | AI实际走的路径 | 根因 |
|------|---------|--------------|------|
| PCB午后整体异动 | §3.3 卖出后新信号→重新评估→三维齐→买入 | "PCB已归档→不在活跃预期→Mode A→盘中无法完成→盘后执行" | 深析流程只有两个分支（活跃/新方向），缺"已归档再异动"分支 |
| PCB板块整体走强 | 看到异动即开始评估（核心框架§4.1：信号=提醒注意） | 等到6涨停才触发Mode A门槛 | 把感知信号当机械门槛 |
| §3.3重新评估 | 盘中立即执行（§2.6：盘中感知≠追涨） | 推到"盘后执行" | §3.3缺少"盘中立即执行"强约束 |

### 1.2 根因分析

| 根因 | 表现 | 为什么改md解决不了 |
|------|------|-------------------|
| **流程分支靠AI选择** | AI读md后自行决定走Mode A还是§3.3 | 只要判断靠LLM理解，上下文一长就漂移 |
| **规则散落在6+个md文件** | 深析流程在公共规范.md，§3.3在买卖规则.md，信号定义在核心框架.md | AI需要跨文件索引+综合理解，每次都有偏差 |
| **规则是建议性的** | "应该走§3.3"但AI可以不走 | 没有程序性约束，规则不被强制执行 |
| **一个AI全做** | 快扫/深析/决策/执行/归档全在一个session | 上下文越来越长，对规则的理解越来越漂移 |

### 1.3 结论

改md文件 = 治标不治本。只要"该走哪条路"靠AI理解，就一定会再出错。需要从架构上把"走哪条路"变成代码判断。

---

## 二、方案选择

### 2.1 核心思路

**代码只做执行（读数据、写文件、跑脚本），AI做全部判断。AI是一个不休息的投资者。**

```
当前：  AI读md → 理解规则 → 选路 → 分析 → 决策 → （上下文太长→理解漂移→走错路）
改后：  代码拿数据 → AI看数据做判断 → AI决策 → 代码执行 → （每个节点上下文独立→不漂移）
```

代码只做执行：
1. **拿数据**：调用astock获取行情、读state.md获取持仓/预期状态
2. **写文件**：写trades.md、思考链路、heartbeat日志
3. **跑脚本**：运行audit_account.py

AI做全部判断：
- 看数据→有没有值得关注的信号？（不是"涨跌幅>2%=信号"，而是"这个异动对预期意味着什么"）
- 板块为什么强？龙头是谁？
- 三维确认齐了吗？买点类型是什么？
- 买不买？卖不卖？买什么？买多少？
- 一切基于预期——资金确认了就买，兑现了就卖

**没有机械阈值。没有"涨停>2就是强"。没有"涨跌幅>2%就触发信号"。** 投资者不做这种判断。

### 2.2 为什么需要LangGraph（如果判断全靠AI）

当前问题的根因不是"AI做了判断"，而是"一个AI session跑太久→上下文越来越长→对规则的理解越来越漂移"。

LangGraph的价值不是"替AI做判断"，而是：

| 价值 | 说明 |
|------|------|
| **上下文隔离** | 每个AI节点有独立、聚焦的上下文，不会因session太长而漂移 |
| **流程骨架** | 确保AI不会跳过步骤（如不写思考链路就交易） |
| **状态传递** | 节点间通过结构化状态传递，不丢失信息 |

每个AI节点收到的是：聚焦的prompt + 完整的规则引用 + 结构化的市场数据。AI在这个聚焦上下文中做判断，不会漂移。

### 2.3 方案对比

| 维度 | 现状(Qoder Skill) | LangGraph |
|------|-------------------|-----------|
| 判断主体 | AI | AI（不变） |
| 执行主体 | AI | 代码（解放AI注意力） |
| 上下文 | 一个session越跑越长→漂移 | 每节点独立→不漂移 |
| 流程 | 靠AI自觉走流程 | 状态机强制流程骨架 |
| 信号检测 | AI（但用机械阈值） | AI（基于预期判断，不用阈值） |
| 路由 | AI读md自行选路→走错 | AI在聚焦上下文中选路→不漂移 |

---

## 三、架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    LangGraph 状态机                       │
│                                                          │
│  ┌─────────┐     ┌──────────────────────────┐            │
│  │ 拿数据   │────→│  AI看盘 (全部判断)        │            │
│  │ (代码)   │     │                          │            │
│  │          │     │  · 有没有信号？           │            │
│  │ ·astock  │     │  · 走哪条路？             │            │
│  │ ·state.md│     │  · 为什么强？             │            │
│  │          │     │  · 三维确认？             │            │
│  └─────────┘     │  · 买不买？卖不卖？        │            │
│       ↑          └──────────┬───────────────┘            │
│       │                     │                            │
│       │          ┌──────────▼───────────────┐            │
│       │          │  执行 (代码)               │            │
│       │          │                           │            │
│       │          │  · 写思考链路              │            │
│       │          │  · 更新trades.md           │            │
│       │          │  · 运行audit               │            │
│       │          │  · 写heartbeat             │            │
│       │          └──────────┬───────────────┘            │
│       └─────────────────────┘                             │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                      外部依赖                             │
│  astock CLI (行情数据)  ·  state.md (状态源)  ·  LLM API  │
└──────────────────────────────────────────────────────────┘
```

**代码节点**（执行）：拿数据、写文件、跑脚本。不做任何判断。
**AI节点**（判断）：看数据→做全部交易判断。不碰文件写入。

状态机确保流程骨架（拿数据→判断→执行），AI在每个节点有独立上下文做判断。

### 3.2 状态机定义

```python
from langgraph.graph import StateGraph, END

# 状态定义：每个节点读写的共享状态
class TradingState(TypedDict):
    # 快扫产出
    scan_result: dict          # op_scan_live.sh 输出
    # 信号分类
    signal_type: str           # NONE / HOLDINGS_ALERT / SECTOR_SURGE / NEW_DIRECTION
    signal_detail: dict        # 信号详情（哪个板块/哪只持仓）
    # 方向状态
    direction_status: str      # ACTIVE / ARCHIVED_RESURGENT / NEW / UNKNOWN
    direction_name: str        # 方向名称
    # 深析产出
    analysis_result: dict      # AI深析结果
    # 规则检查
    rule_checks: dict          # 各项规则检查结果
    # 决策
    decision: str              # BUY / SELL / HOLD / RESEARCH / WAIT
    decision_reason: str       # 决策理由
    # 执行
    execution_result: dict     # 执行结果
    # 元数据
    round_num: int             # 轮次
    timestamp: str             # 当前时间
```

### 3.3 状态机流转图

```
                ┌──────────┐
                │  START   │
                └────┬─────┘
                     │
                ┌────▼─────┐
          ┌─────│ 拿数据    │◄───────────────────────────┐
          │     │ (代码)    │                            │
          │     └────┬─────┘                            │
          │          │                                  │
          │     ┌────▼─────────────────────┐            │
          │     │  AI看盘 (全部判断)        │            │
          │     │                          │            │
          │     │  看数据→有没有信号？       │            │
          │     │  ├─ 无信号 → 继续         │            │
          │     │  └─ 有信号 → 做什么？     │            │
          │     │      ├─ 持仓异动→评估卖出  │            │
          │     │      ├─ 活跃方向→评估买入  │            │
          │     │      ├─ 已归档→§3.3重评   │            │
          │     │      └─ 新方向→Mode A研究 │            │
          │     │                          │            │
          │     │  深析：归因/三维/买点/决策 │            │
          │     └────────┬─────────────────┘            │
          │              │                              │
          │     ┌────────▼─────────────────┐            │
          │     │  AI输出决策               │            │
          │     │  BUY/SELL/WAIT + 标的+仓位│            │
          │     └────────┬─────────────────┘            │
          │              │                              │
          │     ┌────────▼─────────────────┐            │
          │     │  执行 (代码)               │            │
          │     │  · 买入/卖出→写trades+audit│            │
          │     │  · 不操作→写heartbeat     │            │
          │     └────────┬─────────────────┘            │
          └──────────────┘                              │
              (返回拿数据)                               │
                                                    │
                ┌──────────┐                         │
                │   END    │◄────────────────────────┘
                └──────────┘  (收盘/Token耗尽)
```

### 3.4 路由：AI输出驱动，不是代码if-else

```python
def route_after_ai(state) -> str:
    """根据AI的输出决定下一步 — AI做判断，状态机只跟随"""
    ai_output = state["ai_output"]

    if ai_output["action"] == "WAIT":
        return "FETCH_DATA"        # AI说没信号 → 回拿数据
    elif ai_output["action"] == "BUY":
        return "EXECUTE_BUY"       # AI说买 → 执行买入
    elif ai_output["action"] == "SELL":
        return "EXECUTE_SELL"      # AI说卖 → 执行卖出
    elif ai_output["action"] == "RESEARCH":
        return "EXECUTE_RESEARCH"  # AI说需要研究 → 执行研究
    return "FETCH_DATA"
```

**关键变化**：路由不再由代码判断"信号类型""方向状态"——AI看完数据后直接输出"我要做什么"，状态机跟随执行。

状态机强制的是**流程骨架**（必须先拿数据→AI判断→执行），不是**判断内容**（走哪条路由AI决定）。

---

## 四、代码执行层

### 4.1 设计原则

**代码只做执行，不做任何判断。AI做全部判断，包括信号检测。**

| 代码做（执行） | AI做（全部判断） |
|--------------|----------------|
| 调用astock获取行情数据 | 看数据→有没有值得关注的信号？ |
| 读state.md获取持仓/预期状态 | 信号是什么类型？走哪条路？ |
| 写trades.md / 思考链路 / heartbeat | 板块为什么强？龙头是谁？ |
| 运行audit_account.py | 三维确认齐了吗？ |
| 格式化数据给AI看 | 买点类型？买不买？卖不卖？ |
| | 买什么？买多少？风险如何？ |

**没有机械阈值。代码不做"涨跌幅>2%=信号"这种判断。** 代码只负责把数据拿到、格式化好，交给AI看。AI像投资者一样看数据，基于预期做判断。

### 4.2 代码函数清单

代码只做两类函数：拿数据、写文件。

```python
# ========== 类型一：拿数据（给AI看） ==========

def fetch_market_data(holding_codes: list[str]) -> dict:
    """拿市场数据 — 执行op_scan_live.sh，格式化输出给AI"""
    result = subprocess.run(["bash", "op_scan_live.sh", *holding_codes], ...)
    return {
        "index": parse_index(result.stdout),          # 指数涨跌
        "holdings": parse_holdings(result.stdout),     # 持仓涨跌
        "sectors": parse_sectors(result.stdout),       # 板块排名
        "limit_ups": parse_limit_ups(result.stdout),   # 涨停方向
    }

def fetch_sector_members(sector_name: str) -> list[dict]:
    """拿板块成员 — astock live block members"""
    result = subprocess.run(["astock", "live", "block", "members", sector_name], ...)
    return parse_members(result.stdout)

def fetch_stock_quote(codes: list[str]) -> list[dict]:
    """拿多股报价 — astock live quote"""
    result = subprocess.run(["astock", "live", "quote", *codes], ...)
    return parse_quotes(result.stdout)

def fetch_stock_minute(code: str) -> dict:
    """拿个股分时 — astock live minute"""
    result = subprocess.run(["astock", "live", "minute", code], ...)
    return parse_minute(result.stdout)

def read_state() -> dict:
    """读state.md — 持仓+预期+预案"""
    return parse_state_md(read_file("state.md"))

# ========== 类型二：写文件（执行AI的决策） ==========

def write_heartbeat(round_num: int, timestamp: str, content: str):
    """写heartbeat日志"""
    append_to_file("看盘.md", f"| R{round_num} | {timestamp} | {content} |")

def write_thinking_chain(decision: dict):
    """写思考链路 — AI决策后必须先写再执行"""
    write_file(f"{timestamp}_{decision['action']}_{decision['target']}_思考链路.md",
               decision['analysis'])

def execute_trade(decision: dict):
    """执行交易 — 写trades.md + audit + 更新state.md"""
    # 1. 追加trades.md交易行
    append_trade(decision)
    # 2. 运行audit_account.py
    audit_result = subprocess.run(["python3", "audit_account.py"], ...)
    # 3. 用脚本输出更新state.md §二
    update_state_account(audit_result)
    # 4. 更新state.md §一持仓
    update_state_holdings(decision)
```

### 4.3 AI和代码的交互流程

```
代码拿数据 → AI看数据做全部判断 → AI输出决策
                                        │
                                        ▼
                              ┌──────────────────┐
                              │  代码执行          │
                              │  · 买/卖→写trades  │
                              │  · 不操作→写日志   │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │  代码拿数据        │ ← 下一轮
                              └──────────────────┘
```

**AI是投资者，代码是AI的手和眼睛。** AI看数据（眼睛）、做判断（大脑）、代码执行（手）。代码不做任何判断，AI不碰任何文件写入。

---

## 五、AI节点定义

### 5.1 节点清单

| 节点 | 类型 | 职责 |
|------|------|------|
| 拿数据 | 代码 | 调astock+读state.md→格式化给AI |
| AI看盘 | **AI** | 看数据→有没有信号？→走哪条路？→深析→决策 |
| 执行 | 代码 | 按AI决策写文件/跑脚本 |

### 5.2 AI看盘节点的完整职责

AI收到代码拿来的数据后，**自主完成全部交易判断**。像一个不休息的投资者一样看盘。

```python
# AI看盘节点 — 一个AI做全部判断，上下文聚焦不漂移
WATCH_PROMPT = """
你是一个投资者。你在看盘。以下是当前市场数据，请你做判断。

## 当前市场数据（代码已拿好）
- 指数：{index}
- 你的持仓：{holdings}
- 板块排名：{sectors}
- 涨停方向：{limit_ups}
- 当前时间：{timestamp}

## 你的持仓状态（从state.md读取）
- 持仓明细：{positions}
- 活跃预期：{active_expectations}
- 已归档预期：{archived_expectations}
- 待执行预案：{pending_plans}

## 交易规则（完整引用，不需要你跨文件查找）
{full_rules}

## 你需要做的（像一个投资者一样）
1. 看数据，有没有值得关注的？
   - 持仓有没有异动？需不需要评估卖出？
   - 有没有板块在走强？是哪个方向？
   - 涨停方向是什么？和你的预期有关系吗？
   
2. 如果有值得关注的，做什么？
   - 如果是持仓异动 → 评估§4.1卖出三步
   - 如果是活跃方向走强 → 评估买入（三维确认+买点+仓位）
   - 如果是已归档方向再异动 → §3.3重新评估（原预期是否有效？有新催化？）
   - 如果是新方向 → Mode A研究（行业分析+公司分析+创建预期文件）
   
3. 如果需要更多数据，告诉代码去拿什么
   - "需要看PCB板块成员"
   - "需要看沪电股份分时"
   - "需要看方向内多股报价"

4. 做决策
   - 买？卖？不操作？需要研究？
   - 买什么？买多少？为什么？
   - 卖什么？卖多少？为什么？

## 你的输出格式
{
  "signal": "有/无信号·信号是什么",
  "analysis": "你的完整分析过程",
  "need_more_data": ["需要代码拿的数据，如板块成员/分时等"],
  "decision": "BUY / SELL / WAIT / RESEARCH",
  "target": "标的代码（如有）",
  "position_pct": "仓位百分比（如买）",
  "reason": "决策理由"
}

如果需要更多数据，输出need_more_data，代码会去拿，然后你继续分析。
如果你做了BUY/SELL决策，代码会执行交易并写文件。
如果你输出WAIT，代码写heartbeat后进入下一轮。
"""
```

**关键**：
- AI看到的是**全部数据+完整规则**，在聚焦上下文中做判断
- AI自己决定"有没有信号""走哪条路""买不买"——代码不做任何判断
- 每轮AI交互都是独立上下文，不会因session太长而漂移
- 如果AI需要更多数据，可以要求代码去拿（多轮交互）

---

## 六、与现有系统的关系

### 6.1 系统边界

```
┌──────────────────────────────────────┐
│          LangGraph 交易引擎           │
│  (Python程序，独立运行)               │
│                                      │
│  状态机 + 规则引擎 + AI节点           │
└──────────┬───────────┬───────────────┘
           │           │
     ┌─────▼──┐   ┌───▼────────┐
     │ astock │   │ state.md   │
     │ CLI    │   │ trades.md  │
     │ (Go)   │   │ (文件)     │
     └────────┘   └────────────┘

┌──────────────────────────────────────┐
│          Qoder Skill                 │
│  (保留，用于非看盘任务)               │
│                                      │
│  · 盘前分析（八维催化扫描+预案）      │
│  · 盘后归档（逐股扫描+预期更新）      │
│  · 规则维护（修改md/Python规则）      │
│  · 人工干预（用户对话式操作）          │
└──────────────────────────────────────┘
```

### 6.2 看盘流程：模拟真实投资者

一个投资者看盘的自然行为：

```
1. 看大盘（指数涨跌）                           ← 代码拿数据
2. 看板块排名（哪些方向强）                      ← 代码拿数据
3. 看涨停方向（资金在往哪去）                    ← 代码拿数据
4. 看自己持仓（有没有异动）                      ← 代码拿数据
5. 有没有值得关注的？                            ← AI判断
   ├─ 没有 → 写heartbeat → 继续看（回步骤1）
   └─ 有 → 深入看
      6. 看板块成员（哪些个股领涨）               ← 代码按AI要求拿数据
      7. 看龙头走势（分时图）                     ← 代码按AI要求拿数据
      8. 看方向内多股对比                         ← 代码按AI要求拿数据
      9. 基于交易系统思考                         ← AI判断
         · 板块为什么强？归因到催化
         · 龙头是谁？预期内核心个股？
         · 三维确认齐了吗？
         · 买点类型？买不买？买什么？买多少？
         · 或者：持仓该不该卖？§4.1三步
      10. 决策                                    ← AI判断
         ├─ 买/卖 → 代码执行交易 → 继续看
         ├─ 不操作 → 写原因 → 继续看
         └─ 需要研究 → 代码执行Mode A → 继续看
```

**代码做的事**：步骤1-4拿数据、步骤6-8按AI要求拿更多数据、执行交易/写日志
**AI做的事**：步骤5判断有没有信号、步骤9思考、步骤10决策

### 6.3 职责迁移

| 看盘行为 | 当前(Qoder skill) | 改后(LangGraph) |
|---------|-------------------|-----------------|
| 拿数据（指数/板块/持仓/涨停） | AI调Bash命令 | **代码自动拿** |
| AI要更多数据（板块成员/分时） | AI调Bash命令 | **AI说"要什么"→代码去拿** |
| 看数据做判断（有没有信号） | AI（session太长→漂移） | **AI（每轮独立上下文→不漂移）** |
| 基于交易系统思考 | AI读md规则（漂移） | **AI（prompt含完整规则→不漂移）** |
| 买卖决策 | AI | **AI（不变）** |
| 执行交易 | AI写文件+调脚本 | **代码执行（AI不碰文件）** |
| 写heartbeat/思考链路 | AI写 | **代码按AI输出格式化写入** |
| 盘前分析 | Qoder skill | Qoder skill（不变） |
| 盘后归档 | Qoder skill | Qoder skill（不变） |

### 6.4 数据流

```
盘前分析(Qoder) → state.md → LangGraph读state.md → 看盘循环 → 写trades.md → state.md
                                                                      ↓
                                                              盘后归档(Qoder)读trades.md+state.md
```

- state.md 仍是唯一状态源
- trades.md 仍是交易账本
- astock CLI 仍是唯一行情数据入口
- LangGraph 通过 subprocess 调用 astock CLI（复用现有脚本）

---

## 七、项目结构

```
trading-engine/                    # 新建Python项目
├── pyproject.toml                 # 依赖：langgraph, langchain, openai
├── src/
│   ├── main.py                    # 入口：启动状态机
│   ├── graph.py                   # 状态机定义（节点+边+路由）
│   ├── state.py                   # TradingState定义
│   │
│   ├── nodes/                     # 节点实现
│   │   ├── scan.py                # 快扫节点（调用op_scan_live.sh）
│   │   ├── signal_classifier.py   # 信号分类（纯代码）
│   │   ├── direction_checker.py   # 方向状态检查（纯代码）
│   │   ├── buy_analyzer.py        # 买入深析（AI）
│   │   ├── reeval_3_3.py          # §3.3重新评估（AI）
│   │   ├── mode_a.py              # Mode A研究（AI）
│   │   ├── sell_analyzer.py       # 卖出深析（AI）
│   │   ├── decision_maker.py      # 决策节点（AI）
│   │   └── executor.py            # 执行节点（机械）
│   │
│   ├── rules/                     # 规则引擎（纯代码）
│   │   ├── signals.py             # 信号检测
│   │   ├── direction.py           # 方向状态分类
│   │   ├── confirmation.py        # 三维确认
│   │   ├── buy_point.py           # 买点类型
│   │   ├── sell_4_1.py            # §4.1卖出三步
│   │   ├── section_3_3.py         # §3.3重新评估条件
│   │   └── position.py            # 仓位约束
│   │
│   ├── tools/                     # astock CLI封装
│   │   ├── astock.py              # subprocess调用astock
│   │   ├── state_reader.py        # 读state.md
│   │   ├── state_writer.py        # 写state.md/trades.md
│   │   └── audit.py               # 调用audit_account.py
│   │
│   └── prompts/                   # AI节点prompt模板
│       ├── buy_analysis.py
│       ├── reeval_3_3.py
│       ├── sell_analysis.py
│       └── decision.py
│
└── tests/
    ├── test_rules.py              # 规则引擎单元测试
    ├── test_graph.py              # 状态机流转测试
    └── test_replay.py             # 历史数据回放测试
```

---

## 八、实施计划

### 阶段一：规则引擎 + 状态机骨架（核心）

**目标**：把"走哪条路"变成代码，解决反复理解错误问题

| # | 任务 | 产出 |
|---|------|------|
| 1 | 实现规则引擎 | rules/ 全部函数 + 单元测试 |
| 2 | 实现状态机骨架 | graph.py（节点+边+路由） |
| 3 | 实现非AI节点 | 快扫/信号分类/方向检查/执行 |
| 4 | 用7/14盘后数据回放测试 | 验证PCB午后异动→§3.3路径正确触发 |

**验收标准**：回放7/14数据，PCB午后异动时，`route_direction()` 返回 `"SECTION_3_3_REEVAL"` 而不是 `"MODE_A_RESEARCH"`。

### 阶段二：AI节点接入

**目标**：AI只做理解力任务，上下文隔离

| # | 任务 | 产出 |
|---|------|------|
| 5 | 接入LLM API | prompts/ + AI节点实现 |
| 6 | 实现买入深析/§3.3重评/卖出深析/决策节点 | nodes/ AI节点 |
| 7 | 端到端测试：实时看盘 | 接astock live，跑完整循环 |

### 阶段三：收尾

| # | 任务 | 产出 |
|---|------|------|
| 8 | 执行节点完整实现 | 写思考链路+trades.md+audit |
| 9 | 与Qoder skill集成 | state.md读写对齐 |
| 10 | 收盘归档checklist自动化 | 逐股扫描+预期更新 |

### 测试方案

```python
# test_replay.py — 用7/14历史数据回放
def test_pcb_afternoon_resurgent():
    """PCB午后异动应走§3.3，不是Mode A"""
    state = init_state("2026-07-14")
    state["signal_type"] = "SECTOR_SURGE"
    state["direction_name"] = "PCB"

    # 方向状态检查
    status = classify_direction("PCB", state["state_md"])
    assert status == "ARCHIVED_RESURGENT"  # 不是NEW！

    # 路由
    route = route_direction(state)
    assert route == "SECTION_3_3_REEVAL"  # 不是MODE_A_RESEARCH！
```

---

## 九、待讨论

1. **LLM选择**：AI节点用哪个模型？Qoder内置的？还是独立调用OpenAI/Claude API？
2. **运行方式**：LangGraph程序是常驻进程（盘中一直跑）还是由Qoder启动？
3. **state.md格式**：当前是Markdown，是否需要改为JSON/YAML以方便Python解析？
4. **规则引擎维护**：规则变了（如买点类型新增），改Python代码还是改md让代码读？
5. **与web项目的关系**：docs/2026-06-22-trading-web-design.md中的"AI运行状态"场，是否直接对接LangGraph？
6. **模拟看盘**：当前模拟看盘也在Qoder skill中，是否也迁移到LangGraph（切换数据源：live→query）？
7. **human-in-the-loop**：LangGraph支持中断等待人工确认，买入/卖出是否需要人工确认？（当前系统是AI全权自决）
8. **错误恢复**：astock命令失败/LLM API超时，状态机怎么处理？
