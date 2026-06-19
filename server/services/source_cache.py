# services/source_cache.py
"""
公共缓存表 source_cache 读写工具
"""
import logging
from typing import List, Optional
from db.database import get_cache_db

logger = logging.getLogger("数据缓存")

_CN_REGIONS = {
    "北京", "上海", "天津", "重庆",
    "浙江", "江苏", "广东", "山东",
    "安徽", "福建", "湖北", "湖南",
    "河南", "河北", "江西", "山西",
    "四川", "云南", "贵州", "西藏",
    "陕西", "甘肃", "青海", "宁夏",
    "新疆", "黑龙江", "吉林", "辽宁",
    "广西", "内蒙古", "海南"
}


def cache_sources(source_type: str, sources: List[dict]):
    if not sources:
        return

    with get_cache_db() as conn:
        seen = set()
        rows = []
        for s in sources:
            if s["host"] in seen:
                continue
            region = s.get("geoRegion", "")
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
            logger.info(f"💾 {source_type} 写入 {len(rows)} 条, 地区分布: {regions}")


def get_cached_hosts(source_type: str, region: str = "") -> List[str]:
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


def get_cached_geo_batch(hosts: List[str]) -> dict:
    if not hosts:
        return {}
    with get_cache_db() as conn:
        placeholders = ",".join("?" for _ in hosts)
        rows = conn.execute(
            f"SELECT host, geoRegion, geoOperator FROM source_cache WHERE host IN ({placeholders})",
            hosts
        ).fetchall()
        result = {}
        for row in rows:
            if row["geoRegion"] or row["geoOperator"]:
                result[row["host"]] = {"geoRegion": row["geoRegion"], "geoOperator": row["geoOperator"]}
        return result


def get_existing_iptv_hosts_batch(hosts: List[str]) -> set:
    if not hosts:
        return set()
    from db.database import get_iptv_db
    with get_iptv_db() as conn:
        placeholders = ",".join("?" for _ in hosts)
        rows = conn.execute(
            f"SELECT DISTINCT host FROM iptv_list WHERE host IN ({placeholders})",
            hosts
        ).fetchall()
        return {row["host"] for row in rows}


def cache_host_geo(source_type: str, host: str, geo_region: str, geo_operator: str):
    with get_cache_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO source_cache (sourceType, host, geoRegion, geoOperator) VALUES (?, ?, ?, ?)",
            (source_type, host, geo_region, geo_operator)
        )


async def process_source_data(source_type: str, hosts: List[dict]) -> int:
    from services.geoip import enrich_geo_batch

    if not hosts:
        return 0

    logger.info(f"🌐 {source_type} 开始 geoip 富化（{len(hosts)} 条）")

    enriched = await enrich_geo_batch(hosts)

    logger.info(f"✅ {source_type} geoip 富化完成，写入 {len(enriched)} 条")

    if enriched:
        cache_sources(source_type, enriched)

    return len(enriched)
