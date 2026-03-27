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
│   └── fetch_data.py                ← 数据采集工具（Tushare）
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

```bash
# 设置 Tushare Token（一次性）
export TUSHARE_TOKEN='your_token'

# 采集融捷股份日线+分钟数据
python tools/fetch_data.py --code 002192 --days 30 --intraday

# 指定日期+5分钟频率
python tools/fetch_data.py --code 002192 --start 2026-03-01 --end 2026-03-27 --intraday --freq 5min

# 采集涨停数据
python tools/fetch_data.py --limit-up --date 2026-03-27

# 采集指数日线（上证/深成/创业板）
python tools/fetch_data.py --code 000001 --days 60 --index
```

### 环境变量

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

## 系统版本

- **v1**：4阶段情绪周期（冰点→修复→高潮→退潮）
- **v2**：7阶段主线生命周期（冰点→修复→分歧→再确认→主升→高潮→退潮），三维确认信号
- **v2.1**：补入实战教训（多主线并行、板块内部结构、全市场催化扫描、周末风险预案）
- **v2.2**：盘中感知框架（触发条件+快速评估+决策矩阵）、阶段判断确定性标注、虚拟交易账户

## 关键原则

- 低频，但确定
- 不猜、不赌、不扛
- 指标是感知信号，不是触发条件
- 每个决策回到核心问题：预期确认了？兑现了？失效了？
