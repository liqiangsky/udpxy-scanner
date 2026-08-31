# services/source_cache.py
"""
公共缓存表 cache 读写工具
"""
import logging
import time
from typing import List, Optional
from db.database import get_db, db_write_lock
from db.models import Cache, Host

logger = logging.getLogger("数据缓存")

from services.regions import MAINLAND_REGIONS as _CN_REGIONS


def cache_sources(source_type: str, sources: List[dict]):
    if not sources:
        return

    now = int(time.time())

    with db_write_lock:
        with get_db() as session:
            seen = set()
            count = 0
            for s in sources:
                if s["host"] in seen:
                    continue
                region = s.get("geoRegion", "")
                if not region or region not in _CN_REGIONS:
                    continue
                seen.add(s["host"])
                # 检查是否已存在
                existing = session.query(Cache).filter(Cache.host == s["host"]).first()
                if not existing:
                    cache_entry = Cache(
                        source_type=source_type,
                        host=s["host"],
                        geo_region=region,
                        geo_operator=s.get("geoOperator", ""),
                        status=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(cache_entry)
                    count += 1

            if count:
                session.commit()
                regions = set(s.get("geoRegion", "") for s in sources if s.get("geoRegion") and s.get("geoRegion") in _CN_REGIONS)
                logger.info(f"💾 {source_type} 写入 {count} 条, 地区分布: {regions}")


def get_cached_hosts(source_type: str, region: str = "") -> List[str]:
    with get_db() as session:
        query = session.query(Cache.host).filter(Cache.source_type == source_type)
        if region:
            query = query.filter(Cache.geo_region == region)
        return [r.host for r in query.distinct().all()]


def get_cached_geo_batch(hosts: List[str], chunk_size: int = 500) -> dict:
    if not hosts:
        return {}
    result = {}
    with get_db() as session:
        for i in range(0, len(hosts), chunk_size):
            chunk = hosts[i:i + chunk_size]
            rows = session.query(Cache).filter(Cache.host.in_(chunk)).all()
            for row in rows:
                if row.geo_region or row.geo_operator:
                    result[row.host] = {"geoRegion": row.geo_region, "geoOperator": row.geo_operator}
    return result


def get_existing_hosts_batch(hosts: List[str], chunk_size: int = 500) -> set:
    if not hosts:
        return set()
    result = set()
    with get_db() as session:
        for i in range(0, len(hosts), chunk_size):
            chunk = hosts[i:i + chunk_size]
            rows = session.query(Host.host).filter(Host.host.in_(chunk)).all()
            result.update(r.host for r in rows)
    return result


def cache_host_geo_batch(rows: list):
    if not rows:
        return
    now = int(time.time())
    with db_write_lock:
        with get_db() as session:
            for row in rows:
                source_type, host, geo_region, geo_operator = row
                existing = session.query(Cache).filter(Cache.host == host).first()
                if not existing:
                    cache_entry = Cache(
                        source_type=source_type,
                        host=host,
                        geo_region=geo_region,
                        geo_operator=geo_operator,
                        status=0,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(cache_entry)
            session.commit()


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
