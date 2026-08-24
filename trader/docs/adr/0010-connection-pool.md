# ADR-0010: 数据访问层连接池化

- 状态:已接受
- 日期:2026-08-24(T1.2 落地)
- 相关代码:`trader/core/db.py`

## 背景

原 `_connect()` 每次调用新建一条 PG 连接(TCP+认证握手),用完即关。CLI 低频
场景无所谓,但 API 服务化后每个请求多次进出让连接开销成为主延迟来源,且并发
上限受 PG max_connections 直接限制。

## 决定

引入 `psycopg_pool`,进程级单例连接池(min 1/max 8,`TRADER_DB_POOL_MAX` 可调),
`_connect()` 改为从池借出/归还:

- 事务语义逐字保留:`pool.connection()` 内嵌 `with conn`,无异常提交/异常回滚;
- `search_path` 每次借用重设——池连接跨 schema 复用,SET 提交后留存于连接上,
  不重设会串 schema;
- `check_connection` 借用前探活,坏连接自动弃换(防 DB 重启后拿死连接);
- `atexit` 显式关池——否则池对象靠 `__del__` 兜底,解释器线程设施半拆除时
  调度线程停不掉,一次性脚本退出白出一行警告。

## 后果

- 正:请求不再付建连成本;并发连接数有上限保护;语义与原实现完全一致,
  101 条测试零改动通过。
- 负:引入进程级状态(池),测试fork/多进程场景每进程一池(当前用不到);
  连接上的 session 级状态(GUC 等)不再可靠——这正是 search_path 每次重设
  的原因,将来任何 session 级设置都必须进 `_connect` 的借用流程。
