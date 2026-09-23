# services/source_cache.py
"""
公共缓存表 cache 读写工具
"""
import logging
import time
from typing import List
from db.database import get_db, db_write_lock
from db.models import Cache, Host

logger = logging.getLogger("数据缓存")

from services.regions import MAINLAND_REGIONS as _CN_REGIONS


def cache_sources(uid: str, sources: List[dict]) -> int:
    """将富化后的 host 批量写入 cache（ON CONFLICT upsert）。

    host 全局唯一（uq_cache_host 约束）：
    - 新 host：插入，归属当前 uid
    - 已存在 host：什么都不更新——host 归属首次写入它的 uid，
      后续任何订阅（同 uid 或其他 uid）拉到都不重复写、不重复探测

    进程内多路写走 db_write_lock 互斥；upsert 是对任何绕过进程锁路径的
    第二道防线（并发插入同 host 不再抛 UniqueViolation，也不再产生重复行）。
    """
    if not sources:
        return 0

    now = int(time.time())

    with db_write_lock:
        with get_db() as session:
            seen = set()
            rows = []
            for s in sources:
                host = s.get("host", "")
                if not host or host in seen:
                    continue
                region = s.get("geoRegion", "")
                if not region or region not in _CN_REGIONS:
                    continue
                seen.add(host)
                rows.append({
                    "uid": uid,
                    "host": host,
                    "geo_region": region,
                    "geo_operator": s.get("geoOperator", ""),
                    "status": 1,
                    "created_at": now,
                    "updated_at": now,
                })

            if not rows:
                return 0

            from sqlalchemy.dialects.postgresql import insert

            insert_stmt = insert(Cache).values(rows)
            insert_stmt = insert_stmt.on_conflict_do_nothing(
                index_elements=[Cache.host]
            )
            result = session.execute(insert_stmt)
            count = result.rowcount or 0
            session.commit()

            if count:
                regions = set(r["geo_region"] for r in rows)
                logger.info(f"💾 {uid} 写入 {count} 条, 地区分布: {regions}")

    return count

def get_cached_hosts(uid: str, region: str = "") -> List[str]:
    with get_db() as session:
        query = session.query(Cache.host).filter(Cache.uid == uid)
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


def get_existing_cache_hosts(hosts: List[str], chunk_size: int = 500) -> set:
    """批量查询 cache 中已存在的 host（前置去重用）"""
    if not hosts:
        return set()
    result = set()
    with get_db() as session:
        valid = [h for h in hosts if h]
        for i in range(0, len(valid), chunk_size):
            chunk = valid[i:i + chunk_size]
            rows = session.query(Cache.host).filter(Cache.host.in_(chunk)).all()
            result.update(r.host for r in rows)
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
    """扫描入库时同步 geo 信息到 cache（ON CONFLICT upsert）。

    已存在的 host 补齐 geo（首次拿到 geo 的 host 此处落库）；
    不动 uid/created_at——归属与创建时间保持首写时的值。
    """
    if not rows:
        return
    now = int(time.time())
    with db_write_lock:
        with get_db() as session:
            values = [
                {
                    "uid": uid,
                    "host": host,
                    "geo_region": geo_region,
                    "geo_operator": geo_operator,
                    "status": 0,
                    "created_at": now,
                    "updated_at": now,
                }
                for uid, host, geo_region, geo_operator in rows
            ]
            from sqlalchemy.dialects.postgresql import insert

            insert_stmt = insert(Cache).values(values)
            insert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=[Cache.host],
                set_={
                    "geo_region": insert_stmt.excluded.geo_region,
                    "geo_operator": insert_stmt.excluded.geo_operator,
                    "updated_at": insert_stmt.excluded.updated_at,
                },
            )
            session.execute(insert_stmt)
            session.commit()


async def process_source_data(
    uid: str,
    hosts: List[dict],
    session=None,
    probe_sem=None,
    should_cancel=None,
) -> int:
    """订阅数据处理：前置去重 -> geo富化（排除国外） -> 健康检查（共享槽位） -> 写入 cache。

    - 前置去重：已在 cache 中的 host 直接跳过，不产生健康检查探测流量
    - session / probe_sem：共享 aiohttp 会话与全局探测信号量（所有订阅共抢槽位），不传则自建
    - should_cancel：取消回调（如订阅被提前终止），在拿到槽位后检查——
      未发起的请求放弃，已验证完成的结果照常入库（探测成本已花，不丢弃）
    """
    from services.geoip import enrich_geo_batch

    if not hosts:
        return 0

    # 前置去重：只处理 cache 中不存在的新 host，重复拉取不再重复探测
    existing = get_existing_cache_hosts([h.get("host", "") for h in hosts])
    new_hosts = [h for h in hosts if h.get("host", "") and h["host"] not in existing]

    skipped = len(hosts) - len(new_hosts)
    logger.info(f"🌐 {uid} 前置去重：新 {len(new_hosts)} 条，已存在跳过 {skipped} 条")

    if not new_hosts:
        return 0

    logger.info(f"🌐 {uid} 开始 geoip 富化（{len(new_hosts)} 条）")

    enriched = await enrich_geo_batch(
        new_hosts, session=session, should_cancel=should_cancel, probe_sem=probe_sem
    )

    # 提前终止：不再发起新请求，但已完成富化/验证的部分照常入库（探测成本已花，丢弃才浪费）
    partial = bool(should_cancel and should_cancel())
    if partial:
        logger.info(f"⛔ {uid} 已终止，停止后续请求，{len(enriched)} 条进入入库流程")

    logger.info(f"✅ {uid} geoip 富化完成，{len(enriched)} 条待入库")

    # cache_sources 内部会过滤无效地区（如 DNS 解析失败无 geo 的项），返回真实入库数
    inserted = cache_sources(uid, enriched) if enriched else 0

    if partial:
        logger.info(f"⛔ {uid} 提前终止完成，实际入库 {inserted} 条")

    return inserted
