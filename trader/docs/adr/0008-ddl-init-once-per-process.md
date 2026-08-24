# ADR-0008: DDL 初始化进程内只跑一次

- 状态:已接受
- 日期:2026-08-19(死锁实测日)
- 相关代码:`trader/core/db.py::ensure_once`

## 背景

各 store 的 `_init_db`(CREATE TABLE IF NOT EXISTS 等 DDL)原先每次建连接都可能
执行。8/19 实测:并发写场景下多条连接同时跑 DDL,抢 PG 的 AccessExclusiveLock
造成死锁,两次都靠重试自愈——多用户/多并发下这是定时炸弹。

## 决定

DDL 幂等初始化**进程内只执行一次**:`ensure_once(key, init_fn)`,
key=存储类:schema,用可重入锁(RLock)保护——可重入是因为 _init_db 内部可能
再建子表(如 Ledgers→Bags),普通锁会自锁。

## 后果

- 正:并发下 DDL 只由一个线程执行一次,死锁根除;建表成本从每连接一次降为
  每进程一次。
- 负:进程内建过表后,外部 drop 了 schema/表不会再自动重建(需重启进程)——
  测试会话开头的 `t_*` 清理正是靠"每次会话新进程"天然规避。
- 演进:DDL 仍原地保留在各 store 的 `_init_db`(为 T4.3 Alembic 接管做准备,
  接管后本机制退役)。
