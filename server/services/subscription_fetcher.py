"""通用 API 订阅获取器"""
import aiohttp
import logging
from typing import List
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

logger = logging.getLogger("订阅拉取")


async def fetch_subscription(name: str, uid: str, url: str) -> List[dict]:
    """
    请求订阅 URL，自动追加 sourceType 和 sourceName 参数。
    期望格式：{"sourceType": "...", "sourceName": "...", "hosts": [{"host": "ip:port"}, ...]}
    返回原始 host 列表（不含 geoip 富化，由调用方统一处理）。
    """
    # 追加查询参数
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["sourceType"] = [uid]
    qs["sourceName"] = [name]
    new_qs = urlencode(qs, doseq=True)
    fetch_url = urlunparse(parsed._replace(query=new_qs))

    logger.info(f"📡 [订阅:{name}] 开始拉取: {fetch_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                fetch_url,
                headers={"User-Agent": "udpxy-scanner/1.0"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"⚠️ [订阅:{name}] 请求失败，状态码: {resp.status}")
                    return []

                result = await resp.json()

            hosts_data = result.get("hosts", [])
            if not hosts_data:
                logger.warning(f"⚠️ [订阅:{name}] 返回 hosts 为空")
                return []

            raw_sources = []
            for item in hosts_data:
                host_val = item.get("host", "")
                if host_val:
                    raw_sources.append({
                        "host": host_val,
                        "geoRegion": item.get("geoRegion", ""),
                        "geoOperator": item.get("geoOperator", "")
                    })

            logger.info(f"📄 [订阅:{name}] -> {len(raw_sources)} 条")
            return raw_sources

    except Exception as e:
        logger.error(f"❌ [订阅:{name}] 请求异常: {e}")
        return []