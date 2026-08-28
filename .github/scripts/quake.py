"""
360 Quake 测绘 API 扫描脚本
============================
- 每次触发仅调用 1 次 API（start:1, size:999）
- 解析结果，过滤内网，写入数据文件
- 由订阅调度器每 3 天触发一次，月均 ~10 次调用
- 完善的错误处理：API Key 校验、HTTP 异常、业务错误码、JSON 解析异常、配额超限
"""
import os
import sys
import asyncio
import json
import logging
import aiohttp
from datetime import datetime

# ──────────────────────────────────────────────
# 1. 日志初始化
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("quake_scanner")

# ──────────────────────────────────────────────
# 2. 环境变量配置
# ──────────────────────────────────────────────
QUAKE_API_KEY = os.getenv("QUAKE_API_KEY", "").strip()
QUERY = '(app:"udpxy multicast UDP-to-HTTP") AND country_cn: "中国"'
OUTPUT_FILE = os.getenv("OUTPUT_FILE", ".github/data/quake.txt")

# 数据源标识
SOURCE_TYPE = "360quake"
SOURCE_NAME = "360Quake"

# 分页与推送配置
PAGE_SIZE = 700
API_TIMEOUT = 30
MAX_RETRIES = 3

# 内网前缀过滤（含回环地址）
PRIVATE_PREFIXES = (
    "127.", "10.", "192.168.", "0.",
    "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.",
    "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "localhost", "::1", "[::1]", "0.0.0.0"
)


# ──────────────────────────────────────────────
# 3. 工具函数
# ──────────────────────────────────────────────

def is_private(host: str) -> bool:
    """判断是否为内网/回环地址"""
    host_lower = host.lower().strip()
    return any(host_lower.startswith(p) for p in PRIVATE_PREFIXES)


def validate_env() -> bool:
    """校验必需的环境变量，提前暴露配置缺失问题"""
    missing = []
    if not QUAKE_API_KEY:
        missing.append("QUAKE_API_KEY")

    if missing:
        logger.error(f"❌ 缺少必需的环境变量: {', '.join(missing)}")
        logger.error("   请在 GitHub Secrets 中配置以上变量")
        return False

    logger.info("✅ 环境变量校验通过")
    logger.info(f"   SOURCE_TYPE: {SOURCE_TYPE}")
    logger.info(f"   QUERY: {QUERY[:80]}...")
    logger.info(f"   PAGE_SIZE: {PAGE_SIZE}")
    return True


# ──────────────────────────────────────────────
# 4. 核心：调用 360 Quake API
# ──────────────────────────────────────────────

async def fetch_quake_data(session: aiohttp.ClientSession) -> dict | None:
    """
    调用 360 Quake API v3
    参数固定: start=1, size=999
    返回: 解析后的 JSON dict，失败返回 None
    """
    url = "https://quake.360.cn/api/v3/search/quake_service"
    headers = {
        "Content-Type": "application/json",
        "X-QuakeToken": QUAKE_API_KEY,
        "User-Agent": "udpxy-scanner-actions/1.0"
    }
    payload = {
        "query": QUERY,
        "start": 1,
        "size": PAGE_SIZE,
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"📡 [第 {attempt}/{MAX_RETRIES} 次尝试] 请求 360 Quake API...")
            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
            ) as resp:
                # ── HTTP 层错误处理 ──
                if resp.status == 401:
                    logger.error("❌ API 认证失败 (401)：QUAKE_API_KEY 无效或已过期")
                    logger.error("   请检查 GitHub Secrets 中的 QUAKE_API_KEY 是否正确")
                    return None  # 认证失败，无需重试

                if resp.status == 403:
                    logger.error("❌ API 权限不足 (403)：账号可能未开通 Quake 服务或额度已用完")
                    return None  # 权限问题，无需重试

                if resp.status == 429:
                    logger.warning(f"⚠️ API 请求超限 (429)：本月免费额度可能已用完")
                    logger.warning("   360 Quake 免费账号每月限 10 次 API 调用")
                    return None  # 配额超限，重试也没用

                if resp.status == 502 or resp.status == 503 or resp.status == 504:
                    logger.warning(f"⚠️ API 服务暂不可用 ({resp.status})，{attempt}/{MAX_RETRIES}")
                    if attempt < MAX_RETRIES:
                        wait = 5 * attempt
                        logger.info(f"⏳ 等待 {wait} 秒后重试...")
                        await asyncio.sleep(wait)
                        continue
                    else:
                        logger.error("❌ API 服务在多次重试后仍不可用，放弃")
                        return None

                if resp.status != 200:
                    # 尝试读取错误响应体
                    try:
                        error_body = await resp.text()
                    except Exception:
                        error_body = "(无法读取响应体)"
                    logger.error(f"❌ API 返回异常状态码: {resp.status}")
                    logger.error(f"   响应内容: {error_body[:200]}")
                    return None

                # ── 解析 JSON ──
                try:
                    data = await resp.json()
                except json.JSONDecodeError as e:
                    text_preview = (await resp.text(errors='replace'))[:200]
                    logger.error(f"❌ API 返回非 JSON 格式: {e}")
                    logger.error(f"   原始响应前 200 字符: {text_preview}")
                    return None

                # ── 业务错误码检查 ──
                code = data.get("code")
                if code != 0:
                    message = data.get("message", "未知错误")
                    logger.error(f"❌ API 业务错误 (code={code}): {message}")

                    # 常见错误码映射
                    error_hints = {
                        -1: "系统内部错误",
                        -2: "参数错误",
                        -3: "查询语法错误，请检查 QUAKE_QUERY",
                        -4: "查询超时，请简化查询语法",
                        1001: "API Key 无效或已过期",
                        1002: "API 调用次数超限",
                        1003: "IP 白名单限制",
                    }
                    hint = error_hints.get(code)
                    if hint:
                        logger.error(f"   👉 提示: {hint}")
                    return None

                # ── 成功 ──
                logger.info(f"✅ API 调用成功")
                return data

        except asyncio.TimeoutError:
            last_error = f"请求超时 ({API_TIMEOUT}秒)"
            logger.warning(f"⚠️ {last_error}，第 {attempt}/{MAX_RETRIES} 次")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(3)
        except aiohttp.ClientConnectorError as e:
            last_error = f"网络连接失败: {e}"
            logger.error(f"❌ {last_error}")
            return None  # 连接失败，重试大概率也没用
        except aiohttp.ClientError as e:
            last_error = f"HTTP 客户端异常: {e}"
            logger.warning(f"⚠️ {last_error}，第 {attempt}/{MAX_RETRIES} 次")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2)
        except Exception as e:
            last_error = f"未知异常: {e}"
            logger.error(f"❌ {last_error}")
            return None

    # 所有重试耗尽
    logger.error(f"❌ 所有 {MAX_RETRIES} 次重试均失败，最后错误: {last_error}")
    return None


