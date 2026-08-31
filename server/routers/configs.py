import logging
import time
import asyncio
import aiohttp
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from db.database import get_db, get_setting, db_write_lock, run_in_thread
from db.models import ConfigCreateOrUpdate, SourceCacheDelete, Config, Subscription, Cache, Host
from core.status import task_runner
from core.engine import trigger_background_queue, enqueue_background_queue

logger = logging.getLogger("推送接口")
router = APIRouter()


@router.get("/data-sources")
def api_list_data_sources():
    """返回已启用的 API 订阅列表"""
    with get_db() as session:
        rows = session.query(Subscription).filter(Subscription.enabled == 1).order_by(Subscription.id).all()
        return {"sources": [{"value": s.uid, "label": s.name} for s in rows]}


def _check_data_source_enabled(ds: str):
    if not ds:
        return
    with get_db() as session:
        enabled_uids = [s.uid for s in session.query(Subscription).filter(Subscription.enabled == 1).all()]
    for name in ds.split(','):
        name = name.strip()
        if not name:
            continue
        if name not in enabled_uids:
            raise HTTPException(400, f"数据源 '{name}' 未启用或不存在")


@router.get("/configs")
def api_list_configs():
    with get_db() as session:
        rows = session.query(Config).order_by(Config.id.desc()).all()
        return [{
            "id": r.id, "name": r.name, "dataSource": r.data_source,
            "templateRegion": r.template_region, "templateOperator": r.template_operator,
            "templateTargetName": r.template_target_name, "templateTargetAddress": r.template_target_address,
            "enabled": bool(r.enabled), "createdAt": r.created_at, "updatedAt": r.updated_at,
        } for r in rows]


@router.post("/configs")
def api_create_config(data: ConfigCreateOrUpdate):
    _check_data_source_enabled(data.data_source)
    with db_write_lock:
        with get_db() as session:
            now = int(time.time())
            config = Config(
                name=data.name,
                data_source=data.data_source,
                template_region=data.region,
                template_operator=data.operator,
                template_target_name=data.target_name,
                template_target_address=data.target_address,
                enabled=1 if data.enabled else 0,
                created_at=now,
                updated_at=now,
            )
            session.add(config)
            session.flush()
            result = {
                "id": config.id, "name": config.name, "dataSource": config.data_source,
                "templateRegion": config.template_region, "templateOperator": config.template_operator,
                "templateTargetName": config.template_target_name, "templateTargetAddress": config.template_target_address,
                "enabled": bool(config.enabled), "createdAt": config.created_at, "updatedAt": config.updated_at,
            }
    return result


@router.put("/configs/{config_id}")
def api_update_config(config_id: int, data: ConfigCreateOrUpdate):
    _check_data_source_enabled(data.data_source)
    with db_write_lock:
        with get_db() as session:
            config = session.query(Config).filter(Config.id == config_id).first()
            if not config:
                raise HTTPException(404, "配置不存在")
            config.name = data.name
            config.data_source = data.data_source
            config.template_region = data.region
            config.template_operator = data.operator
            config.template_target_name = data.target_name
            config.template_target_address = data.target_address
            config.enabled = 1 if data.enabled else 0
            config.updated_at = int(time.time())
    return {"ok": True}


@router.delete("/configs/{config_id}")
def api_delete_config(config_id: int):
    with db_write_lock:
        with get_db() as session:
            session.query(Config).filter(Config.id == config_id).delete()
    return {"ok": True}


