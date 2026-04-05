# 预期驱动交易系统

> 核心：围绕预期做交易。形态只是确认预期的载体。
> 不是量化公式，是投资者的思维框架。

---

## 目录结构

```
trading-system/
├── README.md                        ← 本文件
├── system/
│   └── trading-system.md            ← 交易系统规则（v2.2）
├── tools/
│   ├── fetch_adata_data.py         ← 数据采集工具（adata，免费）
│   └── fetch_tushare_data.py        ← 数据采集工具（Tushare，历史数据）
├── data/                            ← 采集的数据（JSON，gitignore）
├── daily/
│   └── YYYY-MM-DD/
│       ├── 盘前分析.md              ← 盘前：情绪回顾+预期方向+交易预案
│       ├── 盘后复盘.md              ← 盘后：实际数据+判断回顾+经验教训
│       ├── 模拟看盘.md              ← 盘后：分时回溯+信号模拟
│       └── 信号记录.md              ← 盘后：系统信号触发日志
└── lessons/
    └── learned.md                   ← 经验教训库
```

## 核心流程

```
盘前分析 → 交易预案 → 盘中执行 → 盘后复盘 → 经验教训 → 系统迭代
```

## 数据采集

提供四个数据采集脚本：

### 脚本一：adata（个股/指数/概念基础数据）

`fetch_adata_data.py` 基于 adata，**免费、无需 token、支持当日分时**，适合模拟看盘场景。

```bash
# 获取盯盘股今日全量数据（分时+日线+资金流向）
python tools/fetch_adata_data.py --watch 002192 000722 600726

# 获取指定股票的分时数据
python tools/fetch_adata_data.py --code 002192 --intraday

# 获取指定股票的日线数据（最近30天）
python tools/fetch_adata_data.py --code 002192 --daily

# 获取指数分时/日线
python tools/fetch_adata_data.py --index 000001 --intraday
python tools/fetch_adata_data.py --index 000001 --daily --days 60

# 获取实时行情
python tools/fetch_adata_data.py --realtime 002192 600519 000001

# 获取资金流向
python tools/fetch_adata_data.py --capital 002192

# 获取概念板块数据
python tools/fetch_adata_data.py --concept BK0612 --daily
```

### 脚本二：Tushare（涨停/历史分时）

`fetch_tushare_data.py` 基于 Tushare，支持**历史分钟线**和涨停数据，需要积分。

```bash
# 设置 Tushare Token（一次性）
export TUSHARE_TOKEN='your_token'

# 采集涨停数据
python tools/fetch_tushare_data.py --limit-up --date 2026-04-03

# 采集跌停数据
python tools/fetch_tushare_data.py --limit-up --date 2026-04-03 --type D

# 采集历史分钟数据
python tools/fetch_tushare_data.py --code 002192 --start 2026-03-01 --end 2026-03-27 --intraday
```

### 脚本三：市场情绪指标（新增）

`fetch_market_sentiment.py` 基于 Tushare limit_list_d，采集每日市场情绪数据。

```bash
# 采集指定日期的市场情绪
python tools/fetch_market_sentiment.py --date 2026-04-03

# 采集最近5天的情绪数据
python tools/fetch_market_sentiment.py --days 5
```

**采集内容**:
- 涨停数/跌停数
- 首板涨停/连板涨停
- 最高连板数
- 连板分布（5板/4板/3板/2板/1板）
- 涨停股详情（代码、名称、首封时间、炸板次数）

**数据保存**: `data/market_sentiment/YYYY-MM-DD.json` + `summary.json`

### 脚本四：概念板块排行（新增）

`fetch_concept_rank.py` 基于东方财富，采集概念板块涨幅排行。

```bash
# 获取概念板块涨幅Top50
python tools/fetch_concept_rank.py --top 50

# 获取概念板块跌幅Bottom50
python tools/fetch_concept_rank.py --top 50 --order desc

# 保存排行数据
python tools/fetch_concept_rank.py --top 50 --save
```

**采集内容**:
- 概念板块涨幅排行
- 概念板块跌幅排行
- 板块成交额

**数据保存**: `data/concept_rank/YYYY-MM-DD_up.json` + `YYYY-MM-DD_down.json`

### 脚本五：盘后一键采集（新增）

`collect_daily_data.py` 整合以上所有功能，每日盘后一键执行。

```bash
# 采集今天的全量数据
python tools/collect_daily_data.py

# 采集指定日期
python tools/collect_daily_data.py --date 2026-04-03

# 只采集市场情绪
python tools/collect_daily_data.py --sentiment-only

# 只采集概念排行
python tools/collect_daily_data.py --concept-rank-only
```

**采集流程**:
1. 市场情绪指标（涨停/跌停/连板）
2. 概念板块涨幅/跌幅排行
3. 盯盘股数据（分时+日线+资金流向）
4. 指数数据（分时+日线）

### 环境变量（Tushare）

| 变量 | 说明 | 示例 |
|------|------|------|
| TUSHARE_TOKEN | Tushare API token | export TUSHARE_TOKEN='xxx' |
| TUSHARE_DOMAIN | 自定义API域名（可选） | export TUSHARE_DOMAIN='http://tushare.xyz' |

### Tushare 权限要求

| 数据类型 | 需要积分 |
|---------|---------|
| 日线 | 免费 |
| 基本面（PE/PB/换手率） | 免费 |
| 分钟线（1min/5min等） | 5000 积分 |
| 涨停数据 | 1200 积分 |
| 指数日线 | 免费 |

### 方案对比

| 特性 | adata | Tushare |
|------|-------|---------|
| 费用 | **免费** | 需积分 |
| 注册 | **无需** | 需要 |
| 当日分时 | ✅ | ✅ |
| 历史分时 | ❌ | ✅ |
| 涨停数据 | ❌ | ✅ |
| 实时行情 | ✅ | ❌ |
| 资金流向 | ✅ | ✅ |

**建议**：模拟看盘用 adata（每日盘后获取当天数据），历史回溯用 Tushare。

## 系统版本

- **v1**：4阶段情绪周期（冰点→修复→高潮→退潮）
- **v2**：7阶段主线生命周期（冰点→修复→分歧→再确认→主升→高潮→退潮），三维确认信号
- **v2.1**：补入实战教训（多主线并行、板块内部结构、全市场催化扫描、周末风险预案）
- **v2.2**：盘中感知框架（触发条件+快速评估+决策矩阵）、阶段判断确定性标注、虚拟交易账户
- **v2.3**：全市场催化扫描、改主意条件、盘中感知触发条件
- **v2.4**：外围市场跟踪、隔夜公告扫描、预期强度评估
- **v2.5**：买点分级体系（A/B/C级）、虚拟信号回测机制

## 关键原则

- 低频，但确定
- 不猜、不赌、不扛
- 指标是感知信号，不是触发条件
- 每个决策回到核心问题：预期确认了？兑现了？失效了？
