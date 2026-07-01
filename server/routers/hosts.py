from fastapi import APIRouter
import aiohttp
import logging
import time
from typing import Optional

from db.database import get_db, get_setting, run_in_thread

logger = logging.getLogger("主机")
router = APIRouter()


def _fetch_host_source(source_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM host WHERE id=?", (source_id,)).fetchone()


def _update_host_delay(delay: int, now: int, source_id: int):
    with get_db() as conn:
        conn.execute("UPDATE host SET delay=?, updatedAt=? WHERE id=?", (delay, now, source_id))


@router.get("/hosts")
def api_get_hosts_pool(
    region: Optional[str] = None,
    operator: Optional[str] = None,
    geo_region: Optional[str] = None,
    geo_operator: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    where_clauses = []
    params = []

    if region:
        where_clauses.append("region = ?")
        params.append(region)
    if operator:
        where_clauses.append("operator = ?")
        params.append(operator)
    if geo_region:
        where_clauses.append("geoRegion = ?")
        params.append(geo_region)
    if geo_operator:
        where_clauses.append("geoOperator = ?")
        params.append(geo_operator)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    if page < 1:
        page = 1
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size

    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS cnt FROM host WHERE {where_sql}", params).fetchone()["cnt"]

        rows = conn.execute(f"""
            SELECT id, host, protocol, target, channelName, delay,
                   sourceType, sourceName, region, operator,
                   geoRegion, geoOperator, createdAt, updatedAt
            FROM host
            WHERE {where_sql}
            ORDER BY createdAt DESC
            LIMIT ? OFFSET ?
        """, params + [page_size, offset]).fetchall()

    items = []
    for row in rows:
        protocol = row["protocol"] or "udp"
        target = row["target"] or ""
        if target.startswith("/"):
            target = target[1:]
        play_url = f"http://{row['host']}/{protocol}/{target}"

        items.append({
            "id": row["id"],
            "host": row["host"],
            "protocol": protocol,
            "target": target,
            "channelName": row["channelName"],
            "delay": row["delay"],
            "sourceType": row["sourceType"] or "",
            "sourceName": row["sourceName"] or "",
            "region": row["region"] or "",
            "operator": row["operator"] or "",
            "geoRegion": row["geoRegion"] or "",
            "geoOperator": row["geoOperator"] or "",
            "url": play_url,
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
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
    """测试单个活源延迟，更新数据库并返回最新延迟"""
    row = await run_in_thread(lambda: _fetch_host_source(source_id))

    if not row:
        return {"ok": False, "error": "源不存在"}

    source = dict(row)
    host_val = source["host"]
    target_val = source["target"]
    protocol_val = (source.get("protocol") or "rtp").lower().strip()

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
                    return {"ok": True, "delay": delay}
    except Exception as e:
        logger.warning(f"⚠️ [延迟测试失败] id={source_id} -> {e}")

    now = int(time.time())
    await run_in_thread(_update_host_delay, -1, now, source_id)
    return {"ok": False, "delay": -1}


@router.delete("/hosts/{source_id}")
def api_delete_host_source(source_id: int):
    """删除单个主机。若host在hosts中已无其他条目，同步从cache清理"""
    ok, err = _do_delete_host(source_id)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True}


def _do_delete_host(source_id: int) -> tuple[bool, str]:
    """执行删除，返回 (成功?, 错误信息)"""
    with get_db() as conn:
        row = conn.execute("SELECT host FROM host WHERE id=?", (source_id,)).fetchone()
        if not row:
            return False, "源不存在"
        host = row["host"]
        conn.execute("DELETE FROM host WHERE id=?", (source_id,))
        remaining = conn.execute("SELECT COUNT(*) AS cnt FROM host WHERE host=?", (host,)).fetchone()["cnt"]

    if remaining == 0:
        with get_db() as conn:
            conn.execute("DELETE FROM cache WHERE host=?", (host,))
            logger.info(f"🗑️ [同步清理] host={host} 已从 cache 中删除")

    logger.info(f"🗑️ [删除主机] id={source_id}, host={host}, 剩余条目={remaining}")
    return True, ""


@router.post("/hosts/batch-delete")
def api_batch_delete_hosts(data: dict):
    """批量删除主机。"""
    ids = data.get("ids", [])
    if not ids:
        return {"ok": False, "error": "ids 不能为空"}

    success = []
    failed = []
    for sid in ids:
        ok, err = _do_delete_host(sid)
        if ok:
            success.append(sid)
        else:
            failed.append({"id": sid, "error": err})

    return {"ok": True, "success": success, "failed": failed}
