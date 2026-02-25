---
name: stock-analysis
description: 股票分析工具，输入股票代码或名称，获取实时行情和技术分析。支持A股市场股票基本信息查询和基础技术面分析。
---

# 股票分析工具

## 核心功能

这是一个专门用于股票分析的工具，帮助用户获取A股股票的实时行情和基础技术分析，并支持龙头战法所需的市场情绪、概念板块、人气排行等多维度数据查询。

### 功能1：股票基本信息查询
输入股票代码或名称，获取该股票的详细信息，包括：
- 股票代码和简称
- 最新价格和涨跌幅
- 成交量和成交额
- 市值信息
- 行业分类
- 基础技术面分析

### 功能2：龙头战法数据支持

本工具提供以下6类数据查询能力，全面支持龙头战法决策：

#### 2.1 市场情绪查询
获取指定日期的市场整体状态：
- 涨停/跌停家数
- 连板高度分布
- 指数表现（上证、深证、创业板）
- 两市总成交额
- 市场阶段判断（情绪冰点/增量主升/正常）

**用途**: 判断市场是"冰点修复"还是"增量主升"阶段，决定操作策略

**示例查询**:
```python
from scripts.query_service import QueryService
service = QueryService("data/dragon_stock.db")
market_status = service.get_market_status("2026-02-25")
print(service.format_market_status(market_status))
```

#### 2.2 个股全景数据
获取个股完整信息：
- 实时行情（价格、量额、换手、振幅）
- 涨停状态、连板天数
- 所属概念、行业分类
- 技术面分析（支撑/阻力、趋势判断）

**用途**: 全面了解个股基本面和技术面，支持"建立预期"

**示例查询**:
```python
stock_info = service.get_stock_with_concept("002342", "2026-02-25")
print(service.format_stock_info(stock_info))
```

#### 2.3 概念板块分析
查询概念板块统计：
- 概念内涨停家数、涨停率
- 板块平均涨幅
- 板块总成交额
- 领涨股识别

**用途**: 判断"逻辑正宗性"和"板块联动性"

**示例查询**:
```python
from scripts.concept_manager import ConceptManager
manager = ConceptManager("data/dragon_stock.db")
stats = manager.get_concept_stats("商业航天", "2026-02-25")
```

#### 2.4 人气排行榜
按成交额获取当日人气股：
- Top 30 人气股列表
- 成交额排名
- 涨停状态标识

**用途**: 满足"人气底线"筛选条件（龙头战法要求标的进入人气榜前30）

**示例查询**:
```python
popularity = service.get_stock_popularity_rank("2026-02-25", top_n=30)
for stock in popularity[:10]:
    print(f"{stock['rank']}. {stock['stock_name']} {stock['change_percent']*100:+.2f}%")
```

#### 2.5 历史走势回溯
查询个股历史表现：
- 近10日K线数据
- 历史涨停记录
- 连板周期识别

**用途**: 判断"地位突出"（身位最高/领涨性强），识别连板周期

**示例查询**:
```python
history = service.get_stock_history("002342", days=10)
for day in history:
    status = "涨停" if day['is_limit_up'] else ""
    print(f"{day['trade_date']}: {day['close_price']:.2f} {day['change_percent']*100:+.2f}% {status}")
```

#### 2.6 涨停时序分析
查询概念内涨停先后顺序：
- 首板时间
- 带动关系分析

**用途**: 识别"带动性强"的真龙头（谁先涨停带动板块）

**示例查询**:
```python
sequence = service.check_limit_up_sequence("商业航天", "2026-02-25")
for idx, stock in enumerate(sequence, 1):
    print(f"{idx}. {stock['stock_name']} 涨停时间: {stock['limit_up_time']}")
```

### 功能3：概念配置管理

通过 `data/concepts.json` 文件维护股票与概念的关系：
```json
{
  "商业航天": {
    "core_stocks": ["002025", "002342"],
    "related_stocks": ["300416"],
    "keywords": ["火箭", "卫星", "航天器"]
  }
}
```

加载配置：
```bash
python scripts/concept_manager.py
```

## 使用方法

### 方式1：直接查询股票信息

由于itick API的技术限制，当前需要按以下步骤操作：

1. **获取股票代码**：用户需先通过其他渠道（如搜索引擎、证券交易软件）确认目标股票的6位数字代码
2. **输入股票代码**：直接提供6位股票代码进行查询
3. **获取实时数据**：系统通过itick API获取该股票的实时行情信息
4. **格式化输出**：以清晰的格式展示股票基本信息和技术分析

### 方式2：使用数据查询服务

通过 Python 脚本直接查询数据库：

#### 初始化数据库
```bash
cd scripts
python db_init.py
```

#### 采集当日市场数据
```bash
# 采集当日全市场数据（示例股票）
python market_fetcher.py 2026-02-25

# 加载概念配置
python concept_manager.py 2026-02-25
```

#### 查询市场和个股信息
```bash
# 查询市场状态和个股信息
python query_service.py 2026-02-25
```

#### 在代码中使用
```python
from pathlib import Path
from scripts.query_service import QueryService

db_path = Path("data/dragon_stock.db")
service = QueryService(str(db_path))

# 查询市场状态
market = service.get_market_status("2026-02-25")
print(service.format_market_status(market))

# 查询个股信息（含概念）
stock = service.get_stock_with_concept("002342", "2026-02-25")
print(service.format_stock_info(stock))

# 查询人气榜
popularity = service.get_stock_popularity_rank("2026-02-25", 30)

# 查询概念龙头
leaders = service.get_concept_leaders("2026-02-25", min_limit_up=2)
```

### 示例对话

**用户**："000547怎么样"
**响应**：
```
🔍 000547 (000547) 基本信息

📡 实时数据 (来自itick API)
📈 最新价格：27.58元 (-1.85%)
📊 涨跌额：-0.52元
📊 成交量：1,543,128手
💰 成交额：43.14亿元

📈 技术面分析：
- 今日振幅：3.35%
- 开盘点位：27.75元
- 最高价：28.45元
- 最低价：27.51元
- 昨收价：28.10元
- 数据时间：2026-02-24 14:59:24

📊 基础分析：
- 短期趋势：小幅调整
- 成交活跃度：较高
- 支撑位：27.50元左右
- 阻力位：28.50元左右
```

### 重要说明

⚠️ **API限制提醒**：
- itick API目前**不支持**根据股票名称进行模糊搜索
- 仅支持通过**6位数字股票代码**直接查询
- 建议用户先通过其他途径确认准确的股票代码

## 技术分析要点

### 价格分析
- 当前价格相对于昨日收盘价的位置
- 今日价格波动幅度
- 开盘价与收盘价的关系

### 成交量分析
- 成交量大小反映市场关注度
- 量价配合关系判断趋势可靠性
- 换手率水平评估流动性

### 技术形态
- 短期趋势判断（上涨/下跌/震荡）
- 关键支撑位和阻力位识别
- 价格波动区间分析

## 注意事项

⚠️ **风险提示**：
- 股市有风险，投资需谨慎
- 本工具仅供学习参考，不构成投资建议
- 请结合自身风险承受能力做出投资决策

📌 **使用建议**：
- 结合多种分析方法综合判断
- 关注市场整体环境变化
- 及时跟踪相关政策和消息面影响

## 相关资源

- [技术分析指标说明](reference/技术指标详解.md)
- [风险管理指南](reference/风险控制.md)