# iTick API 配置说明

## 获取API密钥

1. 访问 [iTick官网](https://www.itick.org/) 注册账号
2. 登录后进入开发者中心获取API密钥
3. iTick提供免费套餐，适合个人开发者使用

## 配置环境变量

### macOS/Linux:
```bash
export ITICK_API_KEY="your_api_key_here"
```

### Windows:
```cmd
set ITICK_API_KEY=your_api_key_here
```

### 永久配置（推荐）:

在 `~/.zshrc` 或 `~/.bashrc` 中添加：
```bash
export ITICK_API_KEY="your_api_key_here"
```

然后执行：
```bash
source ~/.zshrc
```

## 测试API连接

```bash
python3 .qoder/skills/dragon-stock-trading/scripts/stock_fetcher.py "工业富联"
```

配置成功后会显示：
```
🔍 工业富联 (601138) 基本信息

📡 实时数据 (来自itick API)
📈 最新价格：XX.XX元 (+X.XX%)
...
```

未配置时会显示模拟数据并提示：
```
⚠️ 未配置ITICK_API_KEY环境变量，显示的是模拟数据。请注册itick获取API密钥以获取实时数据。
```

## 支持的股票

目前已支持以下主要A股：
- 宁德时代、比亚迪、贵州茅台、五粮液
- 东方财富、隆基绿能、阳光电源、迈瑞医疗
- 药明康德、爱尔眼科、工业富联、立讯精密
- 歌尔股份、京东方、海康威视

如需添加更多股票，请修改 `stock_fetcher.py` 中的 `stock_mapping` 字典。