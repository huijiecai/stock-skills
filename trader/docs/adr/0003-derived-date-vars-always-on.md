# ADR-0003: 派生日期变量不依赖 manifest 声明

- 状态:已接受
- 日期:2026-08-24(盘前事故日)
- 相关代码:`trader/core/engine.py::_stage_vars/stage_var_schema`

## 背景

阶段 prompt 支持 `{date}/{prev}/{weekday}/{gap}` 占位符。prev/weekday/gap 是由 date
推算的**派生三件套**。原先是否注入这些变量看 manifest 阶段定义的 `vars` 声明。
2026-08-24 盘前事故:用户在契约编辑器保存阶段时 `vars` 字段被丢掉,prompt 里的
`{prev}` 失去注入,format 直接抛 KeyError,整个盘前阶段加载失败。

## 决定

只要有 `date`,派生三件套(prev/weekday/gap)**一律自动推算注入,不看 manifest
声明**。多余变量对 `str.format` 无害;变量契约面板(`stage_var_schema`)与运行时
(`_stage_vars`)走同一规则,标注 source=auto。

## 后果

- 正:契约编辑器丢字段这类 UI 层失误不再能打断引擎;运行时与编辑器预览天然一致。
- 负:prompt 里写 `{prev}` 但调用方没给 date 时仍会 KeyError——这是合理的快速
  失败(缺核心变量不该静默跑)。
- 约束:新增派生变量必须同时加进 `_stage_vars` 与 `stage_var_schema`,两者同源
  是本 ADR 的核心约束,违背它编辑器预览就会说谎。
