# services/validator.py
import aiohttp
import asyncio
import time
from typing import Optional

async def verify_single_host(session: aiohttp.ClientSession, host: str, target_addr: str, timeout_sec: float, should_stop_func, protocol: str = None) -> Optional[dict]:
    protocols = [protocol.lower().strip()] if protocol else ["rtp", "udp"]
    for proto in protocols:
        if should_stop_func(): return None
        test_url = f"http://{host}/{proto}/{target_addr}"
        try:
            start_time = time.time()
            async with session.get(test_url, timeout=aiohttp.ClientTimeout(total=timeout_sec, connect=5)) as resp:
                if resp.status == 200:
                    # 流数据可能需要时间才开始传输，重试读取
                    for attempt in range(3):
                        chunk = await resp.content.read(512)
                        if chunk:
                            delay = int((time.time() - start_time) * 1000)
                            return {"url": test_url, "protocol": proto, "delay": delay}
                        await asyncio.sleep(0.5)
        except Exception:
            continue
    return None
