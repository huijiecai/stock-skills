# 获取股票真实财务数据 - 配置指南

## 📋 当前问题

之前文档中的财务数据（PE估值、市值等）部分来自网络搜索，存在以下问题：
- 数据来源不统一，准确性无法保证
- 部分数据严重偏差（如特变电工市值1591亿 vs 650亿）
- 无法实时更新

## ✅ 解决方案

已创建两个脚本来获取真实数据：

### 方案1：使用Tushare（推荐，数据最全）

**优点**：
- 数据质量高、更新及时
- 支持历史数据、财报数据
- API稳定

**配置步骤**：

1. 注册Tushare账号（免费）:
   - 访问 https://tushare.pro/register
   - 注册并登录
   - 在"个人中心"获取token

2. 配置token:
   ```bash
   echo "你的token" > ~/.tushare_token
   ```

3. 运行脚本:
   ```bash
   cd /Users/huijiecai/Project/stock
   python3 scripts/fetch_stock_data.py
   ```

### 方案2：使用AKShare（备用，免费无需注册）

**优点**：
- 完全免费，无需注册
- 无需token
- 数据来源：东方财富、新浪财经

**缺点**：
- 依赖较多，安装可能遇到问题
- API不如Tushare稳定

**安装依赖**：
```bash
pip3 install akshare py-mini-racer pandas tabulate
```

**运行脚本**：
```bash
cd /Users/huijiecai/Project/stock
python3 scripts/fetch_stock_data_akshare.py
```

## 📊 输出文件

脚本运行后会生成3个文件：

1. **CSV文件**: `stock_data_YYYYMMDD_HHMMSS.csv`
   - 可用Excel打开
   - 方便数据分析

2. **JSON文件**: `stock_data_YYYYMMDD_HHMMSS.json`
   - 可编程读取
   - 方便集成到系统

3. **Markdown报告**: `stock_data_YYYYMMDD_HHMMSS.md`
   - 包含估值分级（低/中/高估值区）
   - 包含统计信息
   - 可直接查看

## 🔄 如何更新文档

获取到真实数据后，按以下步骤更新投资文档：

1. 查看生成的Markdown报告：
   ```bash
   cat scripts/stock_data_*.md | tail -100
   ```

2. 手动更新文档中的关键数据：
   - PE估值
   - 市值
   - 股价
   - 估值分级建议

## ⚠️ 当前状态

- ✅ 已创建 `fetch_stock_data.py` (Tushare版本)
- ✅ 已创建 `fetch_stock_data_akshare.py` (AKShare版本)
- ⚠️ 需要配置Tushare token 或 安装AKShare依赖
- ⚠️ 文档中的数据仍为网络搜索数据，待更新

## 💡 建议

**最简单的方式**：
1. 花2分钟注册Tushare账号获取token
2. 配置token到 `~/.tushare_token`
3. 运行 `python3 scripts/fetch_stock_data.py`
4. 查看生成的Markdown报告
5. 根据真实数据更新投资文档

这样可以确保所有财务数据都是真实、准确、实时的！
