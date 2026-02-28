# 数据采集脚本使用说明

## 📋 概述

本目录包含以下数据采集脚本：

| 脚本名称 | 功能 | 使用场景 |
|---------|------|---------|
| `import_stock_pool.py` | 从概念股票池体系文档导入股票到后端 | 首次初始化股票池 |
| `collect_market_data_optimized.py` | 采集市场数据（优化版） | 每日行情数据采集 |
| `collect_intraday_data_optimized.py` | 采集分时数据（优化版） | 每日分时数据采集 |
| `run_full_collection.py` | 一键执行所有任务 | 完整数据初始化 |

## 🚀 快速开始

### 1. 首次使用 - 完整数据初始化

```bash
# 进入脚本目录
cd skills/dragon-stock-trading/scripts

# 一键执行：导入股票池 + 采集最近 60 天数据
python run_full_collection.py
```

### 2. 分步执行

```bash
# Step 1: 导入股票池（595 只股票）
python run_full_collection.py --step import

# Step 2: 采集最近 60 天市场数据
python run_full_collection.py --step market --days 60

# Step 3: 采集最近 60 天分时数据
python run_full_collection.py --step intraday --days 60
```

### 3. 日常维护

```bash
# 采集今日市场数据
python collect_market_data_optimized.py --days 1

# 采集今日分时数据
python collect_intraday_data_optimized.py --days 1
```

## 📖 详细说明

### 脚本 1: import_stock_pool.py

**功能**：从 `docs/概念股票池体系.md` 解析所有股票并导入后端数据库

**使用方法**：
```bash
python import_stock_pool.py
```

**特性**：
- ✅ 自动解析 Markdown 表格
- ✅ 去重处理（避免重复导入）
- ✅ 批量同步到 stock_info 表
- ✅ 详细统计信息

**输出示例**：
```
====================================================================
股票池导入工具
====================================================================

📅 执行时间：2026-03-01 10:30:00
📖 正在读取文档：/path/to/docs/概念股票池体系.md
📊 文档大小：125000 字节
✅ 提取到 595 只唯一股票

💾 开始导入股票到后端...
  总数：595 只
  批次：50 只/批

  批次 1/12: ⏭️⏭️✅✅✅... (本批完成)
  ...

📊 导入统计:
  成功：580 只
  失败：0 只
  跳过：15 只（已存在）

✅ 导入完成
```

---

### 脚本 2: collect_market_data_optimized.py

**功能**：采集指定日期范围的市场数据和个股行情

**使用方法**：
```bash
# 采集最近 60 天
python collect_market_data_optimized.py --days 60

# 采集指定日期范围
python collect_market_data_optimized.py --start 2025-12-01 --end 2026-02-28

# 强制重新采集（不跳过已存在的数据）
python collect_market_data_optimized.py --days 60 --force
```

**参数说明**：
- `--days N`: 采集最近 N 天的数据（默认 60）
- `--start YYYY-MM-DD`: 开始日期
- `--end YYYY-MM-DD`: 结束日期（默认为今天）
- `--force`: 强制重新采集
- `--no-skip-weekend`: 不跳过周末（采集所有日期）

**优化特性**：
1. ✅ **断点续传** - 自动跳过已采集的日期
2. ✅ **限流保护** - 180 次/分钟（保守设置）
3. ✅ **失败重试** - 网络异常自动重试
4. ✅ **进度保存** - 每 10 个日期保存一次进度
5. ✅ **详细日志** - 日志文件保存在 `logs/` 目录
6. ✅ **错误容忍** - 单只股票失败不影响整体

**采集内容**：
- 市场概况（涨停/跌停数量、指数涨跌幅等）
- 股票池所有股票的日 K 线数据
- 自动判断涨停/跌停状态
- 同步到后端数据库

---

### 脚本 3: collect_intraday_data_optimized.py

**功能**：采集指定日期范围的分时数据

**使用方法**：
```bash
# 采集最近 60 天
python collect_intraday_data_optimized.py --days 60

# 采集指定日期范围
python collect_intraday_data_optimized.py --start 2025-12-01 --end 2026-02-28

# 强制重新采集
python collect_intraday_data_optimized.py --days 60 --force
```

**参数说明**：与市场数据脚本相同

**优化特性**：
1. ✅ **严格限流** - 180 次/分钟（Tushare API 限制 200 次/分钟）
2. ✅ **增量采集** - 自动跳过已存在的分时数据
3. ✅ **定期休息** - 每 50 只股票休息 2 秒，每 10 个日期休息 10 秒
4. ✅ **详细日志** - 记录每只股票的采集状态

**采集内容**：
- 股票池所有股票的分时数据（1 分钟 K 线）
- 包含：时间、价格、涨跌幅、成交量、成交额、均价
- 同步到后端数据库

---

### 脚本 4: run_full_collection.py

**功能**：一键执行所有数据采集任务

**使用方法**：
```bash
# 全部执行（默认 60 天）
python run_full_collection.py

# 自定义天数
python run_full_collection.py --days 30

# 只导入股票池
python run_full_collection.py --step import

# 只采集市场数据
python run_full_collection.py --step market --days 60

# 只采集分时数据
python run_full_collection.py --step intraday --days 60

# 指定日期范围
python run_full_collection.py --step market --start-date 2025-12-01 --end-date 2026-02-28
```

