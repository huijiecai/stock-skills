# ADR-0006: 版本史粒度=全量 payload

- 状态:已接受
- 日期:2026-08-19(早期设计讨论定案,原始"附录 4"记录未归档,以本文为准)
- 相关代码:`trader/core/documents.py::_init_versions`

## 背景

documents/watchlist 等对象的变更史怎么记?选项:①只记 diff(省空间,重建麻烦);
②记全量 payload 快照(费空间,任一版本直接可读);③只记操作日志无内容(无法回滚)。

## 决定

versions 表每次写操作落一条**全量 payload**(原"附录 4 已定"):subject_type +
subject_id + action + payload(JSONB)。当前 subject_type 为 document/watchlist,
将来任何要留痕的对象都往这里追加,不再单建历史表。

## 后果

- 正:历史任一版本零计算直读,回滚/对比/审计都简单;新对象接入只需定
  subject_type。
- 负:高频写对象(如 watchlist 微调)会产生大量冗余行——知识对象低频,
  可接受;若将来高频对象接入需重新评估。
- 约束:payload 必须含恢复所需的完整状态,不能只记"用户看到的部分字段"。
