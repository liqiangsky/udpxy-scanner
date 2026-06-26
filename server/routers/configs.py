import logging
import time
import asyncio
import aiohttp
from fastapi import APIRouter, HTTPException, Query, Request
from db.database import get_db, get_setting, get_cache_db
from db.models import ConfigCreateOrUpdate, SourceCacheDelete
from typing import Optional
from core.status import task_runner
from core.engine import trigger_background_queue, enqueue_background_queue

logger = logging.getLogger("推送接口")
router = APIRouter()


@router.get("/data-sources")
def api_list_data_sources():
    """返回已启用的 API 订阅列表"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT uid AS value, name AS label FROM api_subscriptions WHERE enabled=1 ORDER BY id"
        ).fetchall()
    return {"sources": [dict(r) for r in rows]}


def _check_data_source_enabled(ds: str):
    if not ds:
        return
    with get_db() as conn:
        enabled_uids = [
            r["uid"] for r in conn.execute(
                "SELECT uid FROM api_subscriptions WHERE enabled=1"
            ).fetchall()
        ]
    for name in ds.split(','):
        name = name.strip()
        if not name:
            continue
        if name not in enabled_uids:
            raise HTTPException(400, f"数据源 '{name}' 未启用或不存在")


@router.get("/configs")
def api_list_configs():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM scan_config ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

@router.post("/configs")
def api_create_config(data: ConfigCreateOrUpdate):
    _check_data_source_enabled(data.dataSource)
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO scan_config (name, dataSource,
                                     templateRegion, templateOperator, templateTargetName, templateTargetAddress,
                                     enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data.name, data.dataSource,
            data.region, data.operator, data.targetName, data.targetAddress,
            1 if data.enabled else 0
        ))
        result = dict(conn.execute("SELECT * FROM scan_config WHERE id=?", (cur.lastrowid,)).fetchone())
    return result

@router.put("/configs/{config_id}")
def api_update_config(config_id: int, data: ConfigCreateOrUpdate):
    _check_data_source_enabled(data.dataSource)
    with get_db() as conn:
        conn.execute("""
            UPDATE scan_config SET name=?, dataSource=?,
                                   templateRegion=?, templateOperator=?, templateTargetName=?, templateTargetAddress=?,
                                   enabled=?, updatedAt=datetime('now')
            WHERE id=?
        """, (
            data.name, data.dataSource,
            data.region, data.operator, data.targetName, data.targetAddress,
            1 if data.enabled else 0, config_id
        ))
    return {"ok": True}

@router.delete("/configs/{config_id}")
def api_delete_config(config_id: int):
    with get_db() as conn: conn.execute("DELETE FROM scan_config WHERE id=?", (config_id,))
    return {"ok": True}

@router.post("/configs/{config_id}/run")
def api_trigger_single_config(config_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT enabled FROM scan_config WHERE id=?", (config_id,)).fetchone()
        if not row:
            raise HTTPException(404, "配置不存在")
        if row["enabled"] != 1:
            raise HTTPException(400, "该配置已禁用")
    if task_runner.is_rechecking():
        raise HTTPException(400, "当前正在进行活源复测，请稍后再启动扫描")
    if task_runner.is_idle():
        logger.info(f"▶️ [手动运行] 空闲状态，启动新队列 cfg_id={config_id}")
        trigger_background_queue([config_id])
    else:
        logger.info(f"▶️ [手动运行] 运行中，追加 cfg_id={config_id}")
        enqueue_background_queue(config_id)
    return {"ok": True}

@router.post("/configs/{config_id}/stop")
def api_stop_single_config(config_id: int):
    if task_runner.is_idle():
        raise HTTPException(400, "当前无运行中的任务")

    # 当前正在执行的配置：中断并跳到下一个
    current_id = task_runner.get_current_config_id()
    queue = task_runner.get_config_ids()
    logger.info(f"🛑 [停止请求] cfg_id={config_id}, current_id={current_id}, queue={queue}")

    if current_id == config_id:
        task_runner.stop_current_and_continue()
        logger.info(f"🛑 [中断当前] cfg_id={config_id}，将跳到下一个")
        return {"ok": True, "msg": "已中断当前任务，自动进入下一个"}

    # 排队中的配置：从队列移除（不包括已完成和正在执行的）
    if task_runner.remove_from_queue(config_id):
        queue = task_runner.get_config_ids()
        logger.info(f"🛑 [移除排队] cfg_id={config_id}，新队列={queue}")
        return {"ok": True, "msg": "已从队列移除"}

    logger.warning(f"⚠️ [停止失败] cfg_id={config_id} 不在队列中（可能已完成或正在执行）")
    raise HTTPException(400, "该配置不在队列中（可能已完成或正在执行）")

@router.post("/configs/run-all")
def api_trigger_run_all():
    if task_runner.is_rechecking():
        raise HTTPException(400, "当前正在进行活源复测，请稍后再启动扫描")
    if task_runner.is_idle():
        with get_db() as conn: rows = conn.execute("SELECT id FROM scan_config WHERE enabled=1").fetchall()
        if not rows: raise HTTPException(400, "无可用激活配置")
        ids = [r["id"] for r in rows]
        logger.info(f"▶️ [全部运行] 空闲状态，启动新队列 ids={ids}")
        trigger_background_queue(ids, skip_disabled=True)
    else:
        with get_db() as conn: rows = conn.execute("SELECT id FROM scan_config WHERE enabled=1").fetchall()
        if not rows: raise HTTPException(400, "无可用激活配置")
        added = []
        for r in rows:
            enqueue_background_queue(r["id"])
            added.append(r["id"])
        logger.info(f"▶️ [全部运行] 运行中，追加 ids={added}")
    return {"ok": True}

@router.get("/configs/progress")
def api_get_progress():
    p = task_runner.get_progress()
    current_id = p["config_ids"][p["current_index"]] if p["config_ids"] and p["current_index"] < len(p["config_ids"]) else None
    queued_ids = p["config_ids"][p["current_index"] + 1:] if p["config_ids"] else []
    return {
        "running": p["running"],
        "currentId": current_id,
        "currentIndex": p["current_index"] if p["running"] else None,
        "total": p["total"],
        "currentName": p["current_config_name"] if p["running"] else None,
        "queuedIds": queued_ids
    }


@router.get("/source-cache/list")
def api_source_cache_list(sourceType: str = Query(None), page: int = Query(1, ge=1), page_size: int = Query(500, ge=1, le=2000)):
    offset = (page - 1) * page_size
    with get_cache_db() as conn:
        if sourceType:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM source_cache WHERE sourceType=?", (sourceType,)).fetchone()["cnt"]
            rows = conn.execute(
                "SELECT * FROM source_cache WHERE sourceType=? ORDER BY id LIMIT ? OFFSET ?",
                (sourceType, page_size, offset)
            ).fetchall()
        else:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM source_cache").fetchone()["cnt"]
            rows = conn.execute("SELECT * FROM source_cache ORDER BY sourceType, id LIMIT ? OFFSET ?", (page_size, offset)).fetchall()
    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "data": [dict(r) for r in rows]
    }


@router.post("/source-cache/delete")
def api_source_cache_delete(data: SourceCacheDelete):
    """根据 id 列表或 sourceType 列表删除 source_cache 数据，body raw JSON"""
    ids = data.ids
    source_types = data.sourceTypes

    # 统一转为列表
    if ids is not None and isinstance(ids, int):
        ids = [ids]
    if source_types is not None and isinstance(source_types, str):
        source_types = [source_types]

    if not ids and not source_types:
        raise HTTPException(400, "请提供 ids 或 sourceTypes 参数")

    with get_cache_db() as conn:
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM source_cache WHERE id IN ({placeholders})", ids)
        if source_types:
            placeholders = ",".join("?" for _ in source_types)
            conn.execute(f"DELETE FROM source_cache WHERE sourceType IN ({placeholders})", source_types)
    return {"ok": True}


@router.post("/source/push")
async def api_source_push(request: Request):
    """
    外部服务推送清洗后的 host 列表到此接口。
    统一数据入库入口，所有数据（外部推送和订阅拉取）都经过相同处理。
    需要 X-API-Key 头部认证（在全局设置中配置）。
    """
    import asyncio
    from services.source_cache import process_source_data

    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        raise HTTPException(401, "缺少 X-API-Key 头部")
    stored_key = get_setting("push_api_key", "")
    if not stored_key:
        raise HTTPException(403, "推送 API Key 未配置，请在全局设置中设置")
    if api_key != stored_key:
        raise HTTPException(403, "API Key 无效")

    body = await request.json()
    source_type = body.get("sourceType", "unknown")
    hosts = body.get("hosts", [])

    logger.info(f"📥 收到 {len(hosts)} 个资产 ({source_type})")

    task = asyncio.create_task(process_source_data(source_type, hosts))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return {
        "ok": True,
        "sourceType": source_type,
        "received": len(hosts),
        "msg": "数据已接收，后台处理中"
    }


