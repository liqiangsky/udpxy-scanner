import asyncio
import aiohttp
import threading
import time
import logging

from typing import List

from db.database import get_db, get_setting, run_in_thread, db_write_lock
from db.models import Config, Subscription, Cache
from core.status import task_runner
from services.source_cache import get_cached_hosts, cache_host_geo_batch, get_existing_hosts_batch
from services.validator import verify_single_host
from services.geoip import enrich_geo_batch
from services.message_service import create_message, MSG_TYPE_INFO, MSG_TYPE_SUCCESS, MSG_TYPE_WARNING, MSG_TYPE_ERROR

logger = logging.getLogger("扫描引擎")


def _fetch_config(cfg_id: int):
    with get_db() as session:
        row = session.query(Config).filter(Config.id == cfg_id).first()
        if row:
            return {
                "id": row.id, "name": row.name, "enabled": row.enabled,
                "data_source": row.data_source, "template_region": row.template_region,
                "template_operator": row.template_operator,
                "template_target_name": row.template_target_name,
                "template_target_address": row.template_target_address,
            }
        return None


def _update_config_timestamp(cfg_id: int):
    with db_write_lock:
        with get_db() as session:
            config = session.query(Config).filter(Config.id == cfg_id).first()
            if config:
                config.updated_at = int(time.time())


def _fetch_enabled_subscription():
    with get_db() as session:
        rows = session.query(Subscription).filter(Subscription.enabled == 1).all()
        return [{"uid": s.uid, "name": s.name} for s in rows]


def _batch_insert_hosts(batch_rows: list):
    """批量插入/更新主机数据（使用 upsert 优化性能）"""
    if not batch_rows:
        return
    hosts = list(set(row[0] for row in batch_rows))
    with db_write_lock:
        with get_db() as session:
            # 使用原始 SQL 进行批量 upsert（与旧代码逻辑一致）
            from sqlalchemy import text
            session.execute(text("""
                INSERT INTO host (
                    host, ip, port,
                    sourceType, sourceName,
                    region, operator,
                    geoRegion, geoOperator,
                    delay, protocol,
                    target, channelName,
                    createdAt, updatedAt
                ) VALUES (
                    :host, :ip, :port,
                    :sourceType, :sourceName,
                    :region, :operator,
                    :geoRegion, :geoOperator,
                    :delay, :protocol,
                    :target, :channelName,
                    :createdAt, :updatedAt
                )
                ON CONFLICT(host, target, channelName)
                DO UPDATE SET
                    delay = excluded.delay,
                    updatedAt = excluded.updatedAt,
                    geoRegion = excluded.geoRegion,
                    geoOperator = excluded.geoOperator
            """), [ {
                    "host": row[0], "ip": row[1], "port": row[2],
                    "sourceType": row[3], "sourceName": row[4],
                    "region": row[5], "operator": row[6],
                    "geoRegion": row[7], "geoOperator": row[8],
                    "delay": row[9], "protocol": row[10],
                    "target": row[11], "channelName": row[12],
                    "createdAt": row[13], "updatedAt": row[14],
                } for row in batch_rows ])

            # 更新 cache 的 active 状态
            if hosts:
                from db.models import Cache
                session.query(Cache).filter(Cache.host.in_(hosts)).update(
                    {Cache.active: 1}, synchronize_session="fetch"
                )


