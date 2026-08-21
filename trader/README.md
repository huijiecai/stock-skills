# Trading V2

从零构建的 A 股看盘交易 agent(PydanticAI + DeepSeek),完整迁移了 skills/trading-system 的方法论:预期管理——预期库是真相源,买入前提是"研究过",卖出对照"兑现/失效标志",所有判断靠 AI(工具只提供数据)。

## 一天三步(完整闭环)

```bash
cd trader
uv run python -m trader.runner premarket 20260817   # ① 盘前:八维催化→预期更新→场景推演→预案落库
uv run python -m trader.runner live                 # ② 盘中:实时看盘(--sleep 300 每5分钟一轮,Ctrl+C 停)
uv run python -m trader.runner close 20260817       # ③ 盘后:预期更新→逐股扫描→复盘→合规自检

# 其他:
uv run python -m trader.runner replay 20260812 --interval 20  # 模拟看盘(回放,自动重置账户+清旧轮日志)
uv run python -m trader.runner replay 20260812 --resume       # 接续上次回放(不清不重置,从最大轮号继续)
uv run python -m trader.runner research "光纤涨价"            # 预期研究(新建/更新自动判断)
```

场次、轮次思考流、交易留痕、文档和 Prompt 版本统一在 Web 工作台查看。

## 断点接续(8/17 起)

