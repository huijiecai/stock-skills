"""api·系统端点:manifest 读写 + prompt 在线编辑(版本库,FE-1 的 PromptEditor 吃这组)。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core.promptver import default_prompt_versions
from trader.core.systems import default_systems

router = APIRouter(prefix="/systems", tags=["systems"])


class SystemIn(BaseModel):
    name: str
    manifest: dict
    status: str = "active"


@router.get("")
def list_systems(who: dict = Depends(require_user)):
    return default_systems().list(user_id=who["user"]["id"])


@router.post("")
def upsert_system(body: SystemIn, who: dict = Depends(require_user)):
    try:
        row = default_systems().upsert(body.name, body.manifest, body.status,
                                       user_id=who["user"]["id"])
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"name": row["name"], "status": row["status"]}


@router.get("/{name}")
def get_system(name: str, who: dict = Depends(require_user)):
    row = default_systems().get(name, user_id=who["user"]["id"])
    if row is None:
        raise HTTPException(404, f"系统不存在:{name}")
    return row


# ── prompt 在线编辑(命名空间=用户;md 编辑面在此退役,实现设计附录 8)──

@router.get("/{name}/prompts")
def list_prompts(name: str, who: dict = Depends(require_user)):
    pv = default_prompt_versions()
    out = []
    for stage, d in (default_systems().get(name, user_id=who["user"]["id"])
                     or {}).get("manifest", {}).get("stages", {}).items():
        p = d.get("prompt")
        if p:
            row = pv.versions(p, user_id=who["user"]["id"])
            out.append({"stage": stage, "prompt": p,
                        "latest_version": row[0]["version"] if row else None})
    sp = (default_systems().get(name, user_id=who["user"]["id"]) or {}) \
        .get("manifest", {}).get("system_prompt")
    if sp:
        row = pv.versions(sp, user_id=who["user"]["id"])
        out.append({"stage": "(system)", "prompt": sp,
                    "latest_version": row[0]["version"] if row else None})
    return out


@router.get("/{name}/prompts/{prompt}/versions")
def prompt_versions(name: str, prompt: str, who: dict = Depends(require_user)):
    return default_prompt_versions().versions(prompt, user_id=who["user"]["id"])


@router.get("/{name}/prompts/{prompt}/versions/{version}")
def prompt_content(name: str, prompt: str, version: int, who: dict = Depends(require_user)):
    c = default_prompt_versions().get(prompt, version, user_id=who["user"]["id"])
    if c is None:
        raise HTTPException(404, "版本不存在")
    return {"prompt": prompt, "version": version, "content": c}


@router.put("/{name}/prompts/{prompt}")
def save_prompt(name: str, prompt: str, body: dict, who: dict = Depends(require_user)):
    """保存新版本(内容变更才入库);返回版本号。"""
    if default_systems().get(name, user_id=who["user"]["id"]) is None:
        raise HTTPException(404, f"系统不存在:{name}")
    r = default_prompt_versions().save(prompt, body.get("content", ""),
                                        user_id=who["user"]["id"])
    return {"prompt": prompt, "version": r["version"], "changed": r["changed"]}