async def execute_scan_queue(config_ids: List[int], skip_disabled: bool = False):

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
            progress = task_runner.get_progress()
            queue = list(progress["config_ids"])

            logger.info(f"🔄 [循环] index={index}, queue={queue}, should_stop={progress['should_stop']}")

            if index >= len(queue):
                logger.info(f"🏁 [队列耗尽] index={index} >= len(queue)={len(queue)}，结束")
                break

            cfg_id = queue[index]

            if task_runner.should_interrupt():
                target = task_runner.get_interrupt_target()
                task_runner.clear_interrupt()
                if target == "__all__":
                    logger.info(f"⛔ [队列停止] cfg_id={cfg_id}，整个队列停止")
                    break
                if target == cfg_id:
                    logger.info(f"⏭️ [中断跳过] cfg_id={cfg_id}（针对当前任务的中断），跳到 index={index + 1}")
                    index += 1
                    continue
                logger.info(f"🔄 [中断清除] cfg_id={cfg_id}（中断针对 cfg_id={target}，不影响当前）")

            row_data = await run_in_thread(lambda: _fetch_config(cfg_id))

            if not row_data:
                logger.warning(f"⚠️ [配置不存在] cfg_id={cfg_id}，跳到 index={index + 1}")
                index += 1
                continue

            config = row_data

            if skip_disabled and not config["enabled"]:
                logger.warning(f"⚠️ [配置已停用] {config['name']}(id={cfg_id})，跳到 index={index + 1}")
                index += 1
                continue

            task_runner.update_progress(index, config["name"])

            await run_in_thread(_update_config_timestamp, cfg_id)

            logger.info(f"🚀 [开始扫描] {config['name']}(id={cfg_id}), index={index}/{len(queue) - 1}")

            try:
                raw_ds = config.get("data_source", "").strip()
                all_subs = await run_in_thread(_fetch_enabled_subscription)
                subs_map = {s["uid"]: s["name"] for s in all_subs}

                if raw_ds:
                    data_sources = [s.strip() for s in raw_ds.split(',') if s.strip()]
                else:
                    data_sources = [s["uid"] for s in all_subs]

                candidate_hosts = []
                for ds_uid in data_sources:
                    source_name = subs_map.get(ds_uid)
                    if not source_name:
                        logger.warning(f"⚠️ [数据源跳过] uid='{ds_uid}' 不存在或未启用")
                        continue
                    region = config.get("template_region", "")
                    hosts = get_cached_hosts(ds_uid, region)
                    logger.info(f"📡 [{source_name}] region='{region}', 匹配 {len(hosts)} 个 host")
                    candidate_hosts.extend((h, ds_uid, source_name) for h in hosts)

                if not candidate_hosts:
                    logger.warning(f"⚠️ [无候选主机] {config['name']}(id={cfg_id}) 未搜索到任何候选 host")
                else:
                    run_concurrency = global_concurrency

                    all_host_items = [h[0] for h in candidate_hosts]
                    existing_hosts = get_existing_hosts_batch(all_host_items)
                    logger.info(f"🔍 [去重] {len(existing_hosts)}/{len(all_host_items)} 个 host 已在主机池中")

                    candidate_hosts_filtered = [
                        h for h in candidate_hosts if h[0] not in existing_hosts
                    ]

                    if not candidate_hosts_filtered:
                        logger.info(f"⏭️ [全部重复] {config['name']} 所有候选 host 已在主机池中，跳过验证")
                    else:
                        logger.info(f"⚡ [验证中] 去重后 {len(candidate_hosts_filtered)} 个候选，并发数={run_concurrency}")

                        from db.models import Cache as CacheModel

                        sem = asyncio.Semaphore(run_concurrency)
                        _skipped_count = 0

                        _valid_lock = threading.Lock()
                        _valid_hosts = []

                        async def worker(host_entry):
                            nonlocal _skipped_count
                            host_item, host_source_type, host_source_name = host_entry

                            if task_runner.should_interrupt() or task_runner.should_stop():
                                _skipped_count += 1
                                return

                            async with sem:
                                if task_runner.should_interrupt() or task_runner.should_stop():
                                    _skipped_count += 1
                                    return

                                try:
                                    res = await verify_single_host(
                                        session,
                                        host_item,
                                        config["template_target_address"],
                                        global_timeout_ms / 1000.0,
                                        task_runner.should_interrupt
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

                        tasks = [asyncio.create_task(worker(h)) for h in candidate_hosts_filtered]

                        async def _cancel_on_interrupt():
                            while not task_runner.should_interrupt() and not task_runner.should_stop():
                                await asyncio.sleep(0.2)
                            for t in tasks:
                                if not t.done():
                                    t.cancel()

                        cancel_task = asyncio.create_task(_cancel_on_interrupt())
                        try:
                            await asyncio.gather(*tasks, return_exceptions=True)
                        finally:
                            cancel_task.cancel()
                            try:
                                await cancel_task
                            except (asyncio.CancelledError, Exception):
                                pass

                        logger.info(f"📊 [验证结果] 有效={len(_valid_hosts)}, 跳过={_skipped_count}, 总候选={len(candidate_hosts_filtered)}")

                        if task_runner.should_interrupt() or task_runner.should_stop():
                            logger.info(f"⚡ [中断] 跳过 geo/入库，直接进入下一个配置")
                            continue

                        if _valid_hosts:
                            enriched = await enrich_geo_batch(_valid_hosts, session, skip_health_check=True)

                            new_geo_count = 0
                            geo_rows = []
                            for item in enriched:
                                if item.get("geoRegion") or item.get("geoOperator"):
                                    geo_rows.append((item["sourceType"], item["host"], item.get("geoRegion", ""), item.get("geoOperator", "")))
                                    new_geo_count += 1
                            if geo_rows:
                                await run_in_thread(cache_host_geo_batch, geo_rows)

                            if new_geo_count:
                                logger.info(f"💾 [geo缓存] {new_geo_count} 条新 geo 信息已写入 cache")

                            enriched = [item for item in enriched if item.get("geoRegion")]
                            if not enriched:
                                logger.info(f"⏭️ [geo为空] {config['name']} 所有有效 host 的 geo 信息为空，跳过入库")
                            else:
                                now_stamp = int(time.time())

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
                                        config.get("template_region", ""),
                                        config.get("template_operator", ""),
                                        item["geoRegion"], item["geoOperator"],
                                        item["delay"], item["protocol"],
                                        config["template_target_address"].strip(),
                                        config["template_target_name"].strip(),
                                        now_stamp, now_stamp,
                                        item["delay"], now_stamp,
                                        item["geoRegion"], item["geoOperator"]
                                    ))

                                await run_in_thread(_batch_insert_hosts, batch_rows)

                                total_valid += len(enriched)
                                logger.info(f"📥 [入库] {len(enriched)} 条写入 host")

                        valid_count = len(_valid_hosts) if _valid_hosts else 0
                        logger.info(f"✅ [扫描完成] {config['name']}(id={cfg_id}) -> 有效={valid_count}, 候选={len(candidate_hosts)}")

            except Exception as e:
                logger.error(f"❌ [扫描异常] {config['name']}(id={cfg_id}) -> {e}")

            finally:
                await run_in_thread(_update_config_timestamp, cfg_id)

            index += 1

            if task_runner.should_stop():
                logger.info(f"⛔ [队列停止-后检查] should_stop=True，结束循环")
                break

            progress_now = task_runner.get_progress()
            next_queue = list(progress_now["config_ids"])
            if index < len(next_queue):
                next_cfg_id = next_queue[index]
                next_cfg = await run_in_thread(lambda: _fetch_config(next_cfg_id))
                next_name = next_cfg["name"] if next_cfg else f"id={next_cfg_id}"
                task_runner.update_progress(index, next_name)
            else:
                task_runner.update_progress(index, "")

            remaining_count = len(next_queue) - index
            if remaining_count > 0:
                logger.info(f"⏳ [等待延迟] {global_config_delay}s 后进入下一个配置（剩余 {remaining_count} 个）")
                delay = global_config_delay
                while delay > 0:
                    if task_runner.should_stop():
                        break
                    if task_runner.should_interrupt():
                        target = task_runner.get_interrupt_target()
                        if target == "__all__" or target == cfg_id:
                            logger.info(f"⚡ [延迟中断] 针对 cfg_id={target} 的中断，提前结束延迟")
                            task_runner.clear_interrupt()
                        break
                    sleep_time = min(2, delay)
                    await asyncio.sleep(sleep_time)
                    delay -= 2

        task_runner.finish()

        if total_valid > 0:
            logger.info(f"✅ [队列结束] 共发现 {total_valid} 个有效主机")
            create_message(MSG_TYPE_SUCCESS, f"扫描完成：发现 {total_valid} 个新主机", f"本次扫描共发现 {total_valid} 个有效新源", "扫描引擎")
        else:
            logger.info(f"📭 [队列结束] 本次扫描未产生新主机")
            create_message(MSG_TYPE_INFO, "扫描完成：未发现新主机", "本次扫描未产生新主机", "扫描引擎")


def trigger_background_queue(config_ids: List[int], skip_disabled: bool = False):

    shared_queue = list(config_ids)
    logger.info(f"▶️ [启动队列] 共 {len(shared_queue)} 个配置: {shared_queue}")

    task_runner.start(len(shared_queue), shared_queue)

    threading.Thread(
        target=lambda: asyncio.run(
            execute_scan_queue(shared_queue, skip_disabled)
        ),
        daemon=True
    ).start()


def enqueue_background_queue(config_id: int):
    """向运行中的队列追加一个配置"""
    if task_runner.is_idle():
        logger.info(f"⚠️ [加入队列失败] 系统空闲，cfg_id={config_id}")
        return False

    progress = task_runner.get_progress()
    remaining = progress["config_ids"][progress["current_index"]:]
    if config_id in remaining:
        logger.info(f"⚠️ [加入队列失败] cfg_id={config_id} 已在剩余队列中")
        return False

    task_runner.append_to_queue(config_id)
    logger.info(f"📋 [加入队列] cfg_id={config_id}, 新队列={task_runner.get_config_ids()}")
    return True
