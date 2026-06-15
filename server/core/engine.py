import asyncio
import aiohttp
import threading
import time
import logging

from typing import List

from db.database import get_db, get_cache_db, get_iptv_db, get_setting
from core.status import task_runner
from services.source_cache import get_cached_hosts, cache_sources, get_cached_geo, cache_host_geo
from services.validator import verify_single_host
from services.geoip import enrich_geo_batch

logger = logging.getLogger("udpxy_scanner")

# SQLite 写锁：序列化所有并发写入，防止 database is locked
_db_write_lock = threading.Lock()


async def execute_scan_queue(config_ids: List[int], skip_disabled: bool = False):

    logger.info(f"🚀 [扫描开始] 配置队列: {config_ids}")

    global_config_delay = int(get_setting("config_delay", "3"))
    global_concurrency = int(get_setting("concurrency", "64"))
    global_timeout_ms = int(get_setting("timeout", "2000"))

    timeout = aiohttp.ClientTimeout(total=global_timeout_ms / 1000.0)

    connector = aiohttp.TCPConnector(
        limit=512,
        ssl=False,
        ttl_dns_cache=300
    )

    total_valid = 0

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector
    ) as session:

        index = 0
        while True:
            # 每次循环从 task_runner 获取最新队列（支持运行时追加/删除）
            progress = task_runner.get_progress()
            queue = list(progress["config_ids"])

            if index >= len(queue):
                break

            cfg_id = queue[index]

            # 全局停止信号
            if task_runner.should_stop():
                logger.info(f"⛔ [停止扫描] 配置 id={cfg_id} 被用户停止")
                break

            with get_db() as conn:
                row_data = conn.execute(
                    "SELECT * FROM scan_config WHERE id=?",
                    (cfg_id,)
                ).fetchone()

            if not row_data:
                logger.warning(f"⚠️ [配置不存在] id={cfg_id}，跳过")
                index += 1
                continue

            config = dict(row_data)

            if skip_disabled and not config["enabled"]:
                logger.warning(f"⚠️ [配置已停用] {config['name']}，跳过")
                index += 1
                continue

            task_runner.update_progress(
                index,
                config["name"]
            )

            with get_db() as conn:
                conn.execute(
                    "UPDATE scan_config SET updatedAt=datetime('now') WHERE id=?",
                    (cfg_id,)
                )

            logger.info(f"🚀 [开始扫描] {config['name']}")

            try:
                # 根据 dataSource 路由（空 = 全部启用订阅，逗号分隔 = 指定 uid）
                raw_ds = config.get("dataSource", "").strip()
                if raw_ds:
                    data_sources = [s.strip() for s in raw_ds.split(',') if s.strip()]
                else:
                    with get_db() as conn:
                        subs = conn.execute(
                            "SELECT uid, name FROM api_subscriptions WHERE enabled=1"
                        ).fetchall()
                    data_sources = [s["uid"] for s in subs]

                candidate_hosts = []  # list of (host, source_type, source_name)
                for ds_uid in data_sources:
                    source_name = ds_uid
                    # 校验：如果 dataSource 不存在或未启用则跳过
                    with get_db() as conn:
                        sub_row = conn.execute(
                            "SELECT uid, name FROM api_subscriptions WHERE uid=? AND enabled=1",
                            (ds_uid,)
                        ).fetchone()
                    if not sub_row:
                        logger.warning(f"⚠️ [数据源跳过] uid='{ds_uid}' 不存在或未启用")
                        continue
                    source_name = sub_row["name"]
                    region = config.get("templateRegion", "")
                    hosts = get_cached_hosts(ds_uid, region)
                    logger.info(f"📡 [{source_name}] 从 source_cache 读取, region='{region}', 匹配到 {len(hosts)} 个 host: {hosts}")
                    candidate_hosts.extend((h, ds_uid, source_name) for h in hosts)

                if not candidate_hosts:
                    logger.warning(f"⚠️ [无候选源] {config['name']} 未搜索到任何候选 host")
                else:

                    run_concurrency = global_concurrency

                    logger.info(f"⚡ [验证中] {len(candidate_hosts)} 个候选，并发数={run_concurrency}")

                    valid_count = 0
                    _valid_lock = threading.Lock()
                    _valid_hosts = []  # 收集验证通过的 host

                    sem = asyncio.Semaphore(run_concurrency)

                    async def worker(host_entry):
                        host_item, host_source_type, host_source_name = host_entry

                        if task_runner.should_stop():
                            return

                        async with sem:

                            try:
                                #
                                # 去重检查：如果 host 已在 iptv_list 中则跳过
                                #
                                with get_iptv_db() as conn:
                                    existing = conn.execute(
                                        "SELECT 1 FROM iptv_list WHERE host=?",
                                        (host_item,)
                                    ).fetchone()
                                if existing:
                                    return

                                res = await verify_single_host(
                                    session,
                                    host_item,
                                    config["templateTargetAddress"],
                                    global_timeout_ms / 1000.0,
                                    task_runner.should_stop
                                )

                                if not res:
                                    return

                                # 收集验证通过的结果（携带来源标签）
                                with _valid_lock:
                                    _valid_hosts.append({
                                        "host": host_item,
                                        "delay": res["delay"],
                                        "protocol": res["protocol"],
                                        "sourceType": host_source_type,
                                        "sourceName": host_source_name
                                    })

                            except Exception as e:
                                logger.error(f"❌ [验证异常] {host_item} -> {e}")

                        return

                    await asyncio.gather(
                        *(worker(h) for h in candidate_hosts)
                    )

                    if _valid_hosts:
                        # 预填充已有 geo 缓存，跳过重复查询
                        for host_item in _valid_hosts:
                            cached = get_cached_geo(host_item["host"])
                            if cached:
                                host_item.update(cached)

                        # 统一 geoip 富化（已有 geo 的会自动跳过）
                        enriched = await enrich_geo_batch(session, _valid_hosts)

                        # 新 geo 回写 source_cache
                        new_geo_count = 0
                        for item in enriched:
                            if item.get("geoRegion") or item.get("geoOperator"):
                                cache_host_geo(item["sourceType"], item["host"], item.get("geoRegion", ""), item.get("geoOperator", ""))
                                new_geo_count += 1

                        if new_geo_count:
                            logger.info(f"💾 [geo缓存] {new_geo_count} 条新 geo 信息已写入 source_cache")

                        now_stamp = int(time.time() * 1000)

                        # 入 iptv_list 活源池
                        _db_write_lock.acquire()
                        try:
                            with get_iptv_db() as conn:
                                for item in enriched:
                                    host_item = item["host"]
                                    if ":" in host_item:
                                        ip_val, port_val = host_item.rsplit(":", 1)
                                    else:
                                        ip_val, port_val = host_item, 80

                                    conn.execute("""
                                        INSERT INTO iptv_list (
                                            host, ip, port,
                                            sourceType, sourceName,
                                            region, operator,
                                            geoRegion, geoOperator,
                                            delay, protocol,
                                            target, channelName,
                                            createTime, updateTime
                                        ) VALUES (
                                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                                        )
                                        ON CONFLICT(host, target, channelName)
                                        DO UPDATE SET
                                            delay = excluded.delay,
                                            updateTime = excluded.updateTime,
                                            geoRegion = excluded.geoRegion,
                                            geoOperator = excluded.geoOperator
                                    """, (
                                        host_item, ip_val, int(port_val),
                                        item["sourceType"], item["sourceName"],
                                        config.get("templateRegion", ""),
                                        config.get("templateOperator", ""),
                                        item["geoRegion"], item["geoOperator"],
                                        item["delay"], item["protocol"],
                                        config["templateTargetAddress"],
                                        config["templateTargetName"],
                                        now_stamp, now_stamp
                                    ))
                        finally:
                            _db_write_lock.release()

                        valid_count = len(enriched)

                    logger.info(f"✅ [扫描完成] {config['name']} -> {valid_count}/{len(candidate_hosts)} 个有效")
                    total_valid += valid_count

            except Exception as e:
                logger.error(f"❌ [扫描异常] {config['name']} -> {e}")

            finally:
                with get_db() as conn:
                    conn.execute(
                        "UPDATE scan_config SET updatedAt=datetime('now') WHERE id=?",
                        (cfg_id,)
                    )

            # 配置间延迟（可中断）
            progress_now = task_runner.get_progress()
            if index < len(progress_now["config_ids"]) - 1 and not task_runner.should_stop():
                logger.info(f"⏳ [等待延迟] {global_config_delay}s 后进入下一个配置")
                delay = global_config_delay
                while delay > 0:
                    if task_runner.should_stop():
                        break
                    sleep_time = min(2, delay)
                    await asyncio.sleep(sleep_time)
                    delay -= 2

            index += 1

        # 自动续跑：用户停止当前配置后，用剩余配置继续执行
        # 保存队列快照（含运行时追加的配置），再调用 finish() 清空
        queue_snapshot = list(task_runner.get_progress()["config_ids"])
        task_runner.finish()

        if total_valid > 0:
            logger.info(f"✅ [扫描完成] 共发现 {total_valid} 个有效源")
        else:
            logger.info("📭 [扫描完成] 本次扫描未产生新活源")

        skipped_ids = task_runner.pop_skipped_configs()
        if skipped_ids:
            next_index = index
            remaining = [cid for cid in queue_snapshot[next_index:] if cid not in skipped_ids]

            if remaining:
                logger.info(f"⏭️ [自动续跑] 用剩余 {len(remaining)} 个配置继续: {remaining}")
                await asyncio.sleep(1)
                threading.Thread(
                    target=auto_restart_with_remaining,
                    args=(list(remaining), False),
                    daemon=True
                ).start()


def auto_restart_with_remaining(config_ids: List[int], skip_disabled: bool = False):
    """自动重启：重置所有中断标记，确保新配置干净启动"""
    # 强制重置所有停止标记，防止旧信号污染新线程
    with task_runner._lock:
        task_runner._should_stop = False
        task_runner._scanning_config_id = None
        task_runner._skip_config_ids.clear()
    task_runner.start(len(config_ids), config_ids)
    asyncio.run(execute_scan_queue(config_ids, skip_disabled))


def trigger_background_queue(config_ids: List[int], skip_disabled: bool = False):

    shared_queue = list(config_ids)
    logger.info(f"▶️ [任务队列] 共 {len(shared_queue)} 个配置: {shared_queue}")

    task_runner.start(len(shared_queue), shared_queue)

    threading.Thread(
        target=lambda: asyncio.run(
            execute_scan_queue(shared_queue, skip_disabled)
        ),
        daemon=True
    ).start()


def enqueue_background_queue(config_id: int):

    if task_runner.is_idle():
        return False

    progress = task_runner.get_progress()
    if config_id in progress["config_ids"]:
        return False

    task_runner.enqueue([config_id])
    logger.info(f"📋 [加入队列] 配置 id={config_id}")
    return True


