# Trading V2

从零开始的 AI 交易 agent,一步步构建。每一步你都能读懂每一行。

## 目录结构

```
trading_v2/
├── trader/             ← 包(源码的家)
│   ├── __init__.py     ← 包标记(空文件,有了它才能 import)
│   ├── config.py       ← 配置出口:key 从 .env 读,模型名/base_url 默认值
│   ├── agent.py        ← 大脑:建 Agent + 注册工具(不含业务逻辑)
│   ├── market.py       ← 看盘域:行情原子工具(get_quote / get_indices / get_quotes)
│   ├── trading.py      ← 交易域:账户/交易原子工具(trade / query_positions)
│   ├── watch.py        ← 组合工具:get_heartbeat / probe_pool / probe_stock(积木3-4 加)
│   └── main.py         ← 入口:建 Deps → 跑心跳循环(积木6 加)
├── .env                ← 敏感配置:API key(不进 git,自己填)
├── .env.example        ← .env 的模板(占位符,进 git)
├── demos/              ← PydanticAI 学习 demo(不进生产)
├── tests/              ← 测试
├── pyproject.toml      ← 项目配置(依赖、Python版本、包名)
├── uv.lock             ← 依赖锁定(自动生成,不用管)
├── README.md           ← 你在看的这个
└── TODO.md             ← 构建清单(积木,做完打钩)
```

### 分层原则

| 层 | 文件 | 干什么 | AI 能看到吗 |
|---|---|---|---|
| 原子工具 | market.py / trading.py | 一个函数查一类数据(报价/指数/持仓/下单) | 是(注册后) |
| 组合工具 | watch.py | 调原子工具,拼成决策视图(心跳/深析) | 是 |
| 大脑 | agent.py | 建模型 + 注册工具 + 组装 toolset | — |
| 入口 | main.py | 建运行环境 + 跑循环 | — |

- 文件怎么分 = 给人读的(能力域);toolset 怎么组装 = 给 AI 看的(积木8)
- 包内 `_` 前缀函数 = 底层实现,AI 看不到

## 怎么跑

```bash
cd trading_v2
cp .env.example .env   # 第一次:填入真实 API key
uv run python -m trader.agent
```

看到这个算成功:
```
AI: 深科技(000021) 现价39.55 涨跌-1.98%
```

### 配置分两类

- **敏感**(API key):放 `.env`,不进 git(根目录 .gitignore 已覆盖)
- **非敏感**(模型名 / base_url):`trader/config.py` 里的默认值,进 git
- 新配置统一加进 `config.py`,一处管理

## 构建进度

- [x] **积木1**:Agent + 1个工具(查股价)← 当前
- [ ] 积木2:get_indices(查指数)+ get_quotes(查多只股)
- [ ] 积木3:get_heartbeat(心跳:指数+持仓价+池健康度)
- [ ] 积木4:probe_pool + probe_stock(深析)
- [ ] 积木5:trade(下单 + T+1/整手/主板校验)
- [ ] 积木6:循环(每轮自动看盘 + message_history 记忆)
- [ ] 积木7:prompt.md(交易规则,外部文件)
- [ ] 积木8:toolset + filtered(14:50 后隐藏交易工具)

详细清单见 TODO.md。
