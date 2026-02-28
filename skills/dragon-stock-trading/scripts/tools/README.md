# 数据采集工具使用说明

## 📦 工具列表

| 工具 | 功能 | 使用场景 |
|------|------|---------|
| `import_stock_pool.py` | 从概念股票池文档导入股票到后端 | 首次初始化股票池 |
| `collect_market_data.py` | 采集市场数据（支持日期范围、断点续传） | 批量采集历史数据 |
| `collect_intraday_data.py` | 采集分时数据（支持日期范围、增量采集） | 批量采集历史分时数据 |
| `run_full_collection.py` | 一键执行所有任务 | 完整数据初始化 |

## 🚀 快速开始

### 1. 首次使用 - 完整数据初始化

```bash
cd skills/dragon-stock-trading/scripts/tools

# 一键执行：导入股票池 + 采集最近 60 天数据
python run_full_collection.py
```

### 2. 分步执行

```bash
# Step 1: 导入股票池（595 只股票）
python import_stock_pool.py

# Step 2: 采集最近 60 天市场数据
python collect_market_data.py --days 60

# Step 3: 采集最近 60 天分时数据
python collect_intraday_data.py --days 60
```

### 3. 采集指定日期的数据

```bash
# 采集某一天的市场数据
python run_full_collection.py --step market --start-date 2026-02-26 --end-date 2026-02-26

# 采集某一天的分时数据
python run_full_collection.py --step intraday --start-date 2026-02-26 --end-date 2026-02-26

# 采集某个日期范围的数据
python run_full_collection.py --step market --start-date 2026-02-20 --end-date 2026-02-26

# 或者直接使用独立脚本
python collect_market_data.py --start 2026-02-26 --end 2026-02-26
python collect_intraday_data.py --start 2026-02-26 --end 2026-02-26
```

### 4. 日常维护

```bash
# 采集今日市场数据
python collect_market_data.py --days 1

# 采集今日分时数据
python collect_intraday_data.py --days 1
```

## ⚙️ 常用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--days N` | 采集最近 N 天 | `--days 60` |
| `--start YYYY-MM-DD` | 开始日期 | `--start 2025-12-01` |
| `--end YYYY-MM-DD` | 结束日期 | `--end 2026-02-26` |
| `--force` | 强制重新采集 | `--force` |
| `--step STEP` | 执行步骤 | `--step market` |

## 🔍 后台运行（长时间执行）

```bash
# 后台执行
nohup python run_full_collection.py > collection.log 2>&1 &

# 查看进度
tail -f collection.log
```

## 📊 验证数据

```bash
# 检查股票池
curl http://localhost:8000/api/stocks | jq '.total'

# 检查市场数据
curl "http://localhost:8000/api/market/sentiment?date=2026-02-26" | jq

# 检查分时数据
curl "http://localhost:8000/api/stocks/intraday/000001/2026-02-26" | jq '.total'
```

## ⏱️ 预计耗时

| 任务 | 60 天预估 |
|------|---------|
| 导入股票池 | 2-5 分钟 |
| 市场数据 | 30-40 分钟 |
| 分时数据 | 60-80 分钟 |
| **总计** | **约 2-3 小时** |

## 💾 磁盘空间

| 数据类型 | 每天 | 60 天 |
|---------|------|------|
| 市场数据 | ~15 MB | ~900 MB |
| 分时数据 | ~75 MB | ~4.5 GB |
| **总计** | **~90 MB** | **~5.4 GB** |

## ⚠️ 注意事项

### 1. API 限流
- Tushare API 限制：200 次/分钟
- 脚本保守设置：180 次/分钟（留有余量）
- 不要并发运行多个采集脚本

### 2. 断点续传
如果采集中途被打断，直接重新运行即可，会自动跳过已采集的数据。

### 3. 网络稳定性
建议在网络稳定的环境下运行，单个 API 调用失败会自动重试。

## 🐛 故障排查

| 问题 | 解决方案 |
|------|---------|
| 股票池为空 | `python import_stock_pool.py` |
| API 限流 (429) | 等待几分钟，或调低限流值 |
| 采集中断 | 直接重新运行（支持断点续传） |
| 数据库连接失败 | 确保后端服务已启动 (`./start.sh`) |

## 📝 日志位置

```bash
# 查看最新日志
ls -lth ../../logs/ | head

# 实时查看
tail -f ../../logs/market_collector_$(date +%Y%m%d).log
tail -f ../../logs/intraday_collector_$(date +%Y%m%d).log
```

## ✅ 执行前检查清单

- [ ] 后端服务已启动 (`./start.sh`)
- [ ] 配置文件正确 (`config.yaml`)
- [ ] 网络稳定
- [ ] 磁盘空间充足（至少 6 GB）
- [ ] Python 环境正常

---

**祝你使用愉快！** 🎉
