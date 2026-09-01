# ADR-0014: 响应模型的精度分层

- 状态:已接受
- 日期:2026-08-25(T2.1 落地)
- 相关代码:`trader/api/schemas.py`、`trader/api/envelope.py`

## 背景

T2.1 给全部 46 个端点加 `response_model=Envelope[XxxOut]`,为 T2.2 从
OpenAPI 生成前端类型打地基。建模时面对一个矛盾:

- **求精确**:把 store 层 `SELECT` 的列清单逐字段复制进模型。core 加一列,
  模型忘改 → response_model 静默过滤掉新列 → 前端拿不到新字段,且无报错,
  排查困难。
- **求宽松**:全部 `dict` 透传,OpenAPI 退化成无结构的 object,T2.2 生成的前端
  类型全是 `Record<string, unknown>`,契约打通失去意义。

两端都不可接受,需要按"结构稳定性"分层。

## 决定

按响应结构的来源分三层建模(基座 `Row` = `extra="allow"`):

1. **手拼小结构逐字段精确**:操作回执(OkOut/StopOut/SealOut)、对话、工具试运行
   等,键就在端点代码里写死,精确建模,不加 extra 键。
2. **store 表行:核心字段 + extra 透传**:声明 id/slug/status 等稳定核心字段
   (有类型、进 OpenAPI),其余列靠 `extra="allow"` 原样透传。core 加列即 API
   可见,消灭"忘改模型静默丢字段"的坑;代价是 OpenAPI 只精确到核心字段。
3. **组装结构顶层精确、内层透传**:rounds/live/curve 等拼装响应,顶层键
   (rounds/points/steps)精确建模,内层"可有可无键"(如 RoundBrief 的
   time/summary/in_progress 视场次类型出现)用 extra 透传——把可有可无键写成
   必填会让序列化补默认值,改变响应形状。

信封配套:端点返回 `Envelope(data=...)`,traceId 留空;中间件识别"已是信封"
(同时有 data/status 键)就只补 traceId,不再二次包装,端点零样板。

## 后果

- 正:OpenAPI 46 个 200 响应全部指向具体模型(114 个组件),T2.2 可生成有结构
  的前端类型;core 表加列零 API 改动即可达前端;响应形状与裸 dict 时代完全
  一致(pytest 114 passed 验证)。
- 负:表行模型的类型保证只到核心字段,extra 透传的列前端类型里是
  `unknown`(T2.2 生成后体现);新增端点需按三层归类,多一步判断。
- 已知边界(T2.3 验收实测):透传层使生成类型带 `[key: string]: unknown`
  索引签名,核心字段改名时旧访问点落到索引签名返回 unknown——"当具体类型
  用"的点(渲染 ReactNode/赋值)被 tsc 捕获,但 `r.status === 'x'` 这类比较点
  静默通过(unknown 与 string 可比较)。改名核心字段的完整影响面 = tsc 报错
  ∪ grep 字段名,改名时需两者并用。这是“后端加列前端零等待”换来的静态
  检测削弱;若未来要严格化,可在 export_openapi 后处理中剥掉模型顶层的
  additionalProperties,代价是访问透传列必须先回后端建模。
