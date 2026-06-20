# stock — A 股量化 + AI 交易闭环

> 个人 A 股量化数据平台 + AI 驱动的预期交易系统。
> 最近一次更新：2026-06-13
>
> **AI 接手须读**：本文件是项目级入口，任何 AI（Qoder / Cursor / Claude Code / Codex 等）首次进入本仓库时**必须先完整读完本文，再开始任何工作**。

---

## 0. 一句话定位

一个 Go CLI（[`astock/`](astock/)）把 A 股全市场行情从 TDX 同步到本地 ClickHouse，三个 AI Skill（[`skills/`](skills/)）在其上做盘前/盘中/盘后的交易决策闭环。所有行情数据**只能通过 astock 访问**，禁止任何形式绕库直读。

---

## 1. 仓库结构

```
stock/
├── README.md                       ← 本文件（项目级入口）
│
├── astock/                         ★ Go CLI：行情数据平台（TDX → ClickHouse）
│   ├── README.md                     使用文档（命令树/同步频率分级）
│   ├── docker-compose.yml            ClickHouse 容器编排
│   ├── cmd/astock/                   命令实现（sync / query / live / stats）
│   ├── internal/                     业务模块（fetch/db/model/query）
│   ├── data/                         ClickHouse 持久化目录（gitignore）
│   └── build/astock                  编译产物（gitignore）
│
├── skills/                         ★ AI Skills
│   └── trading-system/               【唯一·主力】预期驱动交易系统（含研究分析能力）
│       ├── SKILL.md                    系统入口（v3.10）
│       ├── README.md                   工具链与数据采集说明
│       ├── system/
│       │   ├── trading-system.md       规则体系（红线 R1~R12）
│       │   └── templates.md            盘前/模拟看盘/复盘模板（★强制★节点定义）
│       ├── account/portfolio.md        虚拟交易账户状态（最新持仓/累计盈亏）
│       ├── expectations/tracker.md     活跃预期清单（R8 红线依赖）
│       ├── lessons/learned.md          L001~L023 实战教训库
│       ├── knowledge/                  产业链知识 + 公司/行业分析模板
│       ├── daily/YYYY-MM/DD/           每日 4 件套：盘前/模拟看盘/复盘/信号记录
│       └── tools/                      Python 数据采集脚本（adata/tushare，逐步被 astock 替代）
│
├── docs/superpowers/specs/         系统设计文档
│   └── 2026-06-13-astock-ch-design.md   astock ClickHouse 版设计（最新，替代旧 PG 方案）
│
└── data/postgres/                  【已废弃】旧 PG 数据目录（CH 已迁移至 astock/data/）
```

---

## 2. 数据流与技术栈

```
┌──────────┐    sync    ┌──────────────┐   query    ┌──────────────────┐
│ TDX 行情 │ ─────────▶ │ ClickHouse   │ ─────────▶ │ astock CLI       │
│ (通达信) │            │ (本地容器)   │            │ (Go, cobra)      │
└──────────┘            │ kline_daily  │   live     └────────┬─────────┘
                        │ kline_minute │   (直连TDX)         │
                        │ block_*      │                     │ JSON/Table
                        │ securities   │                     ▼
                        │ limit_ladder │            ┌──────────────────┐
                        └──────────────┘            │ AI Skills        │
                                                    │ (trading-system) │
                                                    └────────┬─────────┘
                                                             ▼
                                                    ┌──────────────────┐
                                                    │ daily/YYYY-MM/   │
                                                    │ DD/盘前·看盘·复盘 │
                                                    └──────────────────┘
```

| 层 | 技术 | 说明 |
|----|------|------|
| 数据源 | TDX（通达信） | 覆盖 99% 场景，已废弃东财/腾讯/同花顺多源 |
| 存储 | ClickHouse（列存） | 量化场景比 PG 快 5-10× |
| CLI | Go + cobra + `injoyai/tdx` | 三组命令 sync / query / live |
| AI Skill | Markdown + 少量 Python 工具 | 全部基于 astock 输出做决策 |
| 文档 | Markdown | 设计文档 + 每日交易日志 + 教训库 |

