# 龙头战法数据系统

支持龙头战法的完整数据获取、存储和查询系统。

## 系统架构

本系统采用**分层架构**，将用户功能、技术文档和实现代码分离：

```
skills/dragon-stock-trading/
├── SKILL.md                    # 用户层：功能描述
├── reference/                  # 文档层：技术细节（新增）
│   ├── 龙头战法理论.md         # 预期管理、情绪拐点
│   ├── 数据库设计.md (已移至 ../../backend/)
│   ├── 概念配置指南.md         # 配置维护方法
│   └── 系统架构.md             # 架构设计
├── scripts/                    # 实现层：Python 模块
│   ├── db_init.py
│   ├── market_fetcher.py
│   ├── concept_manager.py
│   ├── query_service.py
│   ├── history_sync.py
│   └── (采集工具见 tools/ 目录)
├── data/                       # 数据层
│   ├── dragon_stock.db        # SQLite数据库（系统自动）
│   ├── concepts.json          # 概念配置（手工维护）
│   └── stock_list.json        # 关注股票池（手工维护，后续自行补充）
├── tests/                      # 测试
│   ├── test_basic_modules.py
│   └── test_integration.py
├── examples.md
├── config.yaml
└── README.md
```

**设计理念**：
- **SKILL.md** - 简洁清晰，只描述"做什么"
- **reference/** - 详细完整，说明"怎么做"
- LLM 根据需求自动查找 reference 文档

## 开发规范

### 数据访问原则 ⚠️

**所有对数据库的操作必须通过后端 API 接口，禁止直接读取数据库文件**

理由：
1. **统一数据校验** - 后端接口包含完整的数据验证逻辑
2. **事务一致性** - 保证数据操作的原子性和一致性
3. **权限控制** - 通过API层控制不同角色的数据访问权限
4. **易于维护** - 业务逻辑集中在一个地方，便于修改和扩展

**正确的做法**：
```python
# ✅ 正确：通过后端API查询
from scripts.backend_client import BackendClient
client = BackendClient()
result = client.get_stock_intraday_existence("000001", "2026-02-26")

# 或者直接调用后端接口
import requests
response = requests.get("http://localhost:8000/api/stocks/intraday-exists/000001/2026-02-26")
```

**错误的做法**：
```python
# ❌ 错误：直接读取数据库（违反规范）
import sqlite3
conn = sqlite3.connect("../../data/dragon_stock.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM stock_intraday WHERE stock_code=? AND trade_date=?", ...)
```

### 代码结构规范

1. **分层清晰** - 严格区分 scripts/（实现）、reference/（文档）、tests/（测试）
2. **命名规范** - 使用下划线命名法（snake_case）
3. **异常处理** - 所有外部调用必须包含try-except
4. **日志记录** - 关键操作必须输出日志，便于调试

## 核心功能

### 6类数据能力

1. **市场情绪数据** - 涨停/跌停家数、连板高度、指数表现、市场阶段判断
2. **个股基础数据** - 实时行情、涨停状态、连板天数、关联概念
3. **题材概念数据** - 概念内涨停家数、平均涨幅、领涨股识别
4. **人气排行数据** - 按成交额排名，筛选人气标的
5. **历史走势数据** - 近期K线、涨停记录、连板周期
6. **板块联动数据** - 同概念涨跌分布、涨停先后顺序

## 快速开始

### 1. 初始化系统

```bash
# 初始化数据库
cd scripts
python db_init.py

# 加载概念配置
python concept_manager.py
```

### 2. 采集数据

```bash
# 采集当日市场数据（示例股票）
python market_fetcher.py 2026-02-25

# 重新计算概念统计
python concept_manager.py 2026-02-25
```

### 3. 查询数据

```bash
# 查询市场状态和个股信息
python query_service.py 2026-02-25
```

### 4. 在代码中使用

```python
from pathlib import Path
from scripts.query_service import QueryService

# 初始化查询服务
db_path = Path("data/dragon_stock.db")
service = QueryService(str(db_path))

# 查询市场状态（判断冰点/主升）
market = service.get_market_status("2026-02-25")
print(f"市场阶段: {market['market_phase']}")
print(f"涨停家数: {market['limit_up_count']}")

# 查询个股信息（含概念）
stock = service.get_stock_with_concept("002342", "2026-02-25")
print(f"{stock['stock_name']}: {stock['change_percent']*100:+.2f}%")
print(f"概念: {[c['name'] for c in stock['concepts']]}")

# 查询人气榜 Top 30
popularity = service.get_stock_popularity_rank("2026-02-25", 30)
for stock in popularity[:10]:
    print(f"{stock['rank']}. {stock['stock_name']} 成交{stock['turnover']/100000000:.2f}亿")

# 查询概念龙头
leaders = service.get_concept_leaders("2026-02-25", min_limit_up=2)
for leader in leaders:
    print(f"{leader['concept_name']}: {leader['leader_name']} (涨停{leader['limit_up_count']}家)")
```

## 数据库设计

### 核心表结构

- **market_sentiment** - 市场情绪日统计（涨停/跌停家数、连板高度）
- **stock_daily** - 个股日行情（价格、量额、涨停状态、连板天数）
- **stock_info** - 股票基本信息（行业分类）
- **stock_concept** - 概念-股票关系（核心标的标识）
- **concept_daily** - 概念日统计（涨停家数、平均涨幅、领涨股）
- **stock_events** - 异动记录（监管、公告）

## 概念配置

通过 `data/concepts.json` 维护概念与股票的关系：

```json
{
  "商业航天": {
    "core_stocks": ["002025", "002342"],
    "related_stocks": ["300416"],
    "keywords": ["火箭", "卫星", "航天器"]
  }
}
```

## 测试

### 运行单元测试

```bash
cd tests
python test_basic_modules.py
```

### 运行集成测试

```bash
python test_integration.py
```

测试覆盖：
- ✅ 数据库初始化
- ✅ 概念配置加载
- ✅ 市场数据采集
- ✅ 市场情绪计算
- ✅ 概念统计计算
- ✅ 数据查询服务
- ✅ 格式化输出

## 龙头战法应用

### 预期管理四步法

1. **建立预期** - 使用人气榜+概念统计筛选标的
2. **买入确认** - 通过市场状态判断节点，个股走势确认
3. **卖出兑现** - 分时走势监控，预期兑现即离场
4. **复盘验证** - 历史走势回溯，验证预期有效性

### 情绪拐点三板斧

#### 模式1：冰点修复
```python
# 判断市场是否冰点
market = service.get_market_status(date)
is_ice_point = (market['limit_down_count'] > 15 and 
                market['max_streak'] <= 2)

# 找抗分歧标的
popularity = service.get_stock_popularity_rank(date, 30)
# 筛选人气前30且跌幅较小的
```

#### 模式2：龙头弱转强
```python
# 找爆量分歧后的龙头
leaders = service.get_concept_leaders(date)
# 次日观察是否高开强承接
```

#### 模式3：补涨分离
```python
# 龙头断板当日，找分离标的
sequence = service.check_limit_up_sequence(concept, date)
# 看谁在龙头弱时主动走强
```

## 注意事项

1. **API 限制** - itick 有频率限制，采集全市场需控制速度
2. **数据完整性** - 首次使用需采集当日数据，历史数据通过每日积累
3. **概念维护** - 概念配置需手工维护，建议定期更新
4. **缓存策略** - 数据库保留最近N天数据（配置 config.yaml）

## 环境变量

```bash
export ITICK_API_KEY="your_api_key_here"
```

## 后续扩展

- [ ] 龙虎榜数据集成
- [ ] 资金流向计算（基于 tick 数据）
- [ ] 分时数据缓存（精确涨停时间）
- [ ] 消息面数据（公告、新闻）
- [ ] 自动化调度（每日15:30自动采集）

## License

MIT