# ──────────────────────────────────────────────
# 5. 解析 API 响应，提取有效 host
# ──────────────────────────────────────────────

def parse_hosts(data: dict) -> tuple[set, int]:
    """
    解析 API 响应，提取 ip:port 并过滤内网地址
    返回: (有效 hosts 集合, 过滤掉的内网地址数量)
    """
    data_list = data.get("data", [])
    total = (
        data.get("meta", {})
        .get("pagination", {})
        .get("total", 0)
    )

    if not isinstance(data_list, list):
        logger.error("❌ API 返回的 data 字段不是数组，可能接口有变动")
        return set(), 0

    hosts = set()
    filtered = 0
    parse_errors = 0

    for idx, item in enumerate(data_list):
        if not isinstance(item, dict):
            parse_errors += 1
            continue

        ip = item.get("ip", "")
        port = item.get("port", "")

        # 字段缺失或无效
        if not ip or not port:
            parse_errors += 1
            continue

        # 端口必须是数字且在合理范围内
        try:
            port_int = int(port)
            if port_int <= 0 or port_int > 65535:
                parse_errors += 1
                continue
        except (ValueError, TypeError):
            parse_errors += 1
            continue

        # 过滤内网
        host = f"{ip}:{port}"
        if is_private(host):
            filtered += 1
            continue

        hosts.add(host)

    if parse_errors > 0:
        logger.warning(f"⚠️ 解析过程中 {parse_errors} 条记录字段异常，已跳过")

    return hosts, filtered


def write_hosts_to_file(hosts: list, output_path: str):
    """将主机列表写入文件，每行一个 host"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for host in sorted(hosts):
            f.write(host + "\n")
    logger.info(f"✅ [写入] 已将 {len(hosts)} 个 host 写入 {output_path}")


# ──────────────────────────────────────────────
# 6. 主流程
# ──────────────────────────────────────────────

async def main():
    """主流程：校验 → 调用 API → 解析 → 写入文件"""
    start_time = datetime.now()
    logger.info("=" * 50)
    logger.info("🚀 360 Quake 扫描任务启动")
    logger.info(f"   时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)

    # ── 6.1 环境变量校验 ──
    if not validate_env():
        logger.error("❌ 环境变量校验失败，终止任务")
        sys.exit(1)

    # ── 6.2 创建 HTTP 会话（禁用 SSL 验证，兼容 360 Quake 的证书问题） ──
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # ── 6.3 调用 API ──
        resp = await fetch_quake_data(session)
        if resp is None:
            logger.error("❌ API 调用失败，终止任务")
            sys.exit(1)

        # ── 6.4 解析数据 ──
        logger.info("=" * 50)
        logger.info("📦 360 Quake API 完整响应:")
        logger.info(json.dumps(resp, ensure_ascii=False, indent=2))
        logger.info("=" * 50)

        hosts, filtered_count = parse_hosts(resp)
        total_in_response = len(resp.get("data", []))
        logger.info(f"📊 API 返回 {total_in_response} 条，过滤内网 {filtered_count} 条，有效 host {len(hosts)} 个")

        # ── 6.5 写入数据文件 ──
        if hosts:
            hosts_list = list(hosts)
            write_hosts_to_file(hosts_list, OUTPUT_FILE)
        else:
            logger.warning("⚠️ 没有有效 host，跳过写入")

    # ── 6.6 完成 ──
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 50)
    logger.info(f"🎉 360 Quake 扫描任务完成，耗时 {elapsed:.1f} 秒")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
