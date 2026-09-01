# ADR-0013: 诊断日志与 CLI 界面的分界

- 状态:已接受
- 日期:2026-08-24(T1.4 落地)
- 相关代码:`trader/core/log.py`、`trader/core/engine.py`、`trader/api/envelope.py`

## 背景

T1.4 引入 `logging` 统一替换散落各处的 print。盘点 engine/runner/prompts 的
print 后发现它们其实是两类东西,不能一刀切:

- **诊断**:系统在做什么/出了什么状况(重试、封场、停止请求、午休、接续场次)。
  读者是运维/排障的人,需要级别、时间戳、上下文字段(run/round/trace)。
- **界面**:用户要的内容本身(AI 每轮的分析输出 `result.output`、轮次分隔横幅、
  runner 的场次/组合列表、prompts diff)。读者是使用 CLI 的人,输出格式即产品,
  还有测试(`test_prompt_versions.py` 用 capsys)直接断言这些内容。

若把界面也塞进 logging,会被时间戳/级别/上下文字段污染,且现有 capsys 测试
断言的纯净输出全废。

## 决定

双通道并存,判定标准一句话:**输出本身是用户要的数据 → print;输出是系统运行
状态 → logging。**

- 诊断走 `core/log.py` 的统一 logger,自动带 `run=/r/trace=` 上下文字段;
  只输出控制台,不写日志文件(项目规约)。
- 界面保持 print:engine 的 AI 轮输出与分隔横幅、runner 列表、prompts diff。
- API 侧信封中间件生成 traceId 时调 `set_trace_id`,让该请求期间所有日志与
  响应信封/X-Trace-Id 头同值,可对账。
- 实现要点:handler 用每次写入动态取 `sys.stderr` 的 `_CurrentStderrHandler`。
  标准 StreamHandler 创建时固化 stderr 对象,pytest 在测试间关闭/替换捕获对象
  后,写入已关闭流会触发 logging 的 handleError,把 `Message: '...'` 形态的
  原始消息混进新 stderr——丢格式且污染输出。

## 后果

- 正:诊断有级别(TRADER_LOG_LEVEL)与上下文字段,排障可按 run/round/trace
  过滤;界面输出不受日志配置影响,capsys 测试继续有效。
- 负:同一次运行两种通道并存,新增输出时需按判定标准归类;终端上两通道
  (stderr 诊断/stdout 界面)交错,不保证严格时序。