**执行流程**：
```
Step 1: 导入股票池（595 只股票）
   ↓
Step 2: 采集市场数据（60 天）
   ↓
Step 3: 采集分时数据（60 天）
```

**预计耗时**：
- Step 1: 2-5 分钟（取决于网络速度）
- Step 2: 约 30-40 分钟（60 个交易日 × 595 只股票）
- Step 3: 约 60-80 分钟（60 个交易日 × 595 只股票，受 API 限流影响）

---

## 🔧 高级用法

### 1. 后台运行（长时间执行）

```bash
# 使用 nohup 后台运行
nohup python run_full_collection.py > collection.log 2>&1 &

# 查看日志
tail -f collection.log

# 查看进程
ps aux | grep python
```

### 2. 断点续传

如果采集中途被打断：

```bash
# 直接重新运行即可，会自动跳过已采集的数据
python collect_market_data_optimized.py --days 60
python collect_intraday_data_optimized.py --days 60
```

### 3. 强制重新采集

```bash
# 强制重新采集所有数据（不跳过已存在的）
python collect_market_data_optimized.py --days 60 --force
python collect_intraday_data_optimized.py --days 60 --force
```

### 4. 查看日志

```bash
# 查看最新日志
tail -f logs/market_collector_20260301.log
tail -f logs/intraday_collector_20260301.log

# 查看所有日志文件
ls -lh logs/
```

---

## 📊 数据验证

### 1. 检查股票池

```bash
# 通过 API 查询股票池
curl http://localhost:8000/api/stocks | jq
```

### 2. 检查市场数据

```bash
# 查询指定日期的市场数据
curl "http://localhost:8000/api/market/sentiment?date=2026-02-28" | jq
```

### 3. 检查分时数据

```bash
# 查询某只股票的分时数据
curl "http://localhost:8000/api/stocks/intraday/000001/2026-02-28" | jq
```

---

## ⚠️ 注意事项

### 1. API 限流

- **Tushare API 限制**：200 次/分钟
- **脚本保守设置**：180 次/分钟（留有余量）
- **建议**：不要在同一个 IP 上并发运行多个采集脚本

### 2. 数据采集时间

- **市场数据**：每个交易日约 595 只股票 × 1 次 API 调用 = 595 次
- **分时数据**：每个交易日约 595 只股票 × 1 次 API 调用 = 595 次
- **60 个交易日预计耗时**：
  - 市场数据：约 30-40 分钟
  - 分时数据：约 60-80 分钟（分时数据 API 调用更频繁）

### 3. 网络稳定性

- **建议**：在网络稳定的环境下运行
- **断点续传**：支持中断后继续采集
- **失败重试**：单个 API 调用失败会自动重试

### 4. 磁盘空间

- **市场数据**：约 10-20 MB/天
- **分时数据**：约 50-100 MB/天
- **60 天数据**：约 4-7 GB

---

## 🐛 故障排查

### 问题 1: API 调用失败

```
❌ API 请求失败：429 Too Many Requests
```

**解决方案**：
- 等待几分钟后继续
- 调低限流值（修改 RateLimiter 参数）

### 问题 2: 股票池为空

```
❌ 股票池为空，请先导入股票
```

**解决方案**：
```bash
python import_stock_pool.py
```

### 问题 3: 数据库连接失败

```
❌ 数据库连接失败
```

**解决方案**：
- 确保后端服务已启动：`./start.sh`
- 检查配置文件中的数据库路径

---

## 📝 最佳实践

### 1. 每日定时采集

创建 cron 任务（Linux/Mac）：

```bash
# 编辑 crontab
crontab -e

# 添加每日收盘后采集（工作日 15:30）
30 15 * * 1-5 cd /path/to/stock/skills/dragon-stock-trading/scripts && \
    python collect_market_data_optimized.py --days 1 >> logs/daily_collection.log 2>&1
```

### 2. 每周完整采集

```bash
# 每周日凌晨 2 点采集最近 7 天数据
0 2 * * 0 cd /path/to/stock/skills/dragon-stock-trading/scripts && \
    python run_full_collection.py --days 7 >> logs/weekly_collection.log 2>&1
```

### 3. 监控采集状态

```bash
# 创建监控脚本 check_collection.sh
#!/bin/bash
LOG_FILE="logs/market_collector_$(date +%Y%m%d).log"
if [ ! -f "$LOG_FILE" ]; then
    echo "❌ 今日未采集"
    exit 1
fi

if grep -q "✅ 采集完成" "$LOG_FILE"; then
    echo "✅ 今日采集成功"
    exit 0
else
    echo "❌ 今日采集失败"
    exit 1
fi

# 使用
chmod +x check_collection.sh
./check_collection.sh
```

---

## 📞 技术支持

如有问题，请查看：
1. 日志文件：`logs/` 目录
2. 后端文档：`backend/README.md`
3. SKILL 文档：`SKILL.md`

---

## 🎯 总结

### 使用流程

```
1. 首次使用：
   python run_full_collection.py

2. 日常维护：
   python collect_market_data_optimized.py --days 1
   python collect_intraday_data_optimized.py --days 1

3. 数据验证：
   curl http://localhost:8000/api/stocks | jq
```

### 核心优势

✅ **自动化** - 一键完成所有数据采集  
✅ **智能化** - 自动跳过已采集数据  
✅ **稳定化** - 失败重试、限流保护  
✅ **可视化** - 详细日志、进度显示  
✅ **灵活化** - 支持多种参数配置  

祝你使用愉快！🎉
