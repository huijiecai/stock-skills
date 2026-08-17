"""viewer 启动入口:uv run python -m trader.viewer [--port 8500] [--reload]。"""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="trader 只读查看器(本地)")
    parser.add_argument("--port", type=int, default=8500, help="端口(默认 8500)")
    parser.add_argument("--reload", action="store_true", help="开发模式:改模板/代码自动生效")
    args = parser.parse_args()
    uvicorn.run("trader.viewer.app:app", host="127.0.0.1", port=args.port,
                reload=args.reload)


if __name__ == "__main__":
    main()
