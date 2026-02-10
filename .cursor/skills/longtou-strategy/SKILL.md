---
name: /longtou-strategy
id: longtou-strategy
category: stockTrading
description: 龙头战法超短线选股助手。基于"预期管理"理论，筛选符合龙头战法的A股股票。支持早盘筛选、逻辑分析、市场状态判断等功能。当用户需要选股、分析个股、或询问龙头战法相关问题时使用此 skill。
---

# 龙头战法选股助手

A股龙头超短战法智能选股工具，帮助识别高确定性的交易机会。

---

## 🎯 核心理念

**预期管理四步法**：建立预期 → 确认预期（买入） → 兑现预期（卖出） → 复盘

**只做情绪拐点，强势板块的领涨个股**：
- 冰点修复（情绪冰点后的修复机会）
- 龙头弱转强（主线延续）
- 补涨分离（主线以补涨延续）

> 💡 **详细战法规则**：参考 `reference/strategy-rules.md`

---

## 📋 使用方式

### 1. 早盘筛选今日自选股

**命令**：`/longtou-strategy 筛选今日自选股` 或 `/longtou-strategy 看情绪`

**功能**：
- 自动获取涨停榜、龙虎榜数据
- 筛选人气榜前30只股票
- 匹配当前热点逻辑
- 判断市场状态（冰点修复 / 增量主升 / 震荡观望）
- 输出符合条件的重点自选股

### 2. 分析特定股票

**命令**：`/longtou-strategy 分析 <股票名称>`

**功能**：
- 分析指定股票是否符合龙头战法
- 匹配逻辑库
- 判断地位和受益等级
- 给出操作建议

### 3. 查看当前逻辑库

**命令**：`/longtou-strategy 查看逻辑库`

**功能**：
- 显示当前关注的热点逻辑
- 逻辑强度、持续性、驱动类型
- 帮助理解当前市场在炒什么

### 4. 更新逻辑库（智能分析）

**命令**：`/longtou-strategy 更新逻辑库`

**功能**：
- 自动分析当前市场热点板块
- 统计涨停股票的板块和概念分布
- 生成逻辑库更新建议
- **清理退潮逻辑**：移除逻辑强度<4星或已无涨停活跃度的过时逻辑
- 引导添加新的热点逻辑

**更新原则**：
- ✅ **添加**：有3+只涨停且有高连板（≥3板）的新热点
- 📝 **更新**：现有逻辑的龙头换人、强度调整
- 🗑️ **移除**：今日无涨停活跃度、或逻辑已证伪退潮的老题材

> 💡 **逻辑库详细管理**：参考 `reference/logic-management.md`

---

## 🔧 执行流程

当用户调用此 SKILL 时，按以下步骤执行：

### Step 1: 识别用户意图

```python
用户输入 -> 判断意图：
  - "筛选" / "选股" / "今日自选股" / "看情绪" -> 执行早盘筛选
  - "分析" + 股票名称 -> 执行个股分析
  - "逻辑库" / "热点" / "查看逻辑" -> 查看逻辑库
  - "更新逻辑" / "市场热点" / "热点分析" -> 自动分析市场热点并建议更新
```

### Step 2: 执行核心功能

根据用户意图，调用相应的 Python 模块：

```python
import sys
import os

# 动态获取skill路径
workspace_root = os.getcwd()
skill_path = os.path.join(workspace_root, '.cursor/skills/longtou-strategy')
sys.path.insert(0, skill_path)

# 根据意图选择模块
from modules import LongtouScreener        # 筛选
from modules import MarketHotspotAnalyzer  # 市场分析
from modules import LogicMatcher           # 逻辑匹配
```

> 💡 **详细执行代码**：参考 `reference/execution-guide.md`

### Step 3: 格式化输出

根据功能类型，使用标准格式输出结果。

> 💡 **输出格式规范**：参考 `reference/output-format.md`

---

## 📚 参考文档

**核心文档**（按需查阅）：

- 📖 **战法规则**：`reference/strategy-rules.md` - 筛选铁律、三种模式、卖出信号
- 🔧 **执行指南**：`reference/execution-guide.md` - 完整代码模板和实现细节
- 📊 **输出格式**：`reference/output-format.md` - 所有输出的标准格式
- 📝 **逻辑库管理**：`reference/logic-management.md` - 如何更新和维护逻辑库

**配置文件**：

- 逻辑库配置：`.cursor/skills/longtou-strategy/logics.yaml`
- Tushare配置：`.cursor/skills/longtou-strategy/modules/config.py`

---

## ⚠️ 重要提示

1. **逻辑库是核心**：每周更新逻辑库，确保逻辑库反映当前市场热点
2. **不是自动交易**：SKILL只提供筛选和分析，具体买卖需要你判断
3. **仅供参考**：所有分析仅供参考，不构成投资建议
4. **风险自负**：股市有风险，投资需谨慎

---

## 📝 快速上手

### 典型工作流程

**早盘（8:30-9:30）**
```
你：/longtou-strategy 筛选今日自选股

AI：[执行筛选，输出市场状态和重点自选股]
```

**盘中（需要时）**
```
你：/longtou-strategy 分析 横店影视

AI：[输出详细分析]
```

**收盘后（每周或主线切换时）**
```
你：/longtou-strategy 更新逻辑库

AI：[分析市场热点，生成更新建议]
```

---

**数据来源**：东方财富（akshare）+ Tushare Pro  
**更新时间**：2026-02-10
