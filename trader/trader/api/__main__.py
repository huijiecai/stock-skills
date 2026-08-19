"""api·CLI 入口:uv run python -m trader.api [--port 8501]。"""
import argparse

import uvicorn

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="平台 API 服务")
    p.add_argument("--port", type=int, default=8501)
    p.add_argument("--reload", action="store_true")
    a = p.parse_args()
    uvicorn.run("trader.api.app:app", host="127.0.0.1", port=a.port, reload=a.reload)
