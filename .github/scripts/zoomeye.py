"""
通用 GitHub Action 脚本：

1. Playwright 访问目标 URL（自动过加速乐等防护）
2. 从页面提取 JSON 数据
3. 内置 ZoomEye 数据清洗器（仅提取 host，去重后打包）
4. 写入数据文件（每行一个 host）
"""
import os
import sys
import json
import asyncio
import logging
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# 1. 初始化日志规范
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("zoomeye_scanner")

# 数据来源
SOURCE_TYPE = "zoomeye"
SOURCE_NAME = "钟馗之眼"

# 输出文件路径
OUTPUT_FILE = os.getenv("OUTPUT_FILE", ".github/data/zoomeye.txt")

# app="udpxy multicast UDP-to-HTTP" && country="中国"
SOURCE_URL = "https://www.zoomeye.ai/api/search?q=YXBwPSJ1ZHB4eSBtdWx0aWNhc3QgVURQLXRvLUhUVFAiICYmIGNvdW50cnk9IuS4reWbvSI%3D"
# "udpxy" && country="China" && "Content-Type: application/octet-stream"

# "udpxy" && country="China" && "Content-Type: application/octet-stream" && subdivisions="Hainan"


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


def write_hosts_to_file(hosts: list, output_path: str):
    """将主机列表写入文件，每行一个 host"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for host in sorted(hosts):
            f.write(host + "\n")
    logger.info(f"✅ [写入] 已将 {len(hosts)} 个 host 写入 {output_path}")


async def main():
    logger.info(f"🚀 ZoomEye 数据采集与清洗全自动化作业启动...")

    # 1. 通过 Playwright 抓取防爬下的原始 JSON
    raw_data = await fetch_via_playwright(SOURCE_URL)
    if not raw_data:
        logger.error("❌ 未抓取到有效数据，任务终止")
        return

    # 2. 调用内置的 ZoomEye 清洗器清洗数据
    cleaned_hosts = clean_zoomeye_data(raw_data)

    # 3. 写入数据文件
    write_hosts_to_file(cleaned_hosts, OUTPUT_FILE)

    logger.info("🏁 GitHub Action 爬取与清洗流程全自动化作业圆满结束。")


if __name__ == "__main__":
    asyncio.run(main())
