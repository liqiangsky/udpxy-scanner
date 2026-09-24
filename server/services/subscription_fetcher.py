"""通用 API 订阅获取器"""
import aiohttp
import logging
import re
from typing import List

logger = logging.getLogger("订阅拉取")


async def fetch_subscription(name: str, uid: str, url: str, session: aiohttp.ClientSession = None) -> List[dict]:
    """从 API（JSON）订阅拉取 host 列表。uid 仅用于日志标识。"""
    # URL 为空时直接返回，避免对空 URL 发起无意义请求
    if not url:
        logger.info(f"⏭️ [订阅:{name}] URL 为空，跳过拉取")
        return []

    logger.info(f"📡 [订阅:{name}] 开始拉取: {url}")

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    try:
        async with session.get(
                url,
                headers={"User-Agent": "udpxy-scanner/1.0"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
            if resp.status != 200:
                logger.warning(f"⚠️ [订阅:{name}] 请求失败，状态码: {resp.status}")
                return []

            result = await resp.json()

        hosts_data = (result or {}).get("hosts", [])
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
    finally:
        if own_session:
            await session.close()


async def fetch_text_subscription(name: str, url: str, session: aiohttp.ClientSession = None) -> List[dict]:
    """从文本格式（m3u/txt）订阅中提取主机，不含协议头"""
    if not url:
        logger.info(f"⏭️ [订阅:{name}] URL 为空，跳过拉取")
        return []

    logger.info(f"📡 [订阅:{name}] 开始拉取文本格式: {url}")

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    try:
        async with session.get(
            url,
            headers={"User-Agent": "udpxy-scanner/1.0"},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                logger.warning(f"⚠️ [订阅:{name}] 请求失败，状态码: {resp.status}")
                return []

            text = await resp.text()

        # 匹配 https?://host[:port]/(rtp|udp)/
        pattern = re.compile(r'https?://([^/\s]+)/(?:rtp|udp)/')
        hosts = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = pattern.search(line)
            if m:
                hosts.add(m.group(1))

        raw_sources = [{"host": h} for h in sorted(hosts)]
        logger.info(f"📄 [订阅:{name}] -> {len(raw_sources)} 条")
        return raw_sources

    except Exception as e:
        logger.error(f"❌ [订阅:{name}] 请求异常: {e}")
        return []
    finally:
        if own_session:
            await session.close()


async def fetch_subscription_by_type(
    name: str, uid: str, url: str, sub_type: str = "api",
    session: aiohttp.ClientSession = None,
) -> List[dict]:
    """根据订阅类型分发到对应的拉取函数（session 可选共享连接池）"""
    if sub_type == "text":
        return await fetch_text_subscription(name, url, session=session)
    else:
        return await fetch_subscription(name, uid, url, session=session)

