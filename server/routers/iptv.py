from fastapi import APIRouter
import aiohttp
import logging
import time
from typing import Optional
from datetime import datetime

from db.database import get_iptv_db, get_cache_db, get_setting, run_in_thread

logger = logging.getLogger("组播源")
router = APIRouter()


def _fetch_iptv_source(source_id: int):
    with get_iptv_db() as conn:
        return conn.execute("SELECT * FROM iptv_list WHERE id=?", (source_id,)).fetchone()


def _update_iptv_delay(delay: int, now: int, source_id: int):
    with get_iptv_db() as conn:
        conn.execute("UPDATE iptv_list SET delay=?, updateTime=? WHERE id=?", (delay, now, source_id))


@router.get("/iptv-pool")
def api_get_iptv_pool(
    region: Optional[str] = None,
    operator: Optional[str] = None,
    geo_region: Optional[str] = None,
    geo_operator: Optional[str] = None,
    page: int = 1,
    page_size: int = 0,
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
    if page_size < 0 or page_size > 2000:
        page_size = 0
    offset = (page - 1) * page_size if page_size > 0 else 0

    with get_iptv_db() as conn:
        total_active = conn.execute(f"SELECT COUNT(*) AS cnt FROM iptv_list WHERE {where_sql}", params).fetchone()["cnt"]

        group_rows = conn.execute(f"""
            SELECT region, operator,
                   COUNT(*) AS cnt,
                   ROUND(AVG(CASE WHEN delay>0 THEN delay END)) AS avg_delay
            FROM iptv_list
            WHERE {where_sql}
            GROUP BY region, operator
            ORDER BY region ASC, operator ASC
        """, params).fetchall()

        if page_size > 0:
            detail_rows = conn.execute(f"""
                SELECT id, host, protocol, target, channelName, delay,
                       sourceType, sourceName, region, operator,
                       geoRegion, geoOperator, createTime, updateTime
                FROM iptv_list
                WHERE {where_sql}
                ORDER BY region ASC, operator ASC, delay ASC, updateTime DESC
                LIMIT ? OFFSET ?
            """, params + [page_size, offset]).fetchall()
        else:
            detail_rows = conn.execute(f"""
                SELECT id, host, protocol, target, channelName, delay,
                       sourceType, sourceName, region, operator,
                       geoRegion, geoOperator, createTime, updateTime
                FROM iptv_list
                WHERE {where_sql}
                ORDER BY region ASC, operator ASC, delay ASC, updateTime DESC
            """, params).fetchall()

    group_map = {}
    for gr in group_rows:
        r_val = gr["region"] or ""
        o_val = gr["operator"] or ""
        key = f"{r_val} / {o_val}"
        group_map[key] = {
            "region": r_val,
            "operator": o_val,
            "count": gr["cnt"],
            "avgLatency": gr["avg_delay"] or 0,
            "heads": []
        }

    for row in detail_rows:
        region_val = row["region"] or ""
        operator_val = row["operator"] or ""
        group_key = f"{region_val} / {operator_val}"

        protocol = row["protocol"] or "udp"
        target = row["target"] or ""
        if target.startswith("/"):
            target = target[1:]
        play_url = f"http://{row['host']}/{protocol}/{target}"

        try:
            last_seen = datetime.fromtimestamp(row["updateTime"] / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError, OverflowError):
            last_seen = ""

        try:
            create_time = datetime.fromtimestamp(row["createTime"] / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError, OverflowError):
            create_time = ""

        group_map[group_key]["heads"].append({
            "id": row["id"],
            "sourceType": row["sourceType"] or "",
            "sourceName": row["sourceName"] or "",
            "url": play_url,
            "host": row["host"],
            "protocol": protocol,
            "target": target,
            "channelName": row["channelName"],
            "latencyMs": row["delay"],
            "region": region_val,
            "operator": operator_val,
            "geoRegion": row["geoRegion"] or "",
            "geoOperator": row["geoOperator"] or "",
            "createTime": create_time,
            "lastSeen": last_seen,
            "updateTime": row["updateTime"]
        })

    result_list = list(group_map.values())

    return {
        "totalActiveHeads": total_active,
        "totalGroups": len(result_list),
        "page": page,
        "pageSize": page_size,
        "totalPages": (total_active + page_size - 1) // page_size if page_size > 0 else 1,
        "groups": result_list
    }


@router.post("/iptv/{source_id}/test-delay")
async def api_test_delay(source_id: int):
    """测试单个活源延迟，更新数据库并返回最新延迟"""
    row = await run_in_thread(lambda: _fetch_iptv_source(source_id))

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
                    now = int(time.time() * 1000)
                    await run_in_thread(_update_iptv_delay, delay, now, source_id)
                    logger.info(f"✅ [延迟测试] id={source_id} -> {delay}ms")
                    return {"ok": True, "delay": delay}
    except Exception as e:
        logger.warning(f"⚠️ [延迟测试失败] id={source_id} -> {e}")

    now = int(time.time() * 1000)
    await run_in_thread(_update_iptv_delay, -1, now, source_id)
    return {"ok": False, "delay": -1}


@router.delete("/iptv/{source_id}")
def api_delete_iptv_source(source_id: int):
    """删除单个组播源。若host在iptv_list中已无其他条目，同步从source_cache清理"""
    ok, err = _do_delete_iptv(source_id)
    if not ok:
        return {"ok": False, "error": err}
    return {"ok": True}


def _do_delete_iptv(source_id: int) -> tuple[bool, str]:
    """执行删除，返回 (成功?, 错误信息)"""
    with get_iptv_db() as conn:
        row = conn.execute("SELECT host FROM iptv_list WHERE id=?", (source_id,)).fetchone()
        if not row:
            return False, "源不存在"
        host = row["host"]
        conn.execute("DELETE FROM iptv_list WHERE id=?", (source_id,))
        remaining = conn.execute("SELECT COUNT(*) AS cnt FROM iptv_list WHERE host=?", (host,)).fetchone()["cnt"]

    if remaining == 0:
        with get_cache_db() as conn:
            conn.execute("DELETE FROM source_cache WHERE host=?", (host,))
            logger.info(f"🗑️ [同步清理] host={host} 已从 source_cache 中删除")

    logger.info(f"🗑️ [删除组播源] id={source_id}, host={host}, 剩余条目={remaining}")
    return True, ""


@router.post("/iptv/batch-delete")
def api_batch_delete_iptv(data: dict):
    """批量删除组播源。"""
    ids = data.get("ids", [])
    if not ids:
        return {"ok": False, "error": "ids 不能为空"}

    success = []
    failed = []
    for sid in ids:
        ok, err = _do_delete_iptv(sid)
        if ok:
            success.append(sid)
        else:
            failed.append({"id": sid, "error": err})

    return {"ok": True, "success": success, "failed": failed}
