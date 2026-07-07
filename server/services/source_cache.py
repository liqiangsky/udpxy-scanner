# services/source_cache.py
"""
公共缓存表 cache 读写工具
"""
import logging
import time
from typing import List, Optional
from db.database import get_db

logger = logging.getLogger("数据缓存")

from services.regions import MAINLAND_REGIONS as _CN_REGIONS


def cache_sources(source_type: str, sources: List[dict]):
    if not sources:
        return

    now = int(time.time())

    with get_db() as conn:
        seen = set()
        rows = []
        for s in sources:
            if s["host"] in seen:
                continue
            region = s.get("geoRegion", "")
            if not region or region not in _CN_REGIONS:
                continue
            seen.add(s["host"])
            rows.append((source_type, s["host"], region, s.get("geoOperator", ""), 1, now, now))

        if rows:
            conn.executemany(
                "INSERT OR IGNORE INTO cache (sourceType, host, geoRegion, geoOperator, status, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows
            )
            regions = set(r[2] for r in rows)
            logger.info(f"💾 {source_type} 写入 {len(rows)} 条, 地区分布: {regions}")


def get_cached_hosts(source_type: str, region: str = "") -> List[str]:
    with get_db() as conn:
        if region:
            rows = conn.execute(
                "SELECT DISTINCT host FROM cache WHERE sourceType=? AND geoRegion=?",
                (source_type, region)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT host FROM cache WHERE sourceType=?",
                (source_type,)
            ).fetchall()
        return [r["host"] for r in rows]


def get_cached_geo_batch(hosts: List[str], chunk_size: int = 500) -> dict:
    if not hosts:
        return {}
    result = {}
    with get_db() as conn:
        for i in range(0, len(hosts), chunk_size):
            chunk = hosts[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT host, geoRegion, geoOperator FROM cache WHERE host IN ({placeholders})",
                chunk
            ).fetchall()
            for row in rows:
                if row["geoRegion"] or row["geoOperator"]:
                    result[row["host"]] = {"geoRegion": row["geoRegion"], "geoOperator": row["geoOperator"]}
    return result


def get_existing_hosts_batch(hosts: List[str], chunk_size: int = 500) -> set:
    if not hosts:
        return set()
    result = set()
    with get_db() as conn:
        for i in range(0, len(hosts), chunk_size):
            chunk = hosts[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT DISTINCT host FROM host WHERE host IN ({placeholders})",
                chunk
            ).fetchall()
            result.update(row["host"] for row in rows)
    return result


def cache_host_geo_batch(rows: list):
    if not rows:
        return
    now = int(time.time())
    batch_rows = [r + (1, now, now) for r in rows]
    with get_db() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO cache (sourceType, host, geoRegion, geoOperator, status, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?)",
            batch_rows
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
