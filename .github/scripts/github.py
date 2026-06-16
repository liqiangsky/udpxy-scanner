import os
import re
import sys
import asyncio
import json
import logging
import aiohttp
from datetime import datetime, timedelta

# 1. 初始化日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("github_scanner")

# 2. 从 GitHub Action 环境变量中获取动态参数
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN", "")  # 必须配置，否则搜索 API 额度极低且无法翻页

# 💡 你的后端推送回调配置
PUSH_CALLBACK_URL = os.getenv("PUSH_CALLBACK_URL", "")
PUSH_API_KEY = os.getenv("PUSH_API_KEY", "")

# 数据来源
SOURCE_TYPE = "github"
SOURCE_NAME = "GitHub"

# 3. 核心配置与正则常量
GITHUB_PER_PAGE = 100
URL_PATTERN = re.compile(r'https?://([^/\s]+)/(rtp|udp)/([^\s"\']+)', re.IGNORECASE)
PRIVATE_PATTERNS = ["127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]"]

# 搜索关键词列表 将 JSON 字符串还原为 Python 的 list 列表
PREFETCH_QUERIES = json.loads(os.getenv("PREFETCH_QUERIES"))

def is_private_ip(host_lower: str) -> bool:
    """过滤内网死源或本地回环地址"""
    if any(p in host_lower for p in PRIVATE_PATTERNS):
        return True
    if host_lower.startswith("192.168.") or host_lower.startswith("10."):
        return True
    if host_lower.startswith("172."):
        parts = host_lower.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return True
            except ValueError:
                pass
    return False

