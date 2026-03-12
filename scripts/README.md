# Tushare Token 配置说明

## 方法1: 获取并配置Tushare Token（推荐）

1. 访问 https://tushare.pro/register 注册账号（免费）
2. 登录后在个人主页获取你的token
3. 创建配置文件：

```bash
echo "你的token" > ~/.tushare_token
```

## 方法2: 使用AKShare（免费，无需token）

运行备用脚本：

```bash
python3 scripts/fetch_stock_data_akshare.py
```

AKShare优点：
- 完全免费
- 无需注册
- 无需token
- 数据来源：东方财富、新浪财经等

## 运行脚本

配置好后运行：

```bash
cd /Users/huijiecai/Project/stock
python3 scripts/fetch_stock_data.py
```

输出文件：
- `stock_data_YYYYMMDD_HHMMSS.csv` - CSV格式
- `stock_data_YYYYMMDD_HHMMSS.json` - JSON格式  
- `stock_data_YYYYMMDD_HHMMSS.md` - Markdown报告（含估值分级）
