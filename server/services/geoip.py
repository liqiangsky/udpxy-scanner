import aiohttp
import logging
import asyncio

logger = logging.getLogger("udpxy_scanner")

async def _health_check_batch(session: aiohttp.ClientSession, hosts: list[dict], concurrency: int = 64) -> list[dict]:
    """健康检查：请求 http://HOST/status，响应包含 "udpxy status" 的认为有效"""
    if not hosts:
        return []

    sem = asyncio.Semaphore(concurrency)
    valid = []

    async def check_entry(entry):
        async with sem:
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


async def query_geoip(session: aiohttp.ClientSession, ip: str) -> dict:
    url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("status") == "fail":
                    logger.info(f"⚠️ [geoip] {ip} API 失败: {data.get('message', 'unknown')}")
                    return {"region": "", "operator": "", "countryCode": ""}
                # 排除国外IP（只保留中国）
                country_code = data.get("countryCode", "")
                if country_code != "CN":
                    logger.info(f"🌍 [geoip] {ip} 国外IP({country_code})，已排除")
                    return {"region": "", "operator": "", "countryCode": country_code, "is_foreign": True}
                result = {
                    "region": data.get("regionName", "").replace("省", "").replace("市", ""),
                    "operator": data.get("isp", ""),
                    "countryCode": country_code
                }
                logger.info(f"🌍 [geoip] {ip} -> {result}")
                return result
            else:
                logger.debug(f"🌍 [geoip] {ip} HTTP {resp.status}")
                return {"region": "", "operator": "", "countryCode": ""}
    except Exception as e:
        logger.debug(f"🌍 [geoip] {ip} 异常: {e}")
        return {"region": "", "operator": "", "countryCode": ""}


async def enrich_geo_batch(session: aiohttp.ClientSession, sources: list[dict]) -> list[dict]:
    """批量富化 geo 信息：对缺少 geoRegion/geoOperator 的 host 条目进行 geoip 查询
    保留原始字段（如 delay、protocol 等），只追加 geo 信息。
    查询前先检查 source_cache 预填充，避免重复 API 调用。
    """
    from services.source_cache import get_cached_geo

    # 健康检查先行：过滤无效 host，避免浪费 geo API 配额
    sources = await _health_check_batch(session, sources)
    if not sources:
        return []

    enriched = []
    queried_count = 0
    skipped_count = 0
    cache_hit_count = 0
    foreign_count = 0

    for item in sources:
        host = item.get("host", "")

        if item.get("geoRegion") or item.get("geoOperator"):
            skipped_count += 1
            enriched.append(item)
            continue

        # 先查 source_cache 预填充
        cached = get_cached_geo(host)
        if cached and (cached.get("geoRegion") or cached.get("geoOperator")):
            enriched.append({
                **item,
                "geoRegion": cached.get("geoRegion", ""),
                "geoOperator": cached.get("geoOperator", "")
            })
            cache_hit_count += 1
            continue

        # 缓存未命中，走 geoip API
        # ip-api.com 免费版上限 45 次/分钟，间隔 1.5s 避免被限流
        await asyncio.sleep(1.5)
        ip_part = host.rsplit(":", 1)[0] if ":" in host else host
        geo = await query_geoip(session, ip_part)
        # 排除国外IP
        if geo.get("is_foreign"):
            foreign_count += 1
            continue
        region_val = geo.get("region", "")
        operator_val = geo.get("operator", "")
        queried_count += 1
        enriched.append({
            **item,
            "geoRegion": region_val,
            "geoOperator": operator_val
        })

    logger.info(f"🌍 [geoip富化] 共 {len(sources)} 条, 缓存命中 {cache_hit_count} 条, API查询 {queried_count} 条, 已有geo跳过 {skipped_count} 条, 国外IP排除 {foreign_count} 条")
    return enriched
