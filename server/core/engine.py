import asyncio
import aiohttp
import threading
import time
import logging

from typing import List

from db.database import get_db, get_cache_db, get_iptv_db, get_setting, run_in_thread
from core.status import task_runner
from services.source_cache import get_cached_hosts, cache_sources, cache_host_geo_batch, get_cached_geo_batch, get_existing_iptv_hosts_batch
from services.validator import verify_single_host
from services.geoip import enrich_geo_batch

logger = logging.getLogger("扫描引擎")

# SQLite 写锁：序列化所有并发写入，防止 database is locked
_db_write_lock = threading.Lock()


def _fetch_scan_config(cfg_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM scan_config WHERE id=?", (cfg_id,)).fetchone()


def _update_config_timestamp(cfg_id: int):
    with get_db() as conn:
        conn.execute("UPDATE scan_config SET updatedAt=datetime('now') WHERE id=?", (cfg_id,))


def _fetch_enabled_subscriptions():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT uid, name FROM api_subscriptions WHERE enabled=1").fetchall()]


def _batch_insert_iptv(batch_rows: list, now_stamp: int):
    _db_write_lock.acquire()
    try:
        with get_iptv_db() as conn:
            conn.executemany("""
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
                    delay = ?,
                    updateTime = ?,
                    geoRegion = ?,
                    geoOperator = ?
            """, batch_rows)
    finally:
        _db_write_lock.release()


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

            row_data = await run_in_thread(lambda: _fetch_scan_config(cfg_id))

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

            await run_in_thread(_update_config_timestamp, cfg_id)

            logger.info(f"🚀 [开始扫描] {config['name']}")

            try:
                # 根据 dataSource 路由（空 = 全部启用订阅，逗号分隔 = 指定 uid）
                raw_ds = config.get("dataSource", "").strip()
                if raw_ds:
                    data_sources = [s.strip() for s in raw_ds.split(',') if s.strip()]
                else:
                    subs = await run_in_thread(_fetch_enabled_subscriptions)
                    data_sources = [s["uid"] for s in subs]

                all_subs = await run_in_thread(_fetch_enabled_subscriptions)
                subs_map = {s["uid"]: s["name"] for s in all_subs}

                candidate_hosts = []
                for ds_uid in data_sources:
                    source_name = subs_map.get(ds_uid)
                    if not source_name:
                        logger.warning(f"⚠️ [数据源跳过] uid='{ds_uid}' 不存在或未启用")
                        continue
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
                    _valid_hosts = []

                    all_host_items = [h[0] for h in candidate_hosts]
                    existing_hosts = get_existing_iptv_hosts_batch(all_host_items)
                    logger.info(f"🔍 [去重] {len(existing_hosts)}/{len(all_host_items)} 个 host 已在活源池中")

                    candidate_hosts_filtered = [
                        h for h in candidate_hosts if h[0] not in existing_hosts
                    ]

                    if not candidate_hosts_filtered:
                        logger.info(f"⏭️ [全部重复] {config['name']} 所有候选 host 已在活源池中，跳过验证")
                    else:
                        logger.info(f"⚡ [验证中] 去重后 {len(candidate_hosts_filtered)} 个候选，并发数={run_concurrency}")

                    sem = asyncio.Semaphore(run_concurrency)

                    async def worker(host_entry):
                        host_item, host_source_type, host_source_name = host_entry

                        if task_runner.should_stop():
                            return

                        async with sem:

                            try:
                                res = await verify_single_host(
                                    session,
                                    host_item,
                                    config["templateTargetAddress"],
                                    global_timeout_ms / 1000.0,
                                    task_runner.should_stop
                                )

                                if not res:
                                    return

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
                        *(worker(h) for h in candidate_hosts_filtered)
                    )

                    if _valid_hosts:
                        valid_host_list = [h["host"] for h in _valid_hosts]
                        cached_geo_map = get_cached_geo_batch(valid_host_list)
                        for host_item in _valid_hosts:
                            cached = cached_geo_map.get(host_item["host"])
                            if cached:
                                host_item.update(cached)

                        # 统一 geoip 富化（已有 geo 的会自动跳过）
                        enriched = await enrich_geo_batch(_valid_hosts, session)

                        # 新 geo 回写 source_cache
                        new_geo_count = 0
                        geo_rows = []
                        for item in enriched:
                            if item.get("geoRegion") or item.get("geoOperator"):
                                geo_rows.append((item["sourceType"], item["host"], item.get("geoRegion", ""), item.get("geoOperator", "")))
                                new_geo_count += 1
                        if geo_rows:
                            await run_in_thread(cache_host_geo_batch, geo_rows)

                        if new_geo_count:
                            logger.info(f"💾 [geo缓存] {new_geo_count} 条新 geo 信息已写入 source_cache")

                        now_stamp = int(time.time() * 1000)

                        batch_rows = []
                        for item in enriched:
                            host_item = item["host"]
                            if ":" in host_item:
                                ip_val, port_val = host_item.rsplit(":", 1)
                            else:
                                ip_val, port_val = host_item, 80
                            batch_rows.append((
                                host_item, ip_val, int(port_val),
                                item["sourceType"], item["sourceName"],
                                config.get("templateRegion", ""),
                                config.get("templateOperator", ""),
                                item["geoRegion"], item["geoOperator"],
                                item["delay"], item["protocol"],
                                config["templateTargetAddress"],
                                config["templateTargetName"],
                                now_stamp, now_stamp,
                                item["delay"], now_stamp,
                                item["geoRegion"], item["geoOperator"]
                            ))

                        await run_in_thread(_batch_insert_iptv, batch_rows, now_stamp)

                        valid_count = len(enriched)

                    logger.info(f"✅ [扫描完成] {config['name']} -> {valid_count}/{len(candidate_hosts)} 个有效")
                    total_valid += valid_count

            except Exception as e:
                logger.error(f"❌ [扫描异常] {config['name']} -> {e}")

            finally:
                await run_in_thread(_update_config_timestamp, cfg_id)

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


