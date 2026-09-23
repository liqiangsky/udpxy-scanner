# services/scheduler.py
"""
定时任务调度服务。
由内置调度器每分钟自动触发 handle_heartbeat() 检查 cron 表达式并执行任务。
"""
import datetime
import time
import asyncio
import aiohttp
import logging
from db.database import get_db, get_setting, db_write_lock
from db.models import Config, Subscription, Host, Cache
from core.engine import trigger_background_queue, trigger_subscription_queue, enqueue_subscription
from core.status import task_runner, sub_runner
from services.notification_service import create_notification, MSG_TYPE_SUCCESS, MSG_TYPE_WARNING, NOTIFICATION_SOURCE_RECHECK

logger = logging.getLogger("定时任务")


def cron_field_match(pattern: str, value: str) -> bool:
    if pattern == "*":
        return True
    # cron 标准里 0 和 7 都是周日（实际取值用 isoweekday，1-7）
    if pattern in ("0", "7") and value == "7":
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
    执行主机复测（二次验证模式）。
    使用 verify_single_host 与扫描逻辑保持一致：尝试 rtp/udp 两种协议，仅接受 status 200。
    首次失败进入失败列表，全部完成后二次复测，仍失败则彻底删除。
    返回淘汰数量。
    """
    timeout_sec = int(get_setting("timeout", "5"))
    concurrency = int(get_setting("concurrency", "30"))

    from services.validator import verify_single_host

    with get_db() as session:
        active_sources = session.query(Host.id, Host.host, Host.target, Host.protocol).all()
        active_sources = [{"id": r.id, "host": r.host, "target": r.target, "protocol": r.protocol} for r in active_sources]

    if not active_sources:
        return 0

    task_runner.set_rechecking()
    try:
        logger.info(f"🧹 [复测] 开始复测 {len(active_sources)} 个主机")

        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        connector = aiohttp.TCPConnector(limit=256, ttl_dns_cache=300, ssl=False)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            failed_list = []
            success_items = []
            _result_lock = asyncio.Lock()
            now_ts = int(time.time())

            async def recheck_worker(source):
                async with concurrency_sem:
                    while task_runner.should_pause_recheck():
                        await asyncio.sleep(2)

                    host_raw = source["host"]
                    target_val = source["target"]
                    proto_val = source["protocol"]
                    result = await verify_single_host(session, host_raw, target_val, timeout_sec, lambda: False, protocol=proto_val)

                    if result:
                        async with _result_lock:
                            success_items.append((result["delay"], now_ts, result["protocol"], source["id"]))
                    else:
                        async with _result_lock:
                            failed_list.append(source)

            concurrency_sem = asyncio.Semaphore(concurrency)
            await asyncio.gather(*(recheck_worker(s) for s in active_sources))

            if success_items:
                # 批量更新（同 protocol/updated_at 的合并为一条 UPDATE），
                # 避免在 db_write_lock 内逐条查询持锁过长
                by_proto = {}
                for delay, updatedat, protocol, id in success_items:
                    by_proto.setdefault((protocol, updatedat, delay), []).append(id)
                with db_write_lock:
                    with get_db() as session:
                        for (protocol, updatedat, delay), ids in by_proto.items():
                            session.query(Host).filter(Host.id.in_(ids)).update(
                                {Host.delay: delay, Host.updated_at: updatedat, Host.protocol: protocol},
                                synchronize_session=False,
                            )
                        session.commit()

            eliminated = 0

            if failed_list:
                failed_hosts_str = ', '.join(s["host"] for s in failed_list)
                logger.info(f"⚠️ [二次复测] 首次失败 {len(failed_list)} 个，开始二次验证: {failed_hosts_str}")

                second_success = []
                second_failed_ids = []
                second_failed_hosts = []
                now2_ts = int(time.time())

                async def second_recheck(source):
                    async with concurrency_sem:
                        while task_runner.should_pause_recheck():
                            await asyncio.sleep(2)

                        host_raw = source["host"]
                        target_val = source["target"]
                        proto_val = source["protocol"]
                        result = await verify_single_host(session, host_raw, target_val, timeout_sec, lambda: False, protocol=proto_val)

                        if result:
                            async with _result_lock:
                                second_success.append((result["delay"], now2_ts, result["protocol"], source["id"]))
                        else:
                            async with _result_lock:
                                second_failed_ids.append((source["id"],))
                                second_failed_hosts.append(source["host"])

                await asyncio.gather(*(second_recheck(s) for s in failed_list))

                if second_success:
                    by_proto2 = {}
                    for delay, updatedat, protocol, id in second_success:
                        by_proto2.setdefault((protocol, updatedat, delay), []).append(id)
                    with db_write_lock:
                        with get_db() as session:
                            for (protocol, updatedat, delay), ids in by_proto2.items():
                                session.query(Host).filter(Host.id.in_(ids)).update(
                                    {Host.delay: delay, Host.updated_at: updatedat, Host.protocol: protocol},
                                    synchronize_session=False,
                                )
                            session.commit()
                    logger.info(f"✅ [二次恢复] {len(second_success)} 个二次复测成功")

                if second_failed_ids:
                    with db_write_lock:
                        with get_db() as session:
                            for (id,) in second_failed_ids:
                                session.query(Host).filter(Host.id == id).delete()
                            session.query(Cache).filter(Cache.host.in_(second_failed_hosts)).delete()
                            session.commit()
                    eliminated = len(second_failed_ids)
                    eliminated_hosts_str = ', '.join(second_failed_hosts)
                    logger.warning(f"🗑️ [彻底淘汰] {eliminated} 个主机（两次复测均失败）: {eliminated_hosts_str}")

            logger.info(f"🧹 [复测完成] {len(active_sources)} 个主机复测完毕，淘汰 {eliminated} 个")
            if eliminated > 0:
                create_notification(MSG_TYPE_WARNING, f"复测完成：淘汰 {eliminated} 个主机", f"{len(active_sources)} 个主机复测完毕，{eliminated} 个已不可达已清除", source=NOTIFICATION_SOURCE_RECHECK, trigger_event=True)
            else:
                create_notification(MSG_TYPE_SUCCESS, f"复测完成：{len(active_sources)} 个主机全部在线", f"{len(active_sources)} 个主机复测完毕，全部在线", source=NOTIFICATION_SOURCE_RECHECK, trigger_event=True)
            return eliminated
    finally:
        task_runner.clear_rechecking()


async def handle_heartbeat() -> dict:
    """
    检查当前时间是否匹配任何 cron 任务，匹配则执行。
    返回本次执行的任务列表。
    """
    now = datetime.datetime.now()
    cron_now = f"{now.minute} {now.hour} {now.day} {now.month} {now.isoweekday()}"

    triggered = []

    # 通用扫描 cron
    scan_cron = get_setting("scan_cron", "")
    if cron_match(scan_cron, cron_now) and _should_exec("scan", now):
        if task_runner.is_idle():
            with get_db() as session:
                rows = session.query(Config).filter(Config.enabled == 1).all()
            if rows:
                ids = [r.id for r in rows]
                trigger_background_queue(ids, skip_disabled=True)
                triggered.append({"task": "scan", "config_ids": ids})
        else:
            logger.info("⏭️ [心跳扫描跳过] 有运行中的任务，等待下次触发")

    # 复测任务触发
    janitor_cron = get_setting("janitor_cron", "")
    if cron_match(janitor_cron, cron_now) and _should_exec("janitor", now):
        if task_runner.is_idle():
            logger.info(f"⏰ [心跳触发] 定时复测 -> cron: {janitor_cron}")
            import threading
            def run_recheck():
                asyncio.run(execute_recheck())
            threading.Thread(target=run_recheck, daemon=True).start()
            triggered.append({"task": "recheck", "status": "started"})
        else:
            logger.info("⏭️ [心跳复测跳过] 有运行中的任务，等待下次触发")

    # 订阅源定时拉取（队列模式：cron 命中的订阅投递到订阅队列，与扫描队列独立运行）
    with get_db() as session:
        subscriptions = session.query(Subscription).filter(
            Subscription.enabled == 1,
            Subscription.fetch_cron != ""
        ).all()

    due_sub_ids = []
    for sub in subscriptions:
        sub_id = sub.id
        fetch_cron = sub.fetch_cron
        if not cron_match(fetch_cron, cron_now) or not _should_exec(f"sub_{sub_id}", now):
            continue
        # URL 为空说明是纯推送型订阅，无需拉取
        if not sub.url:
            logger.info(f"⏭️ [订阅跳过] {sub.name}(id={sub_id}) 无 URL，跳过拉取（纯推送型订阅）")
            continue
        due_sub_ids.append(sub_id)
        logger.info(f"⏰ 订阅触发 {sub.name} -> cron: {fetch_cron}")

    if due_sub_ids:
        if sub_runner.is_idle():
            trigger_subscription_queue(due_sub_ids)
            for sub_id in due_sub_ids:
                triggered.append({"task": f"sub_{sub_id}", "status": "queued"})
        else:
            queued_count = 0
            for sub_id in due_sub_ids:
                if enqueue_subscription(sub_id):
                    queued_count += 1
                    triggered.append({"task": f"sub_{sub_id}", "status": "queued"})
                else:
                    logger.info(f"⏭️ [订阅跳过] sub_id={sub_id} 已在队列中，等待下次触发")

    return triggered