async def parse_file_hosts(session: aiohttp.ClientSession, html_url: str) -> set:
    """下载文件并提取里面的 IP:Port (Hosts)"""
    hosts = set()
    try:
        # 将标准页面转换为 raw 地址
        raw_url = html_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        async with session.get(raw_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                content = await resp.text(errors='ignore')
                for match in URL_PATTERN.finditer(content):
                    host_raw = match.group(1)
                    host_lower = host_raw.lower()
                    if is_private_ip(host_lower):
                        continue
                    hosts.add(host_lower)
    except Exception as e:
        logger.debug(f"⚠️ [解析文件失败] {html_url}: {e}")
    return hosts

async def fetch_search_page(session: aiohttp.ClientSession, headers: dict, query: str, page: int) -> list:
    """调用 GitHub Code Search API 获取单页搜索结果，带重试机制"""
    params = {
        "q": query,
        "per_page": str(GITHUB_PER_PAGE),
        "page": str(page),
        "sort": "updated",
        "order": "desc"
    }

    api_url = "https://api.github.com/search/code"
    max_retries = 3

    for retry in range(max_retries):
        try:
            async with session.get(api_url, headers=headers, params=params, timeout=15) as resp:
                # 触发 GitHub 严厉的次级频控处理
                if resp.status in (403, 429, 408):
                    delay = 45 if retry == 0 else 90  # 适当缩短虚拟机内等待，配合次级频控
                    logger.warning(f"⚠️ [GitHub频控] 触发 HTTP {resp.status}，在 Action 容器内安全休眠 {delay} 秒...")
                    await asyncio.sleep(delay)
                    continue

                if resp.status != 200:
                    logger.warning(f"⚠️ [GitHub异常] 关键词 [{query}] 第 {page} 页请求失败，状态码: {resp.status}")
                    return []

                data = await resp.json()
                return data.get("items", [])
        except Exception as e:
            logger.error(f"❌ [请求异常] 检索页码遭遇网络故障: {e}")
            await asyncio.sleep(10)

    return []

async def search_single_keyword(session: aiohttp.ClientSession, headers: dict, keyword: str, max_pages: int = 5) -> set:
    """搜索单个关键词，流水线处理：获取单页 -> 并发解析当前页文件 -> 翻页休眠"""
    logger.info(f"🔍 [全网扫描] 开始挖掘关键词: {keyword}")
    keyword_hosts = set()

    for page in range(1, max_pages + 1):
        items = await fetch_search_page(session, headers, keyword, page)
        if not items:
            logger.info(f"📄 [扫描反馈] 关键词 [{keyword}] 第 {page} 页未匹配到有效代码条目，终止本词追踪。")
            break

        logger.info(f"📄 [扫描反馈] 关键词 [{keyword}] 第 {page} 页 -> 成功锁定 {len(items)} 个目标源码文件")

        # 收集该页中所有文件的 html_url
        file_urls = [item["html_url"] for item in items if "html_url" in item]

        # 🚀 在 GitHub 强劲的网速下，利用 asyncio 并发榨取这一页所有的文件内容
        logger.info(f"⏳ [流水线解析] 正在并发剥离这 {len(file_urls)} 个文件的有效 IP 资产...")
        parse_tasks = [parse_file_hosts(session, url) for url in file_urls]
        page_hosts_results = await asyncio.gather(*parse_tasks, return_exceptions=True)

        for result in page_hosts_results:
            if isinstance(result, set):
                keyword_hosts.update(result)

        logger.info(f"✅ [小结] 关键词 [{keyword}] 已推进至第 {page} 页，当前词累计榨出 {len(keyword_hosts)} 个 Host。")

        # 如果返回数量少于满页，说明触底
        if len(items) < GITHUB_PER_PAGE:
            logger.info(f"📄 [扫描反馈] 关键词 [{keyword}] 已安全到达 GitHub 数据流底部。")
            break

        # 规避 GitHub 单次滥用频控，翻页强行建立呼吸间隔（在 Action 里面跑，时间充裕，不用缩短）
        if page < max_pages:
            await asyncio.sleep(20)

    return keyword_hosts

async def push_to_backend(session: aiohttp.ClientSession, hosts_list: list):
    “””任务收尾：将去重资产分批（每批 500 个）回调投递给后端”””
    BATCH_SIZE = 500
    headers = {
        “Content-Type”: “application/json”,
        “X-API-Key”: PUSH_API_KEY,
        “X-Callback-Token”: “000”
    }

    total = len(hosts_list)
    for i in range(0, total, BATCH_SIZE):
        batch = hosts_list[i:i + BATCH_SIZE]
        payload = {
            “sourceType”: SOURCE_TYPE,
            “sourceName”: SOURCE_NAME,
            “hosts”: [{“host”: h} for h in batch]
        }

        batch_num = i // BATCH_SIZE + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

        try:
            logger.info(f”Authorization 格式对齐 -> 正在推送第 {batch_num}/{total_batches} 批（{len(batch)} 个资产）...”)

            async with session.post(PUSH_CALLBACK_URL, json=payload, headers=headers, timeout=30) as resp:
                if resp.status in [200, 201]:
                    logger.info(f”🚀 [批次 {batch_num}/{total_batches}] 后端已成功接收（状态码: {resp.status}）。”)
                else:
                    logger.error(f”🚨 后端回调节点响应异常，状态码: {resp.status}”)

        except Exception as e:
            logger.error(f”💥 第 {batch_num}/{total_batches} 批投递异常: {str(e)}”)

        # 批次间隔 1 秒，避免洪峰
        if i + BATCH_SIZE < total:
            await asyncio.sleep(1)

async def main():
    logger.info("🚀 IPTV 关键词级代码扫描全自动化作业正在初始化...")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "udpxy-radar-actions/1.0"
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
        logger.info("🔑 [身份鉴定] GitHub 访问令牌（PAT）注入成功，已解锁高频分页 API 权限。")
    else:
        logger.warning("🔑 [身份鉴定] 缺少环境变量 MY_GITHUB_TOKEN！Code Search API 将受到每分钟仅 10 次限制。")

    all_hosts = set()

    async with aiohttp.ClientSession() as session:
        # ===== 核心逻辑 1：轮询各个代码搜索关键词 =====
        for i, query in enumerate(PREFETCH_QUERIES):
            keyword_hosts = await search_single_keyword(session, headers, query, max_pages=5)
            all_hosts.update(keyword_hosts)

            # 关键词之间保持 60 秒以上的长呼吸，有效遏制 GitHub 的滥用保护机制触发
            if i < len(PREFETCH_QUERIES) - 1:
                logger.info("⏳ [安全隔离] 切换下一组关键词，强制策略隔离休眠 60 秒...")
                await asyncio.sleep(60)

        logger.info(f"📊 [阶段汇总] 全网多关键词搜索检索完成，共取得 {len(all_hosts)} 个不重复 HOST 资产。")

        # ===== 核心逻辑 2：资产输出与后端推送 =====
        hosts_list = list(all_hosts)
        if hosts_list:
            # 1. 此时直接调用，由于 push_to_backend 里面不再 await 响应的 body 内容，这里会执行得非常快
            await push_to_backend(session, hosts_list)

            # 2. 💡 绝妙保障：因为这是在 GitHub Actions 里，为防进程因执行结束被瞬间杀死导致操作系统还来不及将 TCP 缓存区的数据发出，
            # 这里强制给网卡 3 秒钟的清空时间，随后再关闭 ClientSession
            logger.info("⏳ [网络缓冲] 预留 3 秒网络管道排空缓冲，确保异步数据包完美离线...")
            await asyncio.sleep(3)
        else:
            logger.warning("⚠️ 扫描流程已圆满结束，但本次作业没有捕获到任何符合规则的有效 Host。放弃回调推送。")

    logger.info("🎉 [作业圆满结束] 本次 GitHub Actions 自动化扫描流水线完美收尾。")

if __name__ == "__main__":
    asyncio.run(main())
