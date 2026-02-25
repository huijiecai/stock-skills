# 数据查询 API 文档

本文档详细说明龙头战法所需的6类数据查询方法。

## 初始化查询服务

```python
from pathlib import Path
from scripts.query_service import QueryService
from scripts.concept_manager import ConceptManager

# 初始化数据库路径
db_path = Path("data/dragon_stock.db")
service = QueryService(str(db_path))
manager = ConceptManager(str(db_path))
```

## 1. 市场情绪查询

获取指定日期的市场整体状态，用于判断市场是"冰点修复"还是"增量主升"阶段。

### 数据内容
- 涨停/跌停家数
- 连板高度分布（最高几连板）
- 指数表现（上证、深证、创业板）
- 两市总成交额
- 市场阶段判断（情绪冰点/增量主升/正常）

### 查询方法

```python
# 获取市场状态
market_status = service.get_market_status("2026-02-25")

# 返回字段
# {
#     'trade_date': '2026-02-25',
#     'limit_up_count': 50,           # 涨停家数
#     'limit_down_count': 5,          # 跌停家数
#     'max_streak': 3,                # 最高连板数
#     'sh_index_change': 0.0072,      # 上证涨跌幅（小数）
#     'sz_index_change': 0.0129,      # 深证涨跌幅
#     'cy_index_change': 0.0141,      # 创业板涨跌幅
#     'total_turnover': 175.07,       # 总成交额（亿）
#     'market_phase': '正常'           # 市场阶段
# }

# 格式化输出
print(service.format_market_status(market_status))
```

### 市场阶段判断规则

- **情绪冰点**: `跌停家数 > 15 且 最高连板 ≤ 2`
- **增量主升**: `涨停家数 > 30`
- **情绪高潮**: `涨停家数 > 50 且 最高连板 ≥ 5`
- **正常**: 其他情况

---

## 2. 个股全景数据

获取个股完整信息，包括实时行情、涨停状态、关联概念等。

### 数据内容
- 实时行情（价格、量额、换手、振幅）
- 涨停状态、连板天数
- 所属概念、行业分类
- 昨日收盘、今日开高低

### 查询方法

```python
# 获取个股信息（含概念）
stock = service.get_stock_with_concept("002342", "2026-02-25")

# 返回字段
# {
#     'stock_code': '002342',
#     'stock_name': '巨力索具',
#     'market': 'SZ',
#     'open_price': 14.81,
#     'high_price': 16.73,
#     'low_price': 14.66,
#     'close_price': 16.10,
#     'pre_close': 15.21,
#     'change_amount': 0.89,
#     'change_percent': 0.0585,         # 涨跌幅（小数）
#     'volume': 2965779,                # 成交量（手）
#     'turnover': 4728000000,           # 成交额（元）
#     'turnover_rate': 0.0,             # 换手率
#     'is_limit_up': 0,                 # 是否涨停（1/0）
#     'is_limit_down': 0,               # 是否跌停
#     'streak_days': 0,                 # 连板天数
#     'concepts': [                     # 关联概念
#         {'name': '商业航天', 'is_core': 1}
#     ],
#     'industry': 'Producer Manufacturing',
#     'sub_industry': 'Metal Fabrication'
# }

# 格式化输出
print(service.format_stock_info(stock))
```

---

## 3. 概念板块分析

查询概念板块统计，判断"逻辑正宗性"和"板块联动性"。

### 数据内容
- 概念内涨停家数、涨停率
- 板块平均涨幅
- 板块总成交额
- 领涨股识别

### 查询方法

```python
# 获取概念统计
stats = manager.get_concept_stats("商业航天", "2026-02-25")

# 返回字段
# {
#     'trade_date': '2026-02-25',
#     'stock_count': 3,                # 概念内个股数量
#     'limit_up_count': 0,             # 涨停家数
#     'avg_change': 0.0338,            # 平均涨幅（小数）
#     'total_turnover': 53.36,         # 板块总成交额（亿）
#     'leader_code': '002342'          # 领涨股代码
# }

# 获取概念内所有股票
stocks = manager.get_concept_stocks("商业航天")
# [
#     {'stock_code': '002342', 'is_core': 1, 'note': '核心标的'},
#     {'stock_code': '002025', 'is_core': 1, 'note': '核心标的'},
#     ...
# ]

# 获取股票的所有概念
concepts = manager.get_stock_concepts("002342")
# [
#     {'concept_name': '商业航天', 'is_core': 1, 'note': '核心标的'}
# ]
```

---

## 4. 人气排行榜

按成交额获取当日人气股，用于满足"人气底线"筛选条件。

### 数据内容
- Top N 人气股列表（默认30）
- 成交额排名
- 涨停状态、连板天数

### 查询方法

```python
# 获取人气榜 Top 30
popularity = service.get_stock_popularity_rank("2026-02-25", top_n=30)

# 返回字段（列表）
# [
#     {
#         'rank': 1,
#         'stock_code': '000547',
#         'stock_name': '航天发展',
#         'close_price': 16.50,
#         'change_percent': 0.1001,     # 涨跌幅
#         'turnover': 7843000000,       # 成交额（元）
#         'is_limit_up': 1,             # 是否涨停
#         'streak_days': 1              # 连板天数
#     },
#     ...
# ]

# 使用示例：筛选人气前30且涨停的股票
hot_limit_ups = [s for s in popularity if s['is_limit_up'] == 1]
```

---

