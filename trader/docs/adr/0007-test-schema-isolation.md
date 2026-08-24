# ADR-0007: 测试默认 schema 重定向 + 系统注册真幂等

- 状态:已接受
- 日期:2026-08-24(测试污染事故日)
- 相关代码:`trader/core/db.py::_resolve`、`tests/conftest.py`、`trader/core/systems.py::ensure_expectation_system`

## 背景

测试与生产共用 PG 库,靠 schema 隔离:生产在 public,测试用 `t_*` schema。但 store
默认参数是 `schema="public"`,**忘记传隔离 schema 的测试会直写生产**。
2026-08-24 双重事故:
1. test_watchlist 调用 `ensure_expectation_system()` 未传 schema,直写 public;
2. 该函数假幂等(每次 upsert 覆盖 manifest),把用户当天 14:22 自建的
   "个股分析"阶段从 expectation manifest 冲成默认五阶段。systems 表也积了
   300+ 行测试垃圾。

## 决定

双保险,两层各自独立有效:

1. **TRADER_SCHEMA 环境变量重定向**(db.py `_resolve`):只把默认 "public" 重定向
   到指定 schema,显式传入的 `t_*` 等原样通过。conftest.py 在任何 trader import
   之前设 `TRADER_SCHEMA=t_api`;`t_api` 本身匹配会话开始的 `t_%` 清理规则,
   自清洁。9 个 store 签名零改动。
2. **ensure_expectation_system 改真幂等**:已存在直接返回,绝不 upsert 覆盖
   用户编辑过的 manifest。

## 后果

- 正:测试再忘记传 schema,数据也落 t_api 而非 public;即便将来有新代码直写
  默认 schema,生产也不受影响。已验证:两轮全量 pytest 后 public.systems 行数
  与 expectation manifest 纹丝不动。
- 负:`TRADER_SCHEMA` 是隐性全局开关——生产环境误设会把默认读写全部重定向,
  故必须只在测试入口(conftest)设置,且用 setdefault 允许显式覆盖。
- 约束:`_resolve` 只重定向 "public" 这一个值,不能扩大范围(显式 schema 是
  调用方的明确意图,重定向即违背)。
