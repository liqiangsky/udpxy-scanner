from fastapi import APIRouter
import aiohttp
import logging
import time
from typing import Optional

from db.database import get_db, get_setting, run_in_thread, db_write_lock
from db.models import Host

logger = logging.getLogger("主机")
router = APIRouter()


def _fetch_host_source(source_id: int):
    with get_db() as session:
        row = session.query(Host).filter(Host.id == source_id).first()
        if row:
            return {
                "id": row.id, "host": row.host, "target": row.target,
                "protocol": row.protocol, "delay": row.delay,
            }
        return None


def _update_host_delay(delay: int, now: int, source_id: int):
    with db_write_lock:
        with get_db() as session:
            host = session.query(Host).filter(Host.id == source_id).first()
            if host:
                host.delay = delay
                host.updated_at = now


@router.get("/hosts")
def api_get_hosts_pool(
    region: Optional[str] = None,
    operator: Optional[str] = None,
    geo_region: Optional[str] = None,
    geo_operator: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    with get_db() as session:
        query = session.query(Host)

        if region:
            query = query.filter(Host.region == region)
        if operator:
            query = query.filter(Host.operator == operator)
        if geo_region:
            query = query.filter(Host.geo_region == geo_region)
        if geo_operator:
            query = query.filter(Host.geo_operator == geo_operator)

        total = query.count()

        if page < 1:
            page = 1
        page_size = max(1, min(page_size, 200))
        offset = (page - 1) * page_size
        rows = query.order_by(Host.created_at.desc()).limit(page_size).offset(offset).all()

        items = []
        for row in rows:
            protocol = row.protocol or "udp"
            target = row.target or ""
            if target.startswith("/"):
                target = target[1:]
            play_url = f"http://{row.host}/{protocol}/{target}"

            items.append({
                "id": row.id,
                "host": row.host,
                "protocol": protocol,
                "target": target,
                "channelName": row.channel_name,
                "delay": row.delay,
                "sourceType": row.source_type or "",
                "sourceName": row.source_name or "",
                "region": row.region or "",
                "operator": row.operator or "",
                "geoRegion": row.geo_region or "",
                "geoOperator": row.geo_operator or "",
                "url": play_url,
                "createdAt": row.created_at,
                "updatedAt": row.updated_at,
            })

    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": (total + page_size - 1) // page_size,
        "items": items,
    }


@router.post("/hosts/{source_id}/test-delay")
async def api_test_delay(source_id: int):
    """测试单个主机延迟，更新数据库并返回最新延迟"""
    row = await run_in_thread(lambda: _fetch_host_source(source_id))

    if not row:
        return {"ok": False, "error": "主机不存在"}

    host_val = row["host"]
    target_val = row["target"]
    protocol_val = (row["protocol"] or "rtp").lower().strip()

    if not host_val.startswith("http"):
        host_val = f"http://{host_val}"

    test_url = f"{host_val.rstrip('/')}/{protocol_val}/{target_val}"

    timeout_sec = int(get_setting("timeout", "2000")) / 1000.0

    try:
        start_t = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(
                test_url,
                timeout=aiohttp.ClientTimeout(total=timeout_sec),
                headers={"User-Agent": "udpxy-scanner/1.0"}
            ) as r:
                if r.status in [200, 206] and await r.content.read(512):
                    delay = int((time.time() - start_t) * 1000)
                    now = int(time.time())
                    await run_in_thread(_update_host_delay, delay, now, source_id)
                    logger.info(f"✅ [延迟测试] id={source_id} -> {delay}ms")
                    return {"ok": True, "delay": delay, "updatedAt": now}
    except Exception as e:
        logger.warning(f"⚠️ [延迟测试失败] id={source_id} -> {e}")

    now = int(time.time())
    await run_in_thread(_update_host_delay, -1, now, source_id)
    return {"ok": False, "delay": -1, "updatedAt": now}


@router.delete("/hosts/{source_id}")
def api_delete_host_source(source_id: int):
    """删除单个主机。若host在hosts中已无其他条目，同步从cache清理"""
    ok, err = _do_delete_host(source_id)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True}


def _do_delete_host(source_id: int) -> tuple:
    """执行删除，返回 (成功?, 错误信息)"""
    with db_write_lock:
        with get_db() as session:
            from db.models import Cache as CacheModel
            row = session.query(Host).filter(Host.id == source_id).first()
            if not row:
                return False, "主机不存在"
            host = row.host
            session.delete(row)
            remaining = session.query(Host).filter(Host.host == host).count()
            if remaining == 0:
                session.query(CacheModel).filter(CacheModel.host == host).delete(synchronize_session="fetch")
                logger.info(f"🗑️ [同步清理] host={host} 已从 cache 中删除")
    logger.info(f"🗑️ [删除主机] id={source_id}, host={host}, 剩余条目={remaining}")
    return True, ""


@router.post("/hosts/batch-delete")
def api_batch_delete_hosts(data: dict):
    """批量删除主机。"""
    ids = data.get("ids", [])
    if not ids:
        return {"ok": False, "error": "缺少 ids 参数"}

    success = []
    failed = []
    for sid in ids:
        ok, err = _do_delete_host(sid)
        if ok:
            success.append(sid)
        else:
            failed.append({"id": sid, "error": err})

    return {"ok": True, "success": success, "failed": failed}
