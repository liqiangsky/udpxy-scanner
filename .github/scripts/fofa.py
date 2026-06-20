"""
FOFA 爬虫 — 通过 Playwright 渲染 SPA 页面，提取 HOST 并推送回后端

注意：未登录 FOFA 只能看到第一页（约 50-100 条），无需翻页逻辑。
"""
import os
import re
import asyncio
import logging

from playwright.async_api import async_playwright, TimeoutError as PwTimeout
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fofa_scanner")

# ── 环境变量 ──────────────────────────────────────────────
PUSH_CALLBACK_URL = os.getenv("PUSH_CALLBACK_URL", "")
PUSH_API_KEY = os.getenv("PUSH_API_KEY", "")

# 数据来源
SOURCE_TYPE = "fofa"
SOURCE_NAME = "FOFA"

# FOFA 搜索 qbase64（可通过环境变量覆盖，默认搜索 udpxy）
FOFA_QBASE64 = os.getenv(
    "FOFA_QBASE64",
    # country="CN" && udpxy && Content-Type: application/octet-stream
    "Y291bnRyeT0iQ04iICYmIHVkcHh5ICYmIENvbnRlbnQtVHlwZTogYXBwbGljYXRpb24vb2N0ZXQtc3RyZWFt"
    # country="CN" && udpxy && Content-Type: application/octet-stream && region="Hubei"
)
FOFA_URL = f"https://fofa.so/result?qbase64={FOFA_QBASE64}"

# ── 常量 ──────────────────────────────────────────────────
# 匹配 IP:PORT 或 域名:PORT
# 捕获组1 = host（IP 或域名），捕获组2 = port
HOST_RE = re.compile(
    r"(?<![\w\-])"  # 前面不能是字母/数字/连字符
    r"((?:\d{1,3}\.){3}\d{1,3}|[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)"  # IP 或 域名
    r"\:"  # 冒号分隔
    r"(\d{1,5})"  # port
    r"(?![\d:])"  # 后面不能紧跟数字或冒号
)

# 内网前缀过滤
PRIVATE_PREFIXES = (
    "127.", "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "0.", "169.254.",
)
LOCAL_HOSTNAMES = ("localhost",)


def is_private(host: str) -> bool:
    h = host.lower()
    if h in LOCAL_HOSTNAMES:
        return True
    if h.startswith(PRIVATE_PREFIXES):
        return True
    return False


def extract_hosts_from_text(text: str) -> set:
    """从页面文本中提取所有 HOST:PORT（IP 或域名均可）"""
    hosts = set()
    for host, port in HOST_RE.findall(text):
        if not is_private(host):
            hosts.add(f"{host}:{port}")
    return hosts


async def extract_hosts_from_page(page) -> set:
    """通过多种方式从当前页面提取 HOST"""
    # 方案 1: 直接通过 JS 获取所有可见文本，正则匹配 IP:Port
    try:
        body_text = await page.evaluate("() => document.body.innerText")
        hosts = extract_hosts_from_text(body_text)
        if hosts:
            return hosts
    except Exception as e:
        logger.debug(f"方案 1 失败: {e}")

    # 方案 2: 查找 FOFA 典型的结果容器
    try:
        selectors = [
            "td a[href*=':']",           # 表格中的链接
            ".list-cell .ip-address",     # FOFA 经典列表
            "[class*=host]",              # 包含 host 的类名
            "[class*=ip]",                # 包含 ip 的类名
            ".ant-table-tbody td",        # Ant Design 表格
            "[class*=result]",            # 通用结果容器
        ]
        for sel in selectors:
            els = await page.query_selector_all(sel)
            if els:
                texts = await asyncio.gather(*(el.inner_text() for el in els))
                joined = " ".join(texts)
                hosts = extract_hosts_from_text(joined)
                if hosts:
                    return hosts
    except Exception as e:
        logger.debug(f"方案 2 失败: {e}")

    return set()


async def scrape_fofa() -> list:
    """主爬取逻辑：打开 FOFA 页面提取 HOST"""
    logger.info(f"🌐 [FOFA] 启动 Playwright Chromium → {FOFA_URL}")
    all_hosts = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        try:
            # 访问 FOFA 搜索页
            logger.info(f"📄 [FOFA] 正在加载页面...")
            await page.goto(FOFA_URL, timeout=60000, wait_until="domcontentloaded")

            # 等待结果渲染完成（最多 30 秒）
            try:
                await page.wait_for_function(
                    "() => document.body.innerText.length > 200",
                    timeout=30000,
                )
            except PwTimeout:
                logger.warning("⚠️ [FOFA] 页面加载超时，尝试提取已有内容")

            # 额外等待 SPA 渲染
            await page.wait_for_timeout(3000)

            # 提取 HOST
            page_hosts = await extract_hosts_from_page(page)
            if not page_hosts:
                logger.warning("⚠️ [FOFA] 未提取到 Host，可能页面结构变了")
                snippet = await page.evaluate("() => document.body.innerText.slice(0, 500)")
                logger.debug(f"   页面文本片段: {repr(snippet)}")
            else:
                all_hosts.update(page_hosts)

        except Exception as e:
            logger.error(f"❌ [FOFA] 爬取异常: {e}")
        finally:
            await context.close()
            await browser.close()

    logger.info(f"📊 [FOFA] 共得到 {len(all_hosts)} 个 Host")
    return list(all_hosts)


async def push_to_backend(session: aiohttp.ClientSession, hosts: list):
    """推送到后端"""
    if not hosts:
        logger.warning("⚠️ [推送] Host 列表为空，跳过")
        return

    payload = {
        "sourceType": SOURCE_TYPE,
        "sourceName": SOURCE_NAME,
        "hosts": [{"host": h} for h in hosts],
    }
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": PUSH_API_KEY,
    }

    logger.info(f"🚀 [推送] 正在推送 {len(hosts)} 个 Host 到后端...")
    try:
        async with session.post(
            PUSH_CALLBACK_URL, json=payload, headers=headers, timeout=30
        ) as resp:
            if resp.status in (200, 201, 202):
                logger.info(f"✅ [推送] 成功 (HTTP {resp.status})")
            else:
                logger.error(f"❌ [推送] 失败 (HTTP {resp.status})")
                body = await resp.text()
                logger.error(f"   响应: {body[:200]}")
    except Exception as e:
        logger.error(f"❌ [推送] 网络异常: {e}")


async def main():
    logger.info("🚀 FOFA 爬虫作业启动")

    # 参数检查
    if not PUSH_CALLBACK_URL:
        logger.error("❌ 未设置 PUSH_CALLBACK_URL 环境变量")
        return
    if not PUSH_API_KEY:
        logger.error("❌ 未设置 PUSH_API_KEY 环境变量")
        return

    # 1. 爬取
    hosts = await scrape_fofa()

    # 2. 推送
    async with aiohttp.ClientSession() as session:
        await push_to_backend(session, hosts)

    logger.info("🏁 FOFA 爬虫作业结束")


if __name__ == "__main__":
    asyncio.run(main())
