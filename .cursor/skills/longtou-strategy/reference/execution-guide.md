# 执行指南

本文档详细说明如何执行各种功能。

---

## 🔧 执行流程

### Step 1: 识别用户意图

```python
用户输入 -> 判断意图：
  - "筛选" / "选股" / "今日自选股" / "看情绪" -> 执行早盘筛选
  - "分析" + 股票名称 -> 执行个股分析
  - "逻辑库" / "热点" / "查看逻辑" -> 查看逻辑库
  - "更新逻辑" / "市场热点" / "热点分析" -> 自动分析市场热点并建议更新
```

---

## 核心功能实现

### 1. 早盘筛选（最常用）

```python
# 导入模块（动态获取skill路径）
import sys
import os

# 获取当前工作区路径
workspace_root = os.getcwd()
skill_path = os.path.join(workspace_root, '.cursor/skills/longtou-strategy')
sys.path.insert(0, skill_path)

from modules import LongtouScreener

# 执行筛选
screener = LongtouScreener()
result = screener.screen_stocks(
    top_n=30,              # 筛选人气榜前30只
    min_logic_strength=4   # 最小逻辑强度4星
)

# 格式化输出结果（见 output-format.md）
```

### 2. 个股分析

```python
# 获取股票概念
from modules import DataFetcher, LogicMatcher

fetcher = DataFetcher()
matcher = LogicMatcher()

# 获取概念并匹配逻辑
concepts = fetcher.get_stock_board_concept(stock_code)
logic = matcher.match_logic(concepts)

# 输出分析结果
```

### 3. 查看逻辑库

```python
from modules import LogicMatcher

matcher = LogicMatcher()
logics = matcher.get_all_logics()

# 格式化显示所有逻辑
```

### 4. 自动分析市场热点

```python
from modules import MarketHotspotAnalyzer

analyzer = MarketHotspotAnalyzer()
result = analyzer.generate_logic_suggestion()

# 输出热点分析结果和逻辑库更新建议（见 output-format.md）
```

---

## 完整代码模板

```python
import sys
import os

# 动态获取skill路径
workspace_root = os.getcwd()
skill_path = os.path.join(workspace_root, '.cursor/skills/longtou-strategy')
sys.path.insert(0, skill_path)

from modules import LongtouScreener

# 执行筛选
screener = LongtouScreener()
result = screener.screen_stocks(top_n=30, min_logic_strength=4)

# 检查结果
if 'error' in result:
    print(f"❌ {result['error']}")
else:
    # 输出市场状态
    market_state = result['market_state']
    print(f"## 📊 市场状态分析\n")
    print(f"- **状态**：{market_state['状态']}")
    print(f"- **说明**：{market_state['描述']}")
    print(f"- **昨日跌停**：{market_state['昨日跌停']} 家")
    print(f"- **连板高度**：最高 {market_state['连板高度']} 板")
    print(f"- **重点关注**：{', '.join(market_state['重点关注'])}\n")
    
    # 输出自选股
    selected = result['selected_stocks']
    print(f"## 🎯 今日重点自选股（{len(selected)} 只）\n")
    
    for i, stock in enumerate(selected, 1):
        stars = "⭐" * stock['逻辑强度']
        print(f"### {i}. {stock['名称']} ({stock['代码']}) {stars}\n")
        print(f"**基本信息**")
        print(f"- 连板数：{stock['连板数']} 板")
        print(f"- 首板时间：{stock['首板时间']}")
        print(f"- 龙虎榜：{'是' if stock['龙虎榜'] else '否'}\n")
        print(f"**逻辑分析**")
        print(f"- 匹配逻辑：{stock['逻辑']}")
        print(f"- 炒作原因：{stock['炒作原因']}")
        print(f"- 持续性：{stock['持续性']}")
        print(f"- 驱动类型：{stock['驱动类型']}\n")
        print(f"**地位分析**")
        print(f"- 板块地位：{stock['地位']}")
        print(f"- 判断理由：{stock['地位理由']}")
        print(f"- 受益等级：{stock['受益等级']}\n")
        print(f"**操作建议**")
        print(f"- 推荐模式：{', '.join(stock['推荐模式'])}")
        print(f"- 风险提示：{stock['风险提示']}\n")
        print("---\n")
```
