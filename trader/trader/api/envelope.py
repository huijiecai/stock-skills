"""api·标准响应包:一切 JSON 响应统一为 {data, status, message?, traceId}。

中间件实现——不改端点代码,自动包裹:
- 成功:{"data": <原始返回>, "status": "SUCCESS", "traceId": "xxx"}
- 失败:{"data": null, "status": "ERROR", "message": "...", "traceId": "xxx"}
- HTTP 状态码语义不变(200/401/403/404/409...)
- traceId 同时写入响应头 X-Trace-Id(日志/前端报障对账用)

前端 client.ts 的 api() 会自动解包 data 字段,业务代码无感。
"""
import json
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from trader.core.log import get_logger, set_trace_id

log = get_logger("api")

# 这些路径不走信封(静态文件/健康检查/Swagger)
_SKIP_PREFIXES = ("/healthz", "/api-docs", "/api-openapi.json", "/api-redoc", "/web")


class EnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = uuid.uuid4().hex[:32]
        request.state.trace_id = trace_id
        set_trace_id(trace_id)  # 本请求链路上的日志全带同一 trace(与信封/X-Trace-Id 对账)

        response = await call_next(request)

        # 非 API 路径或非 JSON:只加 header,不包裹
        path = request.url.path
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            response.headers["X-Trace-Id"] = trace_id
            return response
        log.info(f"{request.method} {path} → {response.status_code}")  # 请求留痕(带 trace)
        ct = response.headers.get("content-type", "")
        if "application/json" not in ct:
            response.headers["X-Trace-Id"] = trace_id
            return response

        # 读 body → 包信封 → 重建响应
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        try:
            data = json.loads(body)
        except Exception:  # noqa: BLE001 —— body 不是合法 JSON(不该发生)
            data = None

        status_code = response.status_code
        if status_code >= 400:
            # FastAPI 错误格式 {"detail": "..."} → 信封
            message = data.get("detail", str(data)) if isinstance(data, dict) else str(data)
            envelope = {"data": None, "status": "ERROR", "message": message, "traceId": trace_id}
        else:
            # 成功:端点已返回信封(response_model=Envelope,traceId 留空)→ 只补 traceId;
            # 裸 dict(未迁移端点)照旧包装
            if isinstance(data, dict) and "status" in data and "data" in data:
                envelope = data
                if not envelope.get("traceId"):
                    envelope["traceId"] = trace_id
            else:
                envelope = {"data": data, "status": "SUCCESS", "traceId": trace_id}

        new_body = json.dumps(envelope, ensure_ascii=False, default=str).encode()
        headers = dict(response.headers)
        headers["content-length"] = str(len(new_body))
        new_response = Response(
            content=new_body, status_code=status_code,
            headers=headers, media_type="application/json",
        )
        new_response.headers["X-Trace-Id"] = trace_id
        return new_response
