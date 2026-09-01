"""导出 FastAPI OpenAPI 契约 → web/src/api/openapi.json(T2.2)。

前端类型生成链路的中间产物(不入库):本脚本导 json,
`npm run gen:api`(web/)再调 openapi-typescript 生成 schema.d.ts(入库,
diff 即契约变更)。不起服务,直接 app.openapi()。
"""
import json
from pathlib import Path

from trader.api.app import create_app

OUT = Path(__file__).resolve().parent.parent / "web" / "src" / "api" / "openapi.json"


def main() -> None:
    spec = create_app().openapi()
    OUT.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    paths = len(spec.get("paths", {}))
    models = len(spec.get("components", {}).get("schemas", {}))
    print(f"OpenAPI 契约已导出:{OUT}({paths} 条路径,{models} 个模型)")


if __name__ == "__main__":
    main()
