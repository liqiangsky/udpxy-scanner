import aiohttp
import logging
import asyncio
import os
import ipaddress
import threading

import ip2region.searcher as xdb_searcher
import ip2region.util as xdb_util

from db.database import run_in_thread
from services.regions import MAINLAND_REGIONS

logger = logging.getLogger("GeoIP")

_XDB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ip2region_v4.xdb")
_searcher = None
_init_lock = threading.Lock()

def _get_searcher():
    global _searcher
    if _searcher is None:
        with _init_lock:
            if _searcher is None:
                if not os.path.exists(_XDB_PATH):
                    logger.warning(f"⚠️ [ip2region] xdb 文件不存在: {_XDB_PATH}")
                    return None
                try:
                    c_buffer = xdb_util.load_content_from_file(_XDB_PATH)
                    _searcher = xdb_searcher.new_with_buffer(xdb_util.IPv4, c_buffer)
                    logger.info(f"✅ [ip2region] 加载成功: {_XDB_PATH}")
                except Exception as e:
                    logger.error(f"❌ [ip2region] 加载失败: {e}")
                    return None
    return _searcher


def _is_ip_addr(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


async def _resolve_to_ip(host: str) -> str | None:
    ip_part = host.rsplit(":", 1)[0] if ":" in host else host
    if _is_ip_addr(ip_part):
        return ip_part
    try:
        loop = asyncio.get_running_loop()
        addrs = await loop.getaddrinfo(ip_part, None, family=2)
        for addr in addrs:
            return addr[4][0]
        return None
    except Exception as e:
        logger.debug(f"🌍 [DNS] {ip_part} 解析失败: {e}")
        return None


_PROVINCE_SUFFIXES = ("省", "市", "特别行政区")
_AUTONOMOUS_PREFIXES = {
    "内蒙古": "内蒙古",
    "广西": "广西",
    "西藏": "西藏",
    "宁夏": "宁夏",
    "新疆": "新疆",
}

def _normalize_province(raw: str) -> str:
    if not raw:
        return ""
    for prefix, short in _AUTONOMOUS_PREFIXES.items():
        if raw.startswith(prefix):
            return short
    if raw.endswith("自治区"):
        return raw[:-3]
    for suffix in _PROVINCE_SUFFIXES:
        if raw.endswith(suffix):
            return raw[:-len(suffix)]
    return raw


def _query_ip2region(ip: str) -> dict:
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            logger.info(f"🌍 [ip2region] {ip} 私有/内网IP，已排除")
            return {"region": "", "operator": "", "countryCode": "", "is_foreign": True}
    except ValueError:
        pass

    searcher = _get_searcher()
    if not searcher:
        return {"region": "", "operator": "", "countryCode": "", "is_foreign": True}
    try:
        region_str = searcher.search(ip)
        if not region_str:
            return {"region": "", "operator": "", "countryCode": "", "is_foreign": True}
        parts = region_str.split("|")
        if len(parts) < 5:
            return {"region": "", "operator": "", "countryCode": "", "is_foreign": True}
        country = parts[0]
        province_raw = parts[1]
        isp = parts[3]
        code = parts[4]
        if code != "CN" and country != "中国":
            logger.info(f"🌍 [ip2region] {ip} 国外IP({code})，已排除")
            return {"region": "", "operator": "", "countryCode": code, "is_foreign": True}
        region = _normalize_province(province_raw)
        if region not in MAINLAND_REGIONS:
            logger.info(f"🌍 [ip2region] {ip} 非大陆({province_raw}->{region})，已排除")
            return {"region": "", "operator": "", "countryCode": code, "is_foreign": True}
        operator = "" if isp == "0" else isp
        logger.info(f"🌍 [ip2region] {ip} -> {province_raw} | {operator}")
        return {"region": region, "operator": operator, "countryCode": code}
    except ValueError as e:
        logger.debug(f"🌍 [ip2region] {ip} 查询失败(非IPv4?): {e}")
        return {"region": "", "operator": "", "countryCode": "", "is_foreign": True}
    except Exception as e:
        logger.debug(f"🌍 [ip2region] {ip} 查询异常: {e}")
        return {"region": "", "operator": "", "countryCode": "", "is_foreign": True}


async def _health_check_batch(session: aiohttp.ClientSession, hosts: list[dict], should_cancel=None, probe_sem: asyncio.Semaphore = None) -> list[dict]:
    """udpxy 健康检查（真正的网络请求）。

    并发控制：所有订阅共享一个全局信号量（limit = 全局 concurrency 设置）
    + 底层共享连接池双重限流。空位先到先得，满了排队等待。
    should_cancel：取消回调，在【获得槽位、即将发请求前】检查——
    排队中的请求命中取消后立即放弃（不再发起），在途请求自然收尾，
    已验证完成的结果保留（由调用方入库）。"""
    if not hosts:
        return []

    # 固定 64：param 表的 concurrency 是扫描专用配置，订阅探测池独立于此
    sem = probe_sem or asyncio.Semaphore(64)
    valid = []

    async def check_entry(entry):
        async with sem:
            # 取消检查必须在拿到槽位之后：排队中的请求才能被拦截
            if should_cancel and should_cancel():
                return None
            host = entry["host"]
            try:
                status_url = f"http://{host}/status"
                async with session.get(status_url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        body = await r.text()
                        if "udpxy status" in body:
                            return entry
            except Exception:
                pass
            return None

    tasks = [check_entry(h) for h in hosts]
    results = await asyncio.gather(*tasks)
    valid = [r for r in results if r is not None]
    logger.info(f"🔍 [健康检查] {len(valid)}/{len(hosts)} 个有效")
    return valid


async def enrich_geo_batch(
    sources: list[dict],
    session: aiohttp.ClientSession = None,
    skip_health_check: bool = False,
    should_cancel=None,
    probe_sem: asyncio.Semaphore = None,
) -> list[dict]:
    """两阶段富化：先 geo（本地 xdb，零外网请求）排除国外/非大陆，
    再对国内主机做健康检查（真网络请求，全局共享槽位，支持逐请求取消）。"""
    from services.source_cache import get_cached_geo_batch

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    try:
        enriched = []
        queried_count = 0
        skipped_count = 0
        cache_hit_count = 0
        foreign_count = 0
        resolve_fail_count = 0

        # ---------- 阶段一：geo 富化（本地 xdb，零外网请求）----------
        # 先把国外/非大陆 IP 排掉，健康检查只打给国内主机，探测流量最小化
        need_geo_hosts = []
        for item in sources:
            if item.get("geoRegion") or item.get("geoOperator"):
                skipped_count += 1
                enriched.append(item)
            else:
                need_geo_hosts.append(item)

        if need_geo_hosts:
            host_keys = [item.get("host", "") for item in need_geo_hosts]
            cached_geo_map = get_cached_geo_batch(host_keys)

            still_need_query = []
            for item in need_geo_hosts:
                host = item.get("host", "")
                cached = cached_geo_map.get(host)
                if cached:
                    enriched.append({**item, **cached})
                    cache_hit_count += 1
                else:
                    still_need_query.append(item)

            if still_need_query:
                if should_cancel and should_cancel():
                    logger.info(f"🌍 [geoip富化] 已取消，{len(still_need_query)} 条未查询 geo")
                    return enriched

                resolve_tasks = [(_resolve_to_ip(item.get("host", "")), item) for item in still_need_query]
                resolve_results = await asyncio.gather(*(t[0] for t in resolve_tasks))

                mainland_items = []
                for idx, ip in enumerate(resolve_results):
                    item = resolve_tasks[idx][1]
                    if not ip:
                        # DNS 解析失败：无 IP 无法归属地区，直接丢弃
                        #（不进健康检查、不入库、不计入待入库数）
                        resolve_fail_count += 1
                        continue
                    geo = await run_in_thread(_query_ip2region, ip)
                    if geo.get("is_foreign"):
                        foreign_count += 1
                        continue  # 国外/非大陆：不进健康检查，不产生探测流量
                    mainland_items.append({
                        **item,
                        "geoRegion": geo.get("region", ""),
                        "geoOperator": geo.get("operator", ""),
                    })
                    queried_count += 1

                # ---------- 阶段二：健康检查（真网络请求）----------
                # 只探测国内主机；全局共享信号量 + 共享连接池双重限流，
                # 取消在拿到槽位后检查，未发起的放弃，已完成验证的有效结果保留
                mainland_valid = await _health_check_batch(
                    session, mainland_items, should_cancel=should_cancel, probe_sem=probe_sem
                )
                if len(mainland_items) != len(mainland_valid):
                    valid_hosts = {h["host"] for h in mainland_valid}
                    eliminated = len(mainland_items) - len(valid_hosts & {i["host"] for i in mainland_items})
                    logger.info(f"🔍 [健康检查淘汰] {eliminated} 个不可达主机")
                    enriched = [
                        e for e in enriched
                        if not any(e.get("host") == i["host"] for i in mainland_items) or e.get("host") in valid_hosts
                    ]
                enriched.extend(mainland_valid)

        logger.info(f"🌍 [geoip富化] 共 {len(sources)} 条, 缓存命中 {cache_hit_count} 条, 本地查询 {queried_count} 条, 已有geo跳过 {skipped_count} 条, 国外IP排除 {foreign_count} 条, DNS解析失败 {resolve_fail_count} 条")
        return enriched
    finally:
        if own_session:
            await session.close()
