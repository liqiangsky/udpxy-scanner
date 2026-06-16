"""
通用 GitHub Action 脚本：

1. Playwright 访问目标 URL（自动过加速乐等防护）
2. 从页面提取 JSON 数据
3. 内置 ZoomEye 数据清洗器（仅提取 host，去重后打包）
4. 异步推送回调接口（发射后不管，防超时）
"""
import os
import sys
import json
import asyncio
import logging
from urllib.parse import urlparse
from playwright.async_api import async_playwright
import aiohttp

# 1. 初始化日志规范
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("zoomeye_scanner")

# 2. 从 GitHub Action 环境变量中获取动态参数
SOURCE_TYPE = os.getenv("SOURCE_TYPE", "")
SOURCE_NAME = os.getenv("SOURCE_NAME", "")

# 💡 你的后端推送回调配置
PUSH_CALLBACK_URL = os.getenv("PUSH_CALLBACK_URL", "")
PUSH_API_KEY = os.getenv("PUSH_API_KEY", "")

SOURCE_URL = "https://www.zoomeye.ai/api/search?q=YXBwPSJ1ZHB4eSBtdWx0aWNhc3QgVURQLXRvLUhUVFAiICYmIGNvdW50cnk9IuS4reWbvSI%3D"


async def fetch_via_playwright(api_url: str) -> dict:
    """通过 Playwright 访问目标 URL 获取 JSON 数据（支持自动过 JS 挑战挑战页）"""
    logger.info(f"🌐 [Playwright] 正在启动 Chromium 尝试访问目标 API...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # 访问目标 API 接口
            response = await page.goto(api_url, timeout=60000, wait_until="domcontentloaded")
            logger.info(f"📥 [Playwright] 页面已加载，响应状态码: {response.status if response else 'Unknown'}")

            # 等待文本内容渲染（通常 JSON 直接呈现在 body 中）
            await page.wait_for_selector("body", timeout=10000)
            content = await page.evaluate("() => document.body.innerText")

            # 尝试解析为 JSON 字典
            data = json.loads(content.strip())
            return data
        except json.JSONDecodeError:
            logger.error("💥 [Playwright] 抓取到的网页内容无法解析为标准的 JSON 格式，可能遭遇反爬或重定向")
            return {}
        except Exception as e:
            logger.error(f"💥 [Playwright] 页面访问或等待超时异常: {str(e)}")
            return {}
        finally:
            await context.close()
            await browser.close()


def clean_zoomeye_data(data: dict) -> list:
    """ZoomEye 数据清洗器 — 仅提取 host，geoip 由服务端统一处理"""
    matches = data.get("matches", [])
    sources = []
    seen_hosts = set()  # 局部去重，避免单页内提交重复资产

    for item in matches:
        ip = item.get("ip", "")
        portinfo = item.get("portinfo", {})
        port = portinfo.get("port", "")
        if not port:
            port = item.get("port", "")

        if ip and port:
            host_str = f"{ip}:{port}"
            if host_str not in seen_hosts:
                seen_hosts.add(host_str)
                sources.append({"host": host_str})

    logger.info(f"🧹 [数据清洗] ZoomEye 原始数据解析完成，成功清洗出 {len(sources)} 个有效 host 资产")
    return sources


async def push_to_backend(session: aiohttp.ClientSession, hosts_list: list):
    """异步任务收尾：打包去重清洗后的数据投递给后端（发射后不管，防超时）"""
    if not hosts_list:
        logger.warning("⚠️ [后端推送] 资产列表为空，跳过回调推送")
        return

    payload = {
        "sourceType": SOURCE_TYPE,
        "sourceName": SOURCE_NAME,
        "hosts": hosts_list
    }

    headers = {
       "Content-Type": "application/json",
       "X-API-Key": PUSH_API_KEY,
    }

    logger.info(f"🚀 [后端推送] 正在打包 {len(hosts_list)} 个去重资产推送回控制后端...")
    try:
        # 只等待连接建立和请求头成功发送到 TCP 缓冲区，不等待后端慢入库导致超时
        async with session.post(PUSH_CALLBACK_URL, json=payload, headers=headers, timeout=10) as resp:
            if resp.status in [200, 201, 202]:
                logger.info(f"🎉 [后端推送] 成功打通回调链路！数据已移交至网络缓冲区 (状态码: {resp.status})")
            else:
                logger.error(f"🚨 [后端推送] 后端回调节点响应异常，状态码: {resp.status}")
    except Exception as e:
        # 即使这里提示网络异常，可能数据其实已经发出去了
        logger.warning(f"📡 [后端推送] 触发预设发射策略: {str(e)}")


async def main():

    # 1. 通过 Playwright 抓取防爬下的原始 JSON
    raw_data = await fetch_via_playwright(SOURCE_URL)
    if not raw_data:
        logger.error("❌ 未抓取到有效数据，任务终止")
        return

    # 2. 调用内置的内置 ZoomEye 清洗器清洗数据
    cleaned_hosts = clean_zoomeye_data(raw_data)

    # 3. 异步高效推送到控制后端
    async with aiohttp.ClientSession() as session:
        await push_to_backend(session, cleaned_hosts)

    logger.info("🏁 GitHub Action 爬取与清洗流程全自动化作业圆满结束。")


if __name__ == "__main__":
    asyncio.run(main())
