# services/cron_heartbeat.py
"""
Cron 任务检查服务。
需要外部定时调用 /api/cron/heartbeat 触发（如宿主机 crontab 每分钟 curl）。
"""
import datetime
import asyncio
import aiohttp
import logging
from db.database import get_db, get_cache_db, get_iptv_db, get_setting
from core.engine import trigger_background_queue
from core.status import task_runner
from services.source_cache import cache_sources

logger = logging.getLogger("定时任务")


def cron_field_match(pattern: str, value: str) -> bool:
    if pattern == "*":
        return True
    if "/" in pattern:
        base, step = pattern.split("/", 1)
        v = int(value)
        s = int(step)
        if base == "*":
            return v % s == 0
        else:
            return v >= int(base) and (v - int(base)) % s == 0
    if "," in pattern:
        return value in pattern.split(",")
    if "-" in pattern:
        start, end = pattern.split("-", 1)
        return int(start) <= int(value) <= int(end)
    return pattern == value


def cron_match(cron_expr: str, cron_str: str) -> bool:
    if not cron_expr:
        return False
    try:
        c_min, c_hour, c_dom, c_mon, c_dow = cron_expr.strip().split()
        n_min, n_hour, n_dom, n_mon, n_dow = cron_str.strip().split()
        return (
            cron_field_match(c_min, n_min) and
            cron_field_match(c_hour, n_hour) and
            cron_field_match(c_dom, n_dom) and
            cron_field_match(c_mon, n_mon) and
            cron_field_match(c_dow, n_dow)
        )
    except Exception:
        return False


_last_exec_records = {}


def _should_exec(task_key: str, now: datetime.datetime) -> bool:
    exec_key = now.strftime("%Y-%m-%d %H:%M")
    last = _last_exec_records.get(task_key)
    if last == exec_key:
        return False
    _last_exec_records[task_key] = exec_key
    return True


async def execute_recheck() -> int:
    """
    执行活源复测（二次验证模式）。
    使用 verify_single_host 与扫描逻辑保持一致：尝试 rtp/udp 两种协议，仅接受 status 200。
    首次失败进入失败列表，全部完成后二次复测，仍失败则彻底删除。
    返回淘汰数量。
    """
    timeout_sec = int(get_setting("timeout", "2000")) / 1000.0
    concurrency = int(get_setting("concurrency", "64"))

    from services.validator import verify_single_host

    with get_iptv_db() as conn:
        active_sources = conn.execute("SELECT * FROM iptv_list").fetchall()

    if not active_sources:
        return 0

    task_runner.set_rechecking()
    try:
        logger.info(f"🧹 [复测] 开始复测 {len(active_sources)} 个活源")

        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        connector = aiohttp.TCPConnector(limit=256, ttl_dns_cache=300, ssl=False)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            failed_list = []

            def dummy_should_stop():
                return False

            async def recheck_worker(source):
                async with concurrency_sem:
                    if task_runner.should_pause_recheck():
                        while task_runner.should_pause_recheck():
                            await asyncio.sleep(2)

                    host_raw = source["host"]
                    target_val = source["target"]
                    proto_val = source["protocol"]
                    result = await verify_single_host(session, host_raw, target_val, timeout_sec, dummy_should_stop, protocol=proto_val)

                    if result:
                        with get_iptv_db() as conn:
                            conn.execute(
                                "UPDATE iptv_list SET delay=?, updateTime=?, protocol=? WHERE id=?",
                                (result["delay"], int(__import__("time").time() * 1000), result["protocol"], source["id"])
                            )
                        return

                    failed_list.append(source)

            concurrency_sem = asyncio.Semaphore(concurrency)
            await asyncio.gather(*(recheck_worker(s) for s in active_sources))

            eliminated = 0

            if failed_list:
                logger.info(f"⚠️ [二次复测] 首次失败 {len(failed_list)} 个，开始二次验证")

                async def second_recheck(source):
                    nonlocal eliminated
                    async with concurrency_sem:
                        if task_runner.should_pause_recheck():
                            while task_runner.should_pause_recheck():
                                await asyncio.sleep(2)

                        host_raw = source["host"]
                        target_val = source["target"]
                        proto_val = source["protocol"]
                        result = await verify_single_host(session, host_raw, target_val, timeout_sec, dummy_should_stop, protocol=proto_val)

                        if result:
                            with get_iptv_db() as conn:
                                conn.execute(
                                    "UPDATE iptv_list SET delay=?, updateTime=?, protocol=? WHERE id=?",
                                    (result["delay"], int(__import__("time").time() * 1000), result["protocol"], source["id"])
                                )
                            logger.info(f"✅ [二次恢复] {source['host']} 二次复测成功")
                            return

                        logger.warning(f"🗑️ [彻底淘汰] {source['host']} (两次复测均失败)")
                        with get_iptv_db() as conn:
                            conn.execute("DELETE FROM iptv_list WHERE id=?", (source["id"],))
                        with get_cache_db() as conn:
                            conn.execute("DELETE FROM source_cache WHERE host=?", (source["host"],))
                        eliminated += 1

                await asyncio.gather(*(second_recheck(s) for s in failed_list))

            logger.info(f"🧹 [复测完成] {len(active_sources)} 个活源复测完毕，淘汰 {eliminated} 个")
            return eliminated
    finally:
        task_runner.clear_rechecking()


