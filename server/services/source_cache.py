# services/source_cache.py
"""
公共缓存表 source_cache 读写工具
"""
import logging
from typing import List, Optional
from db.database import get_cache_db

logger = logging.getLogger("udpxy_scanner")

# 中国省份/地区白名单（含港澳台），用于过滤非国内 IP
_CN_REGIONS = {
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "台湾", "内蒙古", "广西", "西藏", "宁夏", "新疆",
    "香港", "澳门"
}


def cache_sources(source_type: str, sources: List[dict]):
    """
    将数据写入 source_cache 公共表。
    每个 source dict 至少包含 "host"，可选 "geoRegion", "geoOperator"。
    geoRegion 为空或不在中国省份白名单内的数据不入库。
    """
    if not sources:
        return

    with get_cache_db() as conn:
        seen = set()
        rows = []
        for s in sources:
            if s["host"] in seen:
                continue
            region = s.get("geoRegion", "")
            # 过滤：region 为空或国外
            if not region or region not in _CN_REGIONS:
                continue
            seen.add(s["host"])
            rows.append((source_type, s["host"], region, s.get("geoOperator", "")))

        if rows:
            conn.executemany(
                "INSERT OR IGNORE INTO source_cache (sourceType, host, geoRegion, geoOperator) VALUES (?, ?, ?, ?)",
                rows
            )
            regions = set(r[2] for r in rows)
            logger.info(f"💾 [source_cache] {source_type} 写入 {len(rows)} 条, 地区分布: {regions}")


def get_cached_hosts(source_type: str, region: str = "") -> List[str]:
    """
    从 source_cache 读取缓存 host 列表，按 geoRegion 过滤。
    """
    with get_cache_db() as conn:
        if region:
            rows = conn.execute(
                "SELECT DISTINCT host FROM source_cache WHERE sourceType=? AND geoRegion=?",
                (source_type, region)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT host FROM source_cache WHERE sourceType=?",
                (source_type,)
            ).fetchall()
        return [r["host"] for r in rows]


def get_cached_geo(host: str) -> dict | None:
    """
    查询单个 host 的缓存 geo 信息，不存在返回 None。
    """
    with get_cache_db() as conn:
        row = conn.execute(
            "SELECT geoRegion, geoOperator FROM source_cache WHERE host=?",
            (host,)
        ).fetchone()
        if row:
            return {"geoRegion": row["geoRegion"], "geoOperator": row["geoOperator"]}
        return None


def cache_host_geo(source_type: str, host: str, geo_region: str, geo_operator: str):
    """
    写入单个 host 的 geo 信息到 source_cache。
    """
    with get_cache_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO source_cache (sourceType, host, geoRegion, geoOperator) VALUES (?, ?, ?, ?)",
            (source_type, host, geo_region, geo_operator)
        )


async def process_source_data(source_type: str, hosts: List[dict]) -> int:
    """
    统一数据入库入口：geoip 富化 → 区域过滤 → 写入 source_cache。
    外部推送接口和订阅拉取都调用此函数。
    返回实际写入条数。
    """
    from services.geoip import enrich_geo_batch
    import aiohttp

    if not hosts:
        return 0

    async with aiohttp.ClientSession() as session:
        enriched = await enrich_geo_batch(session, hosts)

    if enriched:
        cache_sources(source_type, enriched)

    return len(enriched)