## 5. 历史走势回溯

查询个股历史表现，判断"地位突出"（身位最高/领涨性强）。

### 数据内容
- 近N日K线数据（默认10日）
- 历史涨停记录
- 连板周期识别

### 查询方法

```python
# 获取近10日历史
history = service.get_stock_history("002342", days=10)

# 返回字段（列表，按日期倒序）
# [
#     {
#         'trade_date': '2026-02-25',
#         'open_price': 14.81,
#         'high_price': 16.73,
#         'low_price': 14.66,
#         'close_price': 16.10,
#         'change_percent': 0.0585,
#         'volume': 2965779,
#         'turnover': 4728000000,
#         'is_limit_up': 0,
#         'streak_days': 0
#     },
#     ...
# ]

# 使用示例：统计近10日涨停次数
limit_up_days = sum(1 for day in history if day['is_limit_up'] == 1)

# 使用示例：找出最长连板周期
max_streak = max(day['streak_days'] for day in history)
```

---

## 6. 涨停时序分析

查询概念内涨停先后顺序，识别"带动性强"的真龙头。

### 数据内容
- 概念内涨停股票列表
- 涨停时间（按时间排序）
- 连板天数

### 查询方法

```python
# 查询概念内涨停顺序
sequence = service.check_limit_up_sequence("商业航天", "2026-02-25")

# 返回字段（列表，按涨停时间排序）
# [
#     {
#         'stock_code': '002342',
#         'stock_name': '巨力索具',
#         'change_percent': 0.1001,
#         'streak_days': 2,
#         'limit_up_time': '09:35:00'    # 涨停时间
#     },
#     ...
# ]

# 使用示例：判断谁是首板龙头
if sequence:
    first_leader = sequence[0]
    print(f"首板龙头: {first_leader['stock_name']} (涨停时间: {first_leader['limit_up_time']})")
```

---

## 7. 概念龙头查询

获取各概念的龙头列表，按涨停家数和平均涨幅排序。

### 查询方法

```python
# 获取涨停家数 ≥ 2 的概念龙头
leaders = service.get_concept_leaders("2026-02-25", min_limit_up=2)

# 返回字段（列表）
# [
#     {
#         'concept_name': '商业航天',
#         'stock_count': 3,
#         'limit_up_count': 2,
#         'avg_change': 0.0520,
#         'total_turnover': 86.50,
#         'leader_code': '002342',
#         'leader_name': '巨力索具',
#         'leader_change': 0.1001,
#         'leader_streak': 2
#     },
#     ...
# ]
```

---

## 常用组合查询

### 场景1：筛选龙头候选股

```python
# 1. 判断市场状态
market = service.get_market_status(date)
is_ice_point = market['limit_down_count'] > 15 and market['max_streak'] <= 2

# 2. 获取人气榜前30
popularity = service.get_stock_popularity_rank(date, 30)

# 3. 筛选涨停且人气高的
candidates = [
    s for s in popularity 
    if s['is_limit_up'] == 1 or s['change_percent'] > 0.05
]

# 4. 查看每只股票的概念
for stock in candidates[:5]:
    concepts = manager.get_stock_concepts(stock['stock_code'])
    print(f"{stock['stock_name']}: {[c['concept_name'] for c in concepts]}")
```

### 场景2：板块强度分析

```python
# 1. 获取所有概念龙头
leaders = service.get_concept_leaders(date, min_limit_up=1)

# 2. 按涨停家数排序
leaders_sorted = sorted(leaders, key=lambda x: x['limit_up_count'], reverse=True)

# 3. 分析强势板块
for leader in leaders_sorted[:5]:
    limit_up_rate = leader['limit_up_count'] / leader['stock_count']
    print(f"{leader['concept_name']}: 涨停率 {limit_up_rate*100:.1f}% "
          f"(涨停{leader['limit_up_count']}/{leader['stock_count']}家)")
```

### 场景3：连板周期追踪

```python
# 获取连板股历史
stock_code = "002342"
history = service.get_stock_history(stock_code, days=10)

# 分析连板周期
current_streak = history[0]['streak_days']
print(f"当前连板: {current_streak}板")

# 找出历史最高连板
max_streak = max(day['streak_days'] for day in history)
print(f"近10日最高: {max_streak}板")
```

---

## 数据采集

### 采集当日市场数据

```bash
# 采集当日数据（使用示例股票）
cd scripts
python market_fetcher.py 2026-02-25

# 计算概念统计
python concept_manager.py 2026-02-25
```

### 批量查询

如需采集全市场数据，需要提供完整的股票列表：

```python
from scripts.market_fetcher import MarketDataFetcher

fetcher = MarketDataFetcher(db_path, api_key)

# 准备股票列表 [(code, name, region), ...]
stock_list = [
    ('000001', '平安银行', 'SZ'),
    ('600000', '浦发银行', 'SH'),
    # ...
]

# 批量采集
fetcher.fetch_all_stocks_daily(trade_date, stock_list)
```

---

## 注意事项

1. **日期格式**: 所有日期参数使用 `YYYY-MM-DD` 格式
2. **百分比表示**: 涨跌幅返回小数格式（如 0.0585 表示 5.85%）
3. **金额单位**: 
   - `turnover` 字段为元
   - `total_turnover` 字段为亿元
4. **数据延迟**: 需要先运行数据采集脚本才能查询当日数据
5. **连板计算**: 连板天数从1开始计数（1板=首板，2板=二连板）
