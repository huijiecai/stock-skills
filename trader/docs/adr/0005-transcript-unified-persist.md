# ADR-0005: 思考流统一落库

- 状态:已接受
- 日期:2026-08-19(早期设计讨论定案,原始"附录 12"记录未归档,以本文为准)
- 相关代码:`trader/core/engine.py::_save_transcript`

## 背景

AI 每轮对话的完整消息史(思考流)要不要落库、怎么命名?选项:①只落 loop 阶段,
single 阶段不留;②按阶段各自设计存储格式;③统一落 documents 表。思考流是复盘与
"继续讨论"功能的唯一数据源,不留则运行结束即失忆;分别设计格式则查询侧要写
多套适配。

## 决定

思考流**统一落 documents 表**(原"附录 12 已定"):doc_type=`transcript_{stage}`,
loop 阶段轮次名 `rN`,single 阶段 name='';payload 含轮次/时点/token 用量与完整
messages(JSON)。

## 后果

- 正:任何阶段运行后都可回放对话、继续讨论;"继续讨论"功能直接读冻结的
  transcript + 冻结版 prompt 恢复现场(见 test_run_discussion 测试)。
- 负:documents 表体量随场次线性增长,长 loop 每场几十条;目前没有清理策略,
  量大了需要归档/淘汰机制(现阶段可接受,单条约几十 KB)。
- 约束:transcript 是"继续讨论"的唯一现场,删除/覆盖文档即破坏该功能。