@router.post("/configs/{config_id}/run")
def api_trigger_single_config(config_id: int):
    with get_db() as session:
        config = session.query(Config).filter(Config.id == config_id).first()
        if not config:
            raise HTTPException(404, "配置不存在")
        if not config.enabled:
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

    current_id = task_runner.get_current_config_id()
    queue = task_runner.get_config_ids()
    logger.info(f"🛑 [停止请求] cfg_id={config_id}, current_id={current_id}, queue={queue}")

    if current_id == config_id:
        task_runner.stop_current_and_continue()
        logger.info(f"🛑 [中断当前] cfg_id={config_id}，将跳到下一个")
        return {"ok": True, "msg": "已中断当前任务"}

    if task_runner.remove_from_queue(config_id):
        queue = task_runner.get_config_ids()
        logger.info(f"🛑 [移除排队] cfg_id={config_id}, 新队列={queue}")
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
    with get_db() as session:
        rows = session.query(Config).filter(Config.enabled == 1).all()
        if not rows:
            raise HTTPException(400, "无可用配置")
        ids = [r.id for r in rows]
    if task_runner.is_idle():
        logger.info(f"▶️ [全部运行] 空闲状态，启动新队列 ids={ids}")
        trigger_background_queue(ids, skip_disabled=True)
    else:
        logger.info(f"▶️ [全部运行] 运行中，追加 ids={ids}")
        for id_val in ids:
            enqueue_background_queue(id_val)
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
    with get_db() as session:
        query = session.query(Cache).filter(Cache.active == 0)
        if geo_region:
            query = query.filter(Cache.geo_region == geo_region)

        total = query.count()

        if page < 1:
            page = 1
        page_size = max(1, min(page_size, 200))
        offset = (page - 1) * page_size
        rows = query.order_by(Cache.source_type, Cache.id.desc()).limit(page_size).offset(offset).all()

        return {
            "items": [{
                "id": r.id, "sourceType": r.source_type, "host": r.host,
                "geoRegion": r.geo_region, "geoOperator": r.geo_operator,
                "active": r.active, "status": r.status,
                "createdAt": r.created_at, "updatedAt": r.updated_at,
            } for r in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,
        }


def _update_cache_status(cache_id: int, new_status: int, now: int):
    with db_write_lock:
        with get_db() as session:
            cache = session.query(Cache).filter(Cache.id == cache_id).first()
            if cache:
                cache.status = new_status
                cache.updated_at = now


def _get_cache_host(cache_id: int):
    with get_db() as session:
        cache = session.query(Cache).filter(Cache.id == cache_id).first()
        host = cache.host if cache else None
    return host


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
    """根据 id 列表或 sourceType 列表删除 cache 数据"""
    ids = data.ids
    source_types = data.source_types

    if ids is not None and isinstance(ids, int):
        ids = [ids]
    if source_types is not None and isinstance(source_types, str):
        source_types = [source_types]

    if not ids and not source_types:
        raise HTTPException(400, "请提供 ids 或 sourceTypes 参数")

    with db_write_lock:
        with get_db() as session:
            if ids:
                session.query(Cache).filter(Cache.id.in_(ids)).delete(synchronize_session="fetch")
            if source_types:
                session.query(Cache).filter(Cache.source_type.in_(source_types)).delete(synchronize_session="fetch")
    return {"ok": True}


@router.post("/source-cache/clear-orphans")
def api_cache_clear_orphans():
    """清空所有游离主机（active=0）"""
    with db_write_lock:
        with get_db() as session:
            deleted = session.query(Cache).filter(Cache.active == 0).delete(synchronize_session="fetch")
    logger.info(f"🗑️ [清空游离] 删除了 {deleted} 条")
    return {"ok": True, "deleted": deleted}


@router.post("/source/push")
async def api_source_push(request: Request):
    """外部服务推送清洗后的 host 列表"""
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

    source_name = source_type
    if source_type != "unknown":
        with get_db() as session:
            sub = session.query(Subscription).filter(Subscription.uid == source_type, Subscription.enabled == 1).first()
            if not sub:
                raise HTTPException(400, f"sourceType '{source_type}' 不存在或未启用，请先在订阅管理中创建对应订阅")
            source_name = sub.name

    logger.info(f"📥 收到 {len(hosts)} 个资产 ({source_type})")

    async def _process_and_notify():
        try:
            count = await process_source_data(source_type, hosts)
            from services.message_service import create_message, MSG_TYPE_SUCCESS
            create_message(MSG_TYPE_SUCCESS, f"数据推送完成：{source_name}", f"获取到 {count} 条数据", "订阅管理")
        except Exception as e:
            from services.message_service import create_message, MSG_TYPE_ERROR
            logger.error(f"❌ 处理推送数据失败: {e}")
            create_message(MSG_TYPE_ERROR, f"数据推送失败：{source_name}", f"错误: {str(e)}", "订阅管理")

    asyncio.create_task(_process_and_notify())

    return {
        "ok": True,
        "sourceType": source_type,
        "received": len(hosts),
        "msg": "已接收，后台处理中"
    }
