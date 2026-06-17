from fastapi import APIRouter
import aiohttp
import logging
import time
from typing import Optional
from datetime import datetime

from db.database import get_iptv_db, get_setting

logger = logging.getLogger("组播源")
router = APIRouter()


@router.get("/iptv-pool")
def api_get_iptv_pool(
    region: Optional[str] = None,
    operator: Optional[str] = None,
    geo_region: Optional[str] = None,
    geo_operator: Optional[str] = None,
):

    where_clauses = []
    params = []

    #
    # 业务归属过滤
    #
    if region:
        where_clauses.append("region = ?")
        params.append(region)

    if operator:
        where_clauses.append("operator = ?")
        params.append(operator)

    #
    # GEOIP 过滤
    #
    if geo_region:
        where_clauses.append("geoRegion = ?")
        params.append(geo_region)

    if geo_operator:
        where_clauses.append("geoOperator = ?")
        params.append(geo_operator)

    where_sql = (
        " AND ".join(where_clauses)
        if where_clauses
        else "1=1"
    )

    with get_iptv_db() as conn:

        rows = conn.execute(f"""
            SELECT *
            FROM iptv_list
            WHERE {where_sql}

            ORDER BY
                region ASC,
                operator ASC,
                delay ASC,
                updateTime DESC
        """, params).fetchall()

    #
    # 分组
    #
    groups = {}

    for row in rows:

        region_val = row["region"] or ""
        operator_val = row["operator"] or ""

        group_key = f"{region_val} / {operator_val}"

        if group_key not in groups:

            groups[group_key] = {
                "region": region_val,
                "operator": operator_val,

                "count": 0,
                "avgLatency": 0,

                "heads": []
            }

        #
        # URL
        #
        protocol = row["protocol"] or "udp"
        target = row["target"] or ""

        if target.startswith("/"):
            target = target[1:]

        play_url = (
            f"http://{row['host']}/{protocol}/{target}"
        )

        #
        # 更新时间
        #
        try:

            last_seen = datetime.fromtimestamp(
                row["updateTime"] / 1000.0
            ).strftime("%Y-%m-%d %H:%M:%S")

        except Exception:

            last_seen = ""

        try:

            create_time = datetime.fromtimestamp(
                row["createTime"] / 1000.0
            ).strftime("%Y-%m-%d %H:%M:%S")

        except Exception:

            create_time = ""

        #
        # 节点信息
        #
        groups[group_key]["heads"].append({

            "id": row["id"],

            #
            # 来源
            #
            "sourceType": row["sourceType"] or "",
            "sourceName": row["sourceName"] or "",

            #
            # 播放
            #
            "url": play_url,
            "host": row["host"],

            "protocol": protocol,
            "target": target,

            #
            # 频道
            #
            "channelName": row["channelName"],

            #
            # 延迟
            #
            "latencyMs": row["delay"],

            #
            # 业务归属
            #
            "region": region_val,
            "operator": operator_val,

            #
            # GEOIP
            #
            "geoRegion": row["geoRegion"] or "",
            "geoOperator": row["geoOperator"] or "",

            #
            # 时间
            #
            "createTime": create_time,
            "lastSeen": last_seen,
            "updateTime": row["updateTime"]
        })

    #
    # 统计
    #
    result_list = []

    for group in groups.values():

        latencies = [
            h["latencyMs"]
            for h in group["heads"]
            if h["latencyMs"] is not None
        ]

        group["count"] = len(group["heads"])

        group["avgLatency"] = (
            round(sum(latencies) / len(latencies))
            if latencies
            else 0
        )

        #
        # 默认按延迟排序
        #
        group["heads"].sort(
            key=lambda x: (
                x["latencyMs"]
                if x["latencyMs"] is not None
                else 999999
            )
        )

        result_list.append(group)

    #
    # 组排序
    #
    result_list.sort(
        key=lambda x: (
            x["region"],
            x["operator"]
        )
    )

    return {

        #
        # 总活跃源
        #
        "totalActiveHeads": len(rows),

        #
        # 分组数
        #
        "totalGroups": len(result_list),

        #
        # 数据
        #
        "groups": result_list
    }


@router.post("/iptv/{source_id}/test-delay")
async def api_test_delay(source_id: int):
    """测试单个活源延迟，更新数据库并返回最新延迟"""
    with get_iptv_db() as conn:
        row = conn.execute("SELECT * FROM iptv_list WHERE id=?", (source_id,)).fetchone()

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
                    with get_iptv_db() as conn:
                        conn.execute(
                            "UPDATE iptv_list SET delay=?, updateTime=? WHERE id=?",
                            (delay, now, source_id)
                        )
                    logger.info(f"✅ [延迟测试] id={source_id} -> {delay}ms")
                    return {"ok": True, "delay": delay}
    except Exception as e:
        logger.warning(f"⚠️ [延迟测试失败] id={source_id} -> {e}")

    now = int(time.time() * 1000)
    with get_iptv_db() as conn:
        conn.execute(
            "UPDATE iptv_list SET delay=?, updateTime=? WHERE id=?",
            (-1, now, source_id)
        )
    return {"ok": False, "delay": -1}


@router.delete("/iptv/{source_id}")
def api_delete_iptv_source(source_id: int):
    """删除单个组播源"""
    with get_iptv_db() as conn:
        row = conn.execute("SELECT host FROM iptv_list WHERE id=?", (source_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "源不存在"}
        host = row["host"]
        conn.execute("DELETE FROM iptv_list WHERE id=?", (source_id,))
        logger.info(f"🗑️ [删除组播源] id={source_id}, host={host}")
    return {"ok": True}