看盘记忆 = documents 里的轮日志(`watch_live`/`watch_replay`,name=rN),不依赖进程:
- live 每轮结束必写轮日志(市况/持仓评估/行动/**自设条件与待办**),随时 Ctrl+C
- 重启 `live` 自动从当天最大轮号接着编号,AI 开场读最近 3 轮恢复盘感与待办
- 午休(11:30-13:00)自动跳过;15:05 后自动收工,不再空转
- 看当天全程:`sqlite3 data/account.db "SELECT content FROM documents WHERE doc_type='watch_live' AND trade_date='20260817' ORDER BY CAST(substr(name,2) AS INTEGER);"`

## live 守护(脱离终端跑法)

```bash
cd trader && mkdir -p logs && uv run python - << 'EOF'
import subprocess
cmd = '''echo $$ > logs/live.pid
while [ "$(date +%H%M)" -lt 1505 ]; do
  PYTHONUNBUFFERED=1 env -u ANTHROPIC_API_KEY uv run python -m trader.runner live --sleep 300
  echo "[watchdog] respawn $(date +%H:%M:%S)"; sleep 10
done'''
subprocess.Popen(['bash','-c',cmd], stdout=open('logs/live_$(date +%Y%m%d).log','ab'),
                 stderr=subprocess.STDOUT, start_new_session=True)
EOF
# 停止:kill $(cat logs/live.pid) 及 ps 里的 trader.runner live 进程(用 PID 文件,别 grep 猜)
```

## 目录结构(平台化 v2,详见 docs/实现设计.md)

```
trader/
├── trader/
│   ├── core/                ← 平台:不知道任何方法论(验收=无"预期"业务概念)
│   │   ├── market.py        ← 行情 9 工具(live/replay 双模 + time 截断防未来)
│   │   ├── ledger.py        ← 钱包(分计价/T+1/fills 留痕)——行级 portfolio_id 隔离
│   │   ├── documents.py     ← 万物记忆(meta + versions 统一版本史)
│   │   ├── watchlist.py     ← 自选组(唯一结构化原语,as_of 历史重建)
│   │   ├── systems.py       ← 交易系统注册表(manifest 纯数据;换系统=换一行)
│   │   ├── engine.py        ← 引擎:读 manifest 装配 agent,驱动 single/loop 阶段
│   │   ├── portfolios.py    ← 组合登记+实验开局三模式(fresh/fork-as-of/custom)+ 指纹
│   │   ├── runs.py          ← 场次登记(封面=prompt 版本+指纹+metrics;clock/portfolio 归属)
│   │   ├── scan.py          ← scan_market 快扫(含【自选组快览】)
│   │   └── registry.py      ← 能力注册表(工具名 → 实现)
│   ├── runner.py            ← CLI 薄壳:五命令=expectation 别名;通用 run <system> <stage>
│   └── tools/               ← 通用工具实现(account/trading/docs;market/watch 为垫片)
├── tests/                   ← 54 passed + 10 盘中专用自动跳过
├── scripts/migrate_to_platform.py  ← 老预期库→文档+自选组 一次性迁移(已执行)
└── .env                     ← 配置(LLM_API_KEY / LLM_MODEL / LLM_BASE_URL)
```

交易系统的原始方法论保存在仓库根目录 `skills/trading-system/`；平台中的 Prompt 由 Web 编辑并在 PG 中版本化。

**核心约定**:预期=文档(doc_type='expectation',meta 存 stage/status),池=自选组(fields.role 分级);
一切管理在 PG(单库行级多租户:实盘=portfolio 0,一场实验=一个实验组合)。

## 全库关系速查:两个世界,一座桥(P0 迁移目标形态)

> 忘了表关系看这张图。详细字段见 [docs/工作台架构.md](docs/工作台架构.md) §8;现状→目标的迁移清单见其 §6。

```
定义世界(是什么)               核算世界(钱和知识在哪)
┌──────────────────┐         ┌────────────────────────┐
│ systems 打法      │         │ portfolios 组合          │
│   ├ prompts 指令   │         │   ├ wallets    现金      │
│   │   └ prompt_versions│    │   ├ positions  持仓      │
│   │                │         │   ├ documents 知识/产出  │
│   └ doc_classes    │         │   ├ watchlists + members│
│                    │         │   └ versions   版本史    │
└─────────┬──────────┘         └───────────┬────────────┘
          │                                │
          └───────────┐      ┌─────────────┘
                      ▼      ▼
   users ──(执行者)──► ┌──────────┐     ┌───────────────┐
                      │  runs    │────►│ run_events    │ 过程:轮/工具事件
   唯一同时连两个世界  │ 一座桥    │────►│ run_documents │ 这场读了/写了哪些文档 ──► documents
                      └────┬─────┘     └───────────────┘
                           │
                           └──► fills 成交(唯一双归属的明细):
                                 portfolio_id 记在哪个组合的账上(必填,主人是组合)
                                 run_id        是哪场下的单(可空,行为归因)
```

三条规则:
1. **runs 是唯一同时连两个世界的表**——发起一次执行 = 在桥上落一行(system_id + portfolio_id + clock)
2. **每个枢纽只挂一种东西**:指令挂 systems;钱和知识挂 portfolios;过程记录挂 runs
3. **fills 双归属**:钱按组合算(portfolio_id),行为按场次算(run_id)——出入金/期初等非执行流水没有 run_id 也成立

users 出现三次:系统归属 / 组合主人 / 执行者(三个独立事实)。

## 常用查看命令

```bash
uv run python -m trader.tools list                                  # 全部工具+签名
uv run python -m trader.tools call get_positions                    # 持仓
uv run python -m trader.tools call get_trades                       # 成交+每笔决策留痕
uv run python -m trader.tools call list_docs doc_type=expectation   # 预期库(=文档集)
uv run python -m trader.tools call get_watchlist name=存储芯片-AI+供需错配驱动存储涨价   # 池(自选组)
uv run python -m trader.tools call get_watchlist_quotes name=存储芯片-AI+供需错配驱动存储涨价 mode=replay date=20260818
uv run python -m trader.tools call list_docs                        # 文档库(盘前/收盘报告)
uv run python -m trader.tools call get_doc doc_type=close trade_date=20260818
# 参数格式:key=value 空格分隔,逗号=列表(codes=000021,000636)
```

## 环境

- **.env**:`cp .env.example .env` 后填 DeepSeek key(联网搜索复用同一 key)
- **ClickHouse**:Docker 里 `astock-clickhouse` 容器,跑之前确认 healthy(否则 replay/query 类会失败)
- **PostgreSQL**:Docker 里 `stock_postgres` 容器(5432,库 `trader`,postgres/password)——trader 的主存储
  (账户/预期/文档/思考流;回放隔离用 PG schema `replay_{date}`)。连接串可用环境变量 `DATABASE_URL` 覆盖;
  旧 SQLite(data/account.db)为 8/18 前的只读存档,迁移脚本 scripts/migrate_sqlite_to_pg.py
- live 类命令(板块排名/异动榜/成交)盘中专用,盘后自动拒绝并提示用 replay
- 回放 = 独立实验(自动重置账户);收盘统计类工具带"未来数据"警示防回放泄漏

## 测试三层

| 层 | 命令 | 成本 | 用途 |
|---|---|---|---|
| 单工具 | `python -m trader.tools call ...` | 免费 | 开发调试 |
| 回归 | `pytest`(见下) | 免费 | 改动后护栏 |
| 端到端 | `runner` 各命令 | 花 token | 完整流程验证 |

## 跑测试

```bash
uv run pytest -v                                # 全部用例(含盘中专用自动跳过项)
uv run pytest tests/test_api.py -v              # 单个文件
uv run pytest tests/test_api.py::test_auth_flow -v   # 单个用例
uv run pytest -v --lf                           # 只跑上次失败的
uv run pytest -v --tb=long                      # 失败时输出完整堆栈
```

- 用 `uv run` 自动走 `.venv`,无需手动安装依赖(dev 组已含 pytest)
- API 层测试(如 test_api.py)走 FastAPI TestClient,不经网络、不需要起服务
- 盘中专用用例会在盘后自动跳过(`-v` 里显示 `SKIPPED`),属预期行为
