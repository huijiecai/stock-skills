# 数据采集 - 快速参考卡片

## 🚀 一键执行（推荐）

```bash
cd skills/dragon-stock-trading/scripts/tools

# 完整执行：导入股票池 + 采集最近 60 天数据
./quick_start.sh

# 或
python run_full_collection.py
```

---

## 📋 分步执行

### Step 1: 导入股票池
```bash
python import_stock_pool.py
```

### Step 2: 采集市场数据
```bash
# 最近 60 天
python collect_market_data.py --days 60

# 指定日期范围
python collect_market_data.py \
  --start 2025-12-01 --end 2026-02-28
```

### Step 3: 采集分时数据
```bash
# 最近 60 天
python collect_intraday_data.py --days 60

# 指定日期范围
python collect_intraday_data.py \
  --start 2025-12-01 --end 2026-02-28
```

---

## ⚙️ 常用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--days N` | 采集最近 N 天 | `--days 60` |
| `--start YYYY-MM-DD` | 开始日期 | `--start 2025-12-01` |
| `--end YYYY-MM-DD` | 结束日期 | `--end 2026-02-28` |
| `--force` | 强制重新采集 | `--force` |
| `--step STEP` | 执行步骤 | `--step market` |

---

## 🔍 后台运行

```bash
# 后台执行
nohup python run_full_collection.py > collection.log 2>&1 &

# 查看进度
tail -f collection.log

# 查看进程
ps aux | grep python
```

---

## 📊 验证数据

```bash
# 检查股票池
curl http://localhost:8000/api/stocks | jq '.total'

# 检查市场数据
curl "http://localhost:8000/api/market/sentiment?date=2026-02-28" | jq

# 检查分时数据
curl "http://localhost:8000/api/stocks/intraday/000001/2026-02-28" | jq '.total'
```

---

## 🐛 故障排查

| 问题 | 解决方案 |
|------|---------|
| 股票池为空 | `python import_stock_pool.py` |
| API 限流 (429) | 等待几分钟，或调低限流值 |
| 采集中断 | 直接重新运行（支持断点续传） |
| 日志过大 | `rm logs/*.log` |

---

## 📝 日志位置

```bash
# 查看最新日志
ls -lth logs/ | head

# 实时查看
tail -f logs/market_collector_$(date +%Y%m%d).log
tail -f logs/intraday_collector_$(date +%Y%m%d).log
```

---

## ⏱️ 预计耗时

| 任务 | 60 天预估 |
|------|---------|
| 导入股票池 | 2-5 分钟 |
| 市场数据 | 30-40 分钟 |
| 分时数据 | 60-80 分钟 |
| **总计** | **约 2-3 小时** |

---

## 💾 磁盘空间

| 数据类型 | 每天 | 60 天 |
|---------|------|------|
| 市场数据 | ~15 MB | ~900 MB |
| 分时数据 | ~75 MB | ~4.5 GB |
| **总计** | **~90 MB** | **~5.4 GB** |

---

## 📞 帮助

```bash
# 查看帮助
python run_full_collection.py --help

# 查看详细文档
cat README_DATA_COLLECTION.md
```

---

## ✅ 检查清单

执行前确认：
- [ ] 后端服务已启动 (`./start.sh`)
- [ ] 配置文件正确 (`config.yaml`)
- [ ] 网络稳定
- [ ] 磁盘空间充足（至少 6 GB）
- [ ] Python 环境正常

---

**祝你使用愉快！** 🎉
