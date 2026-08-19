import logging
import time
import asyncio
import aiohttp
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from db.database import get_db, get_setting, db_write_lock, run_in_thread
from db.models import ConfigCreateOrUpdate, SourceCacheDelete
from core.status import task_runner
from core.engine import trigger_background_queue, enqueue_background_queue

logger = logging.getLogger("推送接口")
router = APIRouter()


@router.get("/data-sources")
def api_list_data_sources():
    """返回已启用的 API 订阅列表"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT uid AS value, name AS label FROM subscription WHERE enabled=1 ORDER BY id"
        ).fetchall()
    return {"sources": [dict(r) for r in rows]}


def _check_data_source_enabled(ds: str):
    if not ds:
        return
    with get_db() as conn:
        enabled_uids = [
            r["uid"] for r in conn.execute(
                "SELECT uid FROM subscription WHERE enabled=1"
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
        rows = conn.execute("SELECT * FROM config ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

@router.post("/configs")
def api_create_config(data: ConfigCreateOrUpdate):
    _check_data_source_enabled(data.dataSource)
    with db_write_lock:
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO config (name, dataSource,
                                     templateRegion, templateOperator, templateTargetName, templateTargetAddress,
                                     enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                data.name, data.dataSource,
                data.region, data.operator, data.targetName, data.targetAddress,
                1 if data.enabled else 0
            ))
            result = dict(conn.execute("SELECT * FROM config WHERE id=?", (cur.lastrowid,)).fetchone())
    return result

@router.put("/configs/{config_id}")
def api_update_config(config_id: int, data: ConfigCreateOrUpdate):
    _check_data_source_enabled(data.dataSource)
    with db_write_lock:
        with get_db() as conn:
            conn.execute("""
                UPDATE config SET name=?, dataSource=?,
                                   templateRegion=?, templateOperator=?, templateTargetName=?, templateTargetAddress=?,
                                   enabled=?, updatedAt=? WHERE id=?
            """, (
                data.name, data.dataSource,
                data.region, data.operator, data.targetName, data.targetAddress,
                1 if data.enabled else 0, int(time.time()), config_id
            ))
    return {"ok": True}

@router.delete("/configs/{config_id}")
def api_delete_config(config_id: int):
    with db_write_lock:
        with get_db() as conn: conn.execute("DELETE FROM config WHERE id=?", (config_id,))
    return {"ok": True}

@router.post("/configs/{config_id}/run")
def api_trigger_single_config(config_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT enabled FROM config WHERE id=?", (config_id,)).fetchone()
        if not row:
            raise HTTPException(404, "配置不存在")
        if row["enabled"] != 1:
            raise HTTPException(400, "配置已禁用")
    if task_runner.is_rechecking():
        raise HTTPException(400, "复测进行中，请稍后")
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
        raise HTTPException(400, "无运行中的任务")

    # 当前正在执行的配置：中断并跳到下一个
    current_id = task_runner.get_current_config_id()
    queue = task_runner.get_config_ids()
    logger.info(f"🛑 [停止请求] cfg_id={config_id}, current_id={current_id}, queue={queue}")

    if current_id == config_id:
        task_runner.stop_current_and_continue()
        logger.info(f"🛑 [中断当前] cfg_id={config_id}，将跳到下一个")
        return {"ok": True, "msg": "已中断当前任务"}

    # 排队中的配置：从队列移除（不包括已完成和正在执行的）
    if task_runner.remove_from_queue(config_id):
        queue = task_runner.get_config_ids()
        logger.info(f"🛑 [移除排队] cfg_id={config_id}，新队列={queue}")
        return {"ok": True, "msg": "已移除队列"}

    logger.warning(f"⚠️ [停止失败] cfg_id={config_id} 不在队列中（可能已完成或正在执行）")
    raise HTTPException(400, "配置不在队列中")

@router.post("/configs/stop-all")
def api_stop_all():
    if task_runner.is_idle():
        raise HTTPException(400, "无运行中的任务")
    task_runner.stop()
    logger.info("🛑 [全部停止] 已请求停止整个扫描队列")
    return {"ok": True}


@router.post("/configs/run-all")
def api_trigger_run_all():
    if task_runner.is_rechecking():
        raise HTTPException(400, "复测进行中，请稍后")
    if task_runner.is_idle():
        with get_db() as conn: rows = conn.execute("SELECT id FROM config WHERE enabled=1").fetchall()
        if not rows: raise HTTPException(400, "无可用配置")
        ids = [r["id"] for r in rows]
        logger.info(f"▶️ [全部运行] 空闲状态，启动新队列 ids={ids}")
        trigger_background_queue(ids, skip_disabled=True)
    else:
        with get_db() as conn: rows = conn.execute("SELECT id FROM config WHERE enabled=1").fetchall()
        if not rows: raise HTTPException(400, "无可用配置")
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


@router.get("/source-cache/orphans")
def api_cache_orphans(geo_region: Optional[str] = None, page: int = 1, page_size: int = 20):
    """获取所有游离主机（active=0），支持 geoRegion 筛选"""
    where = "active = 0"
    params = []
    if geo_region:
        where += " AND geoRegion = ?"
        params.append(geo_region)

    if page < 1:
        page = 1
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size

    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS cnt FROM cache WHERE {where}", params).fetchone()["cnt"]
        rows = conn.execute(f"SELECT * FROM cache WHERE {where} ORDER BY sourceType, id LIMIT ? OFFSET ?", params + [page_size, offset]).fetchall()
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": (total + page_size - 1) // page_size,
    }


def _update_cache_status(cache_id: int, new_status: int, now: int):
    with db_write_lock:
        with get_db() as conn:
            conn.execute(
                "UPDATE cache SET status=?, updatedAt=? WHERE id=?",
                (new_status, now, cache_id)
            )


def _get_cache_host(cache_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT host FROM cache WHERE id=?", (cache_id,)).fetchone()
    return row["host"] if row else None


@router.post("/source-cache/{cache_id}/check-online")
async def api_cache_check_online(cache_id: int):
    """检测游离主机是否在线（udpxy health check）"""
    host_val = await run_in_thread(_get_cache_host, cache_id)
    if not host_val:
        raise HTTPException(404, "主机不存在")

    if not host_val.startswith("http"):
        host_val = f"http://{host_val}"
    status_url = f"{host_val.rstrip('/')}/status"

    timeout_sec = int(get_setting("timeout", "2000")) / 1000.0
    new_status = -1

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                status_url,
                timeout=aiohttp.ClientTimeout(total=timeout_sec),
                headers={"User-Agent": "udpxy-scanner/1.0"}
            ) as r:
                body = await r.text()
                if r.status == 200 and "udpxy" in body.lower():
                    new_status = 1
    except Exception as e:
        logger.warning(f"⚠️ [在线检测失败] id={cache_id} -> {e}")
    now = int(time.time())
    await run_in_thread(_update_cache_status, cache_id, new_status, now)

    return {"ok": True, "online": new_status == 1, "updatedAt": now, "status": new_status}


@router.post("/source-cache/delete")
def api_cache_delete(data: SourceCacheDelete):
    """根据 id 列表或 sourceType 列表删除 cache 数据，body raw JSON"""
    ids = data.ids
    source_types = data.sourceTypes

    # 统一转为列表
    if ids is not None and isinstance(ids, int):
        ids = [ids]
    if source_types is not None and isinstance(source_types, str):
        source_types = [source_types]

    if not ids and not source_types:
        raise HTTPException(400, "请提供 ids 或 sourceTypes 参数")

    with db_write_lock:
        with get_db() as conn:
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"DELETE FROM cache WHERE id IN ({placeholders})", ids)
            if source_types:
                placeholders = ",".join("?" for _ in source_types)
                conn.execute(f"DELETE FROM cache WHERE sourceType IN ({placeholders})", source_types)
    return {"ok": True}


@router.post("/source-cache/clear-orphans")
def api_cache_clear_orphans():
    """清空所有游离主机（active=0）"""
    with db_write_lock:
        with get_db() as conn:
            deleted = conn.execute("DELETE FROM cache WHERE active=0").rowcount
    logger.info(f"🗑️ [清空游离] 删除了 {deleted} 条")
    return {"ok": True, "deleted": deleted}


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

    # 校验 sourceType 必须是已启用的订阅 UID，防止非法数据入库
    if source_type != "unknown":
        with get_db() as conn:
            sub = conn.execute(
                "SELECT id FROM subscription WHERE uid=? AND enabled=1",
                (source_type,)
            ).fetchone()
        if not sub:
            raise HTTPException(400, f"sourceType '{source_type}' 不存在或未启用，请先在订阅管理中创建对应订阅")

    logger.info(f"📥 收到 {len(hosts)} 个资产 ({source_type})")

    async def _process_and_notify():
        try:
            count = await process_source_data(source_type, hosts)
            from services.message_service import create_message, MSG_TYPE_SUCCESS
            create_message(MSG_TYPE_SUCCESS, f"数据推送完成：{source_type}", f"接收到 {len(hosts)} 条，入库 {count} 条", "外部推送")
        except Exception as e:
            from services.message_service import create_message, MSG_TYPE_ERROR
            logger.error(f"❌ 处理推送数据失败: {e}")
            create_message(MSG_TYPE_ERROR, f"数据推送失败：{source_type}", f"错误: {str(e)}", "外部推送")

    asyncio.create_task(_process_and_notify())

    return {
        "ok": True,
        "sourceType": source_type,
        "received": len(hosts),
        "msg": "已接收，后台处理中"
    }


