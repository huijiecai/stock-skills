"""api·系统端点:manifest 读写 + 指令在线编辑(版本库,按系统命名空间)。"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trader.api.deps import require_user
from trader.core.promptver import default_prompt_versions
from trader.core.systems import default_systems

router = APIRouter(prefix="/systems", tags=["systems"])


def _validate_manifest(manifest: dict) -> None:
    from trader.core.stageio import validate_stage_contracts

    errors = validate_stage_contracts(manifest)
    if errors:
        raise HTTPException(400, "阶段配置无效:" + "；".join(errors[:8]))


def _own_system(slug: str, who: dict) -> dict:
    row = default_systems().get(slug, user_id=who["user"]["id"])
    if row is None:
        raise HTTPException(404, f"系统不存在:{slug}")
    return row


class SystemIn(BaseModel):
    slug: str
    display_name: str = ""
    manifest: dict
    status: str = "active"


def _ensure_manifest_prompts(row: dict, user_id: int) -> None:
    """系统创建即具备可运行的 v1，不依赖用户先进入设置页保存一次。"""
    manifest = row["manifest"]
    pv = default_prompt_versions()
    for stage_name, sdef in manifest.get("stages", {}).items():
        prompt = sdef.get("prompt")
        if prompt and pv.latest(row["id"], prompt, user_id=user_id) is None:
            pv.save(row["id"], prompt,
                    f"# {row['slug']} · {stage_name}\n\n(在此编写此阶段的 prompt...)\n",
                    user_id=user_id, display_name=sdef.get("label") or stage_name)
    system_prompt = manifest.get("system_prompt")
    if system_prompt and pv.latest(row["id"], system_prompt, user_id=user_id) is None:
        pv.save(row["id"], system_prompt,
                f"你是 {row['slug']} 的 AI agent。\n(在此编写系统级角色设定...)\n",
                user_id=user_id, display_name="系统设定")


@router.get("")
def list_systems(who: dict = Depends(require_user)):
    rows = default_systems().list(user_id=who["user"]["id"])
    from trader.core.portfolios import default_portfolios
    for row in rows:
        default_portfolios().ensure_main(who["user"]["id"], row["id"])
    return rows


@router.post("")
def upsert_system(body: SystemIn, who: dict = Depends(require_user)):
    _validate_manifest(body.manifest)
    row = default_systems().upsert(body.slug, body.manifest, body.status,
                                   user_id=who["user"]["id"],
                                   display_name=body.display_name)
    _ensure_manifest_prompts(row, who["user"]["id"])
    from trader.core.portfolios import default_portfolios
    default_portfolios().ensure_main(who["user"]["id"], row["id"])
    return {"slug": row["slug"], "display_name": row["display_name"],
            "status": row["status"]}


@router.get("/{slug}")
def get_system(slug: str, who: dict = Depends(require_user)):
    row = _own_system(slug, who)
    from trader.core.portfolios import default_portfolios
    default_portfolios().ensure_main(who["user"]["id"], row["id"])
    return row


class ManifestIn(BaseModel):
    manifest: dict


@router.put("/{slug}/manifest")
def update_manifest(slug: str, body: ManifestIn, who: dict = Depends(require_user)):
    """更新 manifest(阶段/工具/联网开关)——编辑器里动态改的一切走这里。
    新增阶段的指令如果不存在,自动创建空模板(挂在系统命名空间)。"""
    uid = who["user"]["id"]
    row = _own_system(slug, who)
    system_id = row["id"]

    m = body.manifest
    _validate_manifest(m)
    pv = default_prompt_versions()
    for stage_name, sdef in m.get("stages", {}).items():
        p = sdef.get("prompt")
        if p and pv.latest(system_id, p, user_id=uid) is None:
            pv.save(system_id, p,
                    f"# {slug} · {stage_name}\n\n(在此编写此阶段的 prompt...)\n", user_id=uid)
    sp = m.get("system_prompt")
    if sp and pv.latest(system_id, sp, user_id=uid) is None:
        pv.save(system_id, sp, f"你是 {slug} 的 AI agent。\n(在此编写系统级角色设定...)\n",
                user_id=uid)

    updated = default_systems().upsert(slug, m, row.get("status", "active"), user_id=uid,
                                       display_name=row.get("display_name") or slug)
    return {"slug": updated["slug"], "stages": list(m.get("stages", {}).keys()),
            "tools": len(m.get("tools", []))}


# ── 指令在线编辑(命名空间=系统;md 编辑面在此退役)──────

@router.get("/{slug}/stages/{stage}/context")
def stage_context(slug: str, stage: str, date: str = "",
                  who: dict = Depends(require_user)):
    """阶段变量契约:该阶段 prompt 可用的占位符(编辑器变量面板/占位符 lint/
    替换预览共用,与引擎运行时同源)。date 给出时派生变量算真值。
    stage=(system) 表示系统设定——不做变量替换。"""
    row = _own_system(slug, who)
    if stage == "(system)":
        return {"kind": "system", "vars": [],
                "note": "系统设定不做变量替换,任何 {xxx} 都按字面文本发给模型"}
    sdef = (row["manifest"].get("stages") or {}).get(stage)
    if sdef is None:
        raise HTTPException(404, f"阶段不存在:{stage}")
    from trader.core.engine import stage_var_schema
    return stage_var_schema(sdef, date=date or None)


@router.get("/{slug}/prompts")
def list_prompts(slug: str, who: dict = Depends(require_user)):
    row = _own_system(slug, who)
    pv = default_prompt_versions()
    out = []
    for stage, d in row["manifest"].get("stages", {}).items():
        p = d.get("prompt")
        if p:
            vr = pv.versions(row["id"], p, user_id=who["user"]["id"])
            out.append({"stage": stage, "prompt": p,
                        "latest_version": vr[0]["version"] if vr else None})
    sp = row["manifest"].get("system_prompt")
    if sp:
        vr = pv.versions(row["id"], sp, user_id=who["user"]["id"])
        out.append({"stage": "(system)", "prompt": sp,
                    "latest_version": vr[0]["version"] if vr else None})
    return out


@router.get("/{slug}/prompts/{prompt}/versions")
def prompt_versions(slug: str, prompt: str, who: dict = Depends(require_user)):
    row = _own_system(slug, who)
    return default_prompt_versions().versions(row["id"], prompt,
                                               user_id=who["user"]["id"])


@router.get("/{slug}/prompts/{prompt}/versions/{version}")
def prompt_content(slug: str, prompt: str, version: int,
                   who: dict = Depends(require_user)):
    row = _own_system(slug, who)
    c = default_prompt_versions().get(row["id"], prompt, version,
                                      user_id=who["user"]["id"])
    if c is None:
        raise HTTPException(404, "版本不存在")
    return {"prompt": prompt, "version": version, "content": c}


@router.put("/{slug}/prompts/{prompt}")
def save_prompt(slug: str, prompt: str, body: dict, who: dict = Depends(require_user)):
    """保存新版本(内容变更才入库);返回版本号。"""
    row = _own_system(slug, who)
    r = default_prompt_versions().save(row["id"], prompt, body.get("content", ""),
                                       user_id=who["user"]["id"])
    return {"prompt": prompt, "version": r["version"], "changed": r["changed"]}


@router.put("/{slug}/restore")
def restore_system(slug: str, who: dict = Depends(require_user)):
    """恢复归档系统(status → active)。"""
    from trader.core.db import _connect
    uid = who["user"]["id"]
    _own_system(slug, who)
    with _connect() as conn:
        conn.execute("UPDATE systems SET status='active', updated_at=%s"
                     " WHERE user_id=%s AND slug=%s",
                     (datetime.now().isoformat(timespec="seconds"), uid, slug))
    return {"restored": slug, "status": "active"}


@router.delete("/{slug}")
def delete_system(slug: str, who: dict = Depends(require_user)):
    """归档系统(软删除,数据保留,状态→archived)。"""
    from trader.core.db import _connect
    uid = who["user"]["id"]
    _own_system(slug, who)
    with _connect() as conn:
        conn.execute("UPDATE systems SET status='archived', updated_at=%s"
                     " WHERE user_id=%s AND slug=%s",
                     (datetime.now().isoformat(timespec="seconds"), uid, slug))
    return {"deleted": slug, "status": "archived",
            "note": "系统已归档(数据保留,场次历史不受影响;恢复改 status=active)"}


# ── 运行系统(子进程,每会话一进程)──────────────────────

class RunIn(BaseModel):
    date: str
    stage: str = ""          # 空=取 manifest 第一个阶段
    clock: str = "real"      # 发起时绑定:real(实盘值守) | simulated(重演某日)
    interval: int = 5        # simulated:模拟时钟步进(分钟/轮)
    sleep_seconds: int = 0   # real loop:每轮完成后休息秒数(0=连续看盘)
    prompt_version: int | None = None  # 钉住阶段指令版本；空=最新
    opening: str = "fresh"   # simulated 实验组合开局
    portfolio_type: str = "main"  # real 时 main | paper；simulated 强制 experiment


@router.post("/{slug}/run")
def run_system(slug: str, body: RunIn, who: dict = Depends(require_user)):
    """发起一次运行,子进程执行。阶段类型 × 时钟自动适配:
    - single:跑一次出报告(premarket/close/research/自定义分析)
    - loop + real:实时看盘(对接当前行情,15:05 自动收工)
    - loop + simulated:重演某日(模拟时钟,9:35-15:00 循环)
    """
    import subprocess
    from pathlib import Path
    uid = who["user"]["id"]
    row = _own_system(slug, who)
    stages = row["manifest"].get("stages", {})
    stage = body.stage or next(iter(stages), "")
    if stage not in stages:
        raise HTTPException(400, f"阶段不存在:{stage}(可用:{list(stages)})")

    sdef = stages[stage]
    kind = sdef.get("kind", "single")
    if body.clock not in ("real", "simulated"):
        raise HTTPException(400, "clock 只允许 real 或 simulated")
    if body.opening not in ("fresh", "fork", "fork-as-of"):
        raise HTTPException(400, "opening 只允许 fresh、fork、fork-as-of")
    if body.portfolio_type not in ("main", "paper"):
        raise HTTPException(400, "portfolio_type 只允许 main 或 paper")
    if body.prompt_version is not None:
        prompt = sdef.get("prompt", "")
        content = default_prompt_versions().get(row["id"], prompt, body.prompt_version,
                                                user_id=uid)
        if content is None:
            raise HTTPException(400, f"指令 {prompt} v{body.prompt_version} 不存在")

    # ── 重复触发硬拦(防双进程并发写轮次/撞名静默失败)──
    from trader.core.runs import default_runs
    from datetime import datetime as _dt
    mine = default_runs().list(system=slug, user_id=uid)
    if kind == "loop" and body.clock == "real":
        today = _dt.now().strftime("%Y%m%d")
        alive = [r for r in mine if r["clock"] == "real" and r["trade_date"] == today
                 and r.get("stage") == stage
                 and r["status"] in ("running", "stopping")]
        if alive:
            r = alive[0]
            raise HTTPException(409, f"今日实盘已在跑(场次 #{r['id']} {r['status']})。"
                                     "请先在 web 停止它(或强制封存僵尸场),再重新运行——live 会自动接续轮号")
    elif kind == "loop":
        # 重演:web 发起名固定 {date}-web-{slug},同名已存在必撞 UniqueViolation
        dup = next((r for r in mine if r["kind"] == "replay"
                    and r["slug"] == f"{body.date}-web-{slug}"), None)
        if dup:
            raise HTTPException(409, f"{body.date} 已有该系统的重演场(#{dup['id']} {dup['status']})。"
                                     "换个日期,或先删除旧场再跑")

    if kind == "single":
        code = (f"from trader.core.engine import run_single; "
                f"run_single({slug!r}, {stage!r}, user_id={uid}, date={body.date!r}, "
                f"clock={body.clock!r}, prompt_version={body.prompt_version!r}, "
                f"opening={body.opening!r}, portfolio_type={body.portfolio_type!r})")
    elif body.clock == "real":
        code = (f"from trader.core.engine import run_live; "
                f"run_live({slug!r}, stage_name={stage!r}, user_id={uid}, "
                f"sleep_seconds={body.sleep_seconds}, prompt_version={body.prompt_version!r}, "
                f"portfolio_type={body.portfolio_type!r})")
    else:  # loop + simulated(重演某日)
        code = (f"from trader.core.engine import run_replay; "
                f"run_replay({slug!r}, {body.date!r}, stage_name={stage!r}, "
                f"interval={body.interval}, tag={'web-' + slug!r}, user_id={uid}, "
                f"opening={body.opening!r}, prompt_version={body.prompt_version!r})")

    cmd = ["uv", "run", "python", "-c", code]
    log = Path("logs/api_runs.log")
    with log.open("ab") as f:
        subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True,
                         cwd=Path(__file__).resolve().parent.parent.parent,
                         env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"})
    return {"started": True, "system": slug, "stage": stage, "date": body.date,
            "kind": kind, "clock": body.clock,
            "note": "已发起,到「场次」页看进度和结果"}