---

## 3. AI 接手 Checklist（首次进入本仓库必做）

### Step 1 — 理解当前阶段

读 [`skills/trading-system/account/portfolio.md`](skills/trading-system/account/portfolio.md) 顶部，获取：
- 最近交易日 + 虚拟账户当前总资产 / 现金 / 持仓三项
- 每只持仓的成本价、失效线、失效依据

### Step 2 — 理解系统规则

读以下 3 个文件（按顺序）：
1. [`skills/trading-system/SKILL.md`](skills/trading-system/SKILL.md) — 系统核心逻辑（预期/三维确认/决策树）
2. [`skills/trading-system/system/trading-system.md`](skills/trading-system/system/trading-system.md) — 红线 R1~R12（强约束）
3. [`skills/trading-system/system/templates.md`](skills/trading-system/system/templates.md) — 盘前/模拟看盘/复盘模板，**第 287-346 行的 4 个 ★强制★ 节点不可跳过**

### Step 3 — 理解数据工具

读 [`astock/README.md`](astock/README.md)，掌握以下高频命令：

```bash
# 真实看盘（直连 TDX，全市场任意股票）
./astock/build/astock live block rank --type concept --limit 30   # 板块涨停排行（已含涨停数列）
./astock/build/astock live block members <板块代码> --json         # 板块成分股
./astock/build/astock live quote 000630                            # 实时报价
./astock/build/astock live minute 000630                           # 实时分时

# 历史回溯（查 CH）
./astock/build/astock query kline 000630 --date 20260612 --limit 30 --json
./astock/build/astock query kline 600487 --freq 1m --date 20260612 --limit 240 --json
./astock/build/astock query limit 20260612 --exclude-st --json     # 当日涨停股
./astock/build/astock query block rank --date 20260612 --type concept --limit 30
```

### Step 4 — 检查最近教训

读 [`skills/trading-system/lessons/learned.md`](skills/trading-system/lessons/learned.md) 最新几条（L019-L023），避免重蹈覆辙。

---

## 4. 关键约束 / 红线

### 4.1 数据访问

- ❌ **严禁 `curl http://localhost:8123` 或任何形式直读 ClickHouse / PostgreSQL**
- ❌ **严禁用 WebSearch 替代行情查询**（WebSearch 只用于消息面：政策/公告/研报/外盘）
- ✅ 行情数据**只能通过 astock CLI**
- ✅ astock 缺什么命令/字段 → **补到 astock 里**（参考 6/13 `live block rank` 新增 `LimitUpCount` 的实现），不要绕开

### 4.2 交易决策

- ❌ 禁止偏向"不操作"：失效线未到 → 不卖是纪律；三维三齐 → 不买也是违纪
- ❌ 禁止用"叙事流"（剧本式心理活动）替代"填表流"（按 templates.md ★强制★节点逐格填表）
- ❌ 禁止把模板里的 ★强制★ 节点写"待查 / 观察 / 后续评估"然后跳过
- ✅ 任何模拟看盘 / 真实看盘 / 盘前分析任务，**启动前先用 TodoWrite 把 templates.md 的 ★强制★ 节点列为待办**
- ✅ 候选方向优先级判定铁律：前一日涨停数 **≥5 只必须 P1**，2-4 只 P2，0-1 只 P3

### 4.3 文档维护

- 每日盘后必须更新 [`account/portfolio.md`](skills/trading-system/account/portfolio.md) 顶部账户状态
- 每个交易日产出 [`daily/YYYY-MM/DD/`](skills/trading-system/daily/) 下的 4 件套（盘前/模拟看盘/复盘/信号记录）
- 新发现的结构性教训追加到 [`lessons/learned.md`](skills/trading-system/lessons/learned.md)（编号续 L024+）
- astock 能力升级后更新本文件第 3 节命令清单

---

## 5. 当前阶段（2026-06-13）

