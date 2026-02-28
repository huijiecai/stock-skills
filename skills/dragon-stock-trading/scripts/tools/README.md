# 数据采集工具

这些是用于批量采集股票数据的命令行工具。

## 📦 工具列表

| 工具 | 功能 |
|------|------|
| `import_stock_pool.py` | 从概念股票池文档导入股票到后端 |
| `collect_market_data.py` | 采集市场数据（支持日期范围、断点续传） |
| `collect_intraday_data.py` | 采集分时数据（支持日期范围、增量采集） |
| `run_full_collection.py` | 一键执行所有任务 |

## 🚀 快速开始

```bash
# 完整执行（推荐）
python run_full_collection.py

# 分步执行
python import_stock_pool.py                    # Step 1: 导入股票池
python collect_market_data.py --days 60        # Step 2: 采集市场数据
python collect_intraday_data.py --days 60      # Step 3: 采集分时数据
```

## 📖 详细文档

详见上级目录的 `README_DATA_COLLECTION.md` 和 `QUICK_REFERENCE.md`