async def handle_heartbeat() -> dict:
    """
    检查当前时间是否匹配任何 cron 任务，匹配则执行。
    返回本次执行的任务列表。
    """
    now = datetime.datetime.now()
    cron_now = f"{now.minute} {now.hour} {now.day} {now.month} {now.weekday() + 1}"

    triggered = []

    # 通用扫描 cron
    scan_cron = get_setting("scan_cron", "")
    if cron_match(scan_cron, cron_now) and _should_exec("scan", now):
        with get_db() as conn:
            rows = conn.execute("SELECT id FROM scan_config WHERE enabled=1").fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            trigger_background_queue(ids, skip_disabled=True)
            triggered.append({"task": "scan", "config_ids": ids})

    # 复测任务触发
    janitor_cron = get_setting("janitor_cron", "")
    if cron_match(janitor_cron, cron_now) and _should_exec("janitor", now):
        if task_runner.is_idle():
            logger.info(f"⏰ [心跳触发] 定时复测 -> cron: {janitor_cron}")
            import threading
            import asyncio
            def run_recheck():
                asyncio.run(execute_recheck())
            threading.Thread(target=run_recheck, daemon=True).start()
            triggered.append({"task": "recheck", "status": "started"})

    # 订阅源定时拉取
    with get_db() as conn:
        subscriptions = conn.execute(
            "SELECT * FROM api_subscriptions WHERE enabled=1 AND fetchCron!=''"
        ).fetchall()

    for sub in subscriptions:
        fetch_cron = sub["fetchCron"]
        if cron_match(fetch_cron, cron_now) and _should_exec(f"sub_{sub['id']}", now):
            import time
            trace_id = f"cron_{sub['uid']}_{int(time.time())}"
            logger.info(f"⏰ [trace:{trace_id}] 订阅触发 {sub['name']} -> cron: {fetch_cron}")
            from services.subscription_fetcher import fetch_subscription
            from services.source_cache import process_source_data
            sources = await fetch_subscription(sub["name"], sub["uid"], sub["url"])
            if sources:
                hosts_data = [{"host": s["host"], "geoRegion": s.get("geoRegion", ""), "geoOperator": s.get("geoOperator", "")} for s in sources]
                await process_source_data(sub["uid"], hosts_data, trace_id=trace_id)
            from datetime import datetime
            with get_db() as conn:
                conn.execute(
                    "UPDATE api_subscriptions SET lastFetchAt=? WHERE id=?",
                    (datetime.now().isoformat(), sub["id"])
                )
            triggered.append({"task": f"sub_{sub['id']}", "name": sub["name"]})

    return triggered