| 项 | 值 |
|----|----|
| 当前日期 | 2026-06-13（周六） |
| 最近交易日 | 2026-06-12（周五，已完成模拟看盘） |
| 下一交易日 | **2026-06-15（周一）** |
| 阶段切换 | **6/15 起从"模拟看盘"切换为"真实看盘"** |
| 账户性质 | 虚拟账户（用户暂未接入真实下单），数据来源切换为 `live` 实时 |

### 5.1 虚拟账户状态（2026-06-12 收盘）

| 标的 | 数量 | 成本价 | 6/12 收盘 | 失效线 | 失效依据 |
|------|------|--------|-----------|--------|----------|
| 亨通光电 600487 | 300 | 89.55 | 97.00 | 89.55 | 光纤涨价 + CPO 逻辑被否定 |
| 沪电股份 002463 | 100 | 116.50 | 125.20 | 104.50 | PCB 扩产 + AI 硬件需求被否定 |
| 铜陵有色 000630 | 1500 | 6.60 | 7.10 | 黄金涨停≤2只+金价-3% | 6/12 盘中感知三维三齐买入 |

- 现金 **54,279.40** / 持仓市值 **52,270.00** / 总资产 **106,549.40**（累计 **+6.55%**）

### 5.2 最近会话关键变更

1. **astock 能力升级**：`live block rank` 新增 `LimitUpCount` 字段（与 `query block rank` 对齐）
   - 文件：[`astock/cmd/astock/live_block.go`](astock/cmd/astock/live_block.go)
   - commit：`d7fcead`
2. **6/12 模拟看盘补完**：从"全天 0 操作"修正为"10:30 盘中感知触发买入铜陵有色 1500 股 @6.60"
   - 文件：[`skills/trading-system/daily/2026-06/12/模拟看盘.md`](skills/trading-system/daily/2026-06/12/模拟看盘.md)
3. **6/15 周一盘前分析**已产出：[`skills/trading-system/daily/2026-06/15/盘前分析.md`](skills/trading-system/daily/2026-06/15/盘前分析.md)

### 5.3 已知能力缺口

| 缺口 | 影响 | workaround |
|------|------|-----------|
| 涨停首封时间字段 | 无法直接判断 10:30 时哪只已封板 | `live block members` 实时观察 + 日 K open/low 反推 |
| 历史日盘中实时快照 | 历史日 10:30 板块涨停数无法回溯 | 已完成的历史模拟日不再回溯 |
| 非监控股 1m 历史 K | 仅 ~295 只监控股有 `kline_minute` | 用 `sync kline --code <x> --freq 1m --days 1` 按需补 |

---

## 6. 环境与启动

### 6.1 必备环境

| 组件 | 版本 | 用途 |
|------|------|------|
| Go | 1.21+ | astock 编译 |
| Docker / Docker Compose | 24+ | ClickHouse 容器 |
| Python | 3.10+ | skills/trading-system/tools 部分脚本（逐步退役） |

### 6.2 启动步骤

```bash
# 1. 起 ClickHouse（持久化目录在 astock/data/clickhouse）
cd astock && docker compose up -d

# 2. 编译 astock
make build      # 或 go build -o build/astock ./cmd/astock/

# 3. 验证
./build/astock live block rank --type concept --limit 10
```

### 6.3 每日盘后同步（cron 推荐）

```bash
# 全市场 daily K（10-30min）
./astock sync all --all --days 1 --skip-info --skip-finance --skip-xdxr --skip-minute

# 监控股多频率 K（持仓+候选）
./astock sync all --code 600487,002463,000630 --days 1 \
    --skip-info --skip-finance --skip-xdxr
```

详见 [`astock/README.md`](astock/README.md) "同步频率分级"小节。

---

## 7. 这个 README 如何维护

- **每个交易日盘后**：更新第 5 节（日期 / 账户状态 / 重要变更）
- **astock 能力变更**：更新第 3 节命令清单 + 第 5.3 节能力缺口
- **新增系统规则 / 教训**：在第 3 节 Step 4 提示更新位置
- **架构变动**（如新增 skill、迁移存储）：更新第 1/2 节

> **维护原则**：本文件是"活文档"。任何 AI 接手时若发现内容过期，**先更新本文件再开始任务**。这是项目的元规则。
