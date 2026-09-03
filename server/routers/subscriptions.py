"""API 订阅管理路由"""
import logging
import threading
import asyncio
import time
from fastapi import APIRouter, HTTPException
from db.database import get_db, db_write_lock
from db.models import ApiSubscriptionCreate, Subscription, Cache
from core.status import task_runner
from services.source_cache import process_source_data
from services.subscription_fetcher import fetch_subscription_by_type
from services.message_service import create_message, MSG_TYPE_SUCCESS, MSG_TYPE_WARNING, MSG_TYPE_ERROR

logger = logging.getLogger("订阅管理")
router = APIRouter()


@router.get("/subscriptions")
def api_list_subscriptions():
    """获取所有 API 订阅"""
    with get_db() as session:
        rows = session.query(Subscription).order_by(Subscription.id).all()
        return [{
            "id": r.id, "name": r.name, "uid": r.uid, "url": r.url,
            "type": r.type, "enabled": bool(r.enabled), "fetchCron": r.fetch_cron,
            "lastFetchAt": r.last_fetch_at, "createdAt": r.created_at, "updatedAt": r.updated_at,
        } for r in rows]


@router.post("/subscriptions")
def api_create_subscription(data: ApiSubscriptionCreate):
    """创建 API 订阅"""
    with db_write_lock:
        with get_db() as session:
            try:
                sub = Subscription(
                    name=data.name,
                    uid=data.uid,
                    url=data.url,
                    type=data.type,
                    enabled=1 if data.enabled else 0,
                    fetch_cron=data.fetch_cron,
                    created_at=int(time.time()),
                    updated_at=int(time.time()),
                )
                session.add(sub)
                session.flush()
                sub_id = sub.id
            except Exception as e:
                raise HTTPException(400, f"创建失败: {e}")
    return {"ok": True, "id": sub_id}


@router.put("/subscriptions/{sub_id}")
def api_update_subscription(sub_id: int, data: ApiSubscriptionCreate):
    """更新 API 订阅"""
    with db_write_lock:
        with get_db() as session:
            sub = session.query(Subscription).filter(Subscription.id == sub_id).first()
            if not sub:
                raise HTTPException(404, "订阅不存在")
            old_uid = sub.uid
            sub.name = data.name
            sub.uid = data.uid
            sub.url = data.url
            sub.type = data.type
            sub.enabled = 1 if data.enabled else 0
            sub.fetch_cron = data.fetch_cron
            sub.updated_at = int(time.time())
            if old_uid != data.uid:
                session.query(Cache).filter(Cache.source_type == old_uid).update(
                    {Cache.source_type: data.uid}, synchronize_session="fetch"
                )
    return {"ok": True}


@router.delete("/subscriptions/{sub_id}")
def api_delete_subscription(sub_id: int):
    """删除 API 订阅"""
    with db_write_lock:
        with get_db() as session:
            from db.models import Config
            sub = session.query(Subscription).filter(Subscription.id == sub_id).first()
            if not sub:
                raise HTTPException(404, "订阅不存在")
            old_uid = sub.uid
            session.delete(sub)
            session.query(Cache).filter(Cache.source_type == old_uid).delete(synchronize_session="fetch")
            # 清理所有引用了该订阅的配置的 dataSource 字段
            configs = session.query(Config).filter(Config.data_source.like(f'%{old_uid}%')).all()
            for cfg in configs:
                parts = [p.strip() for p in cfg.data_source.split(',') if p.strip()]
                parts = [p for p in parts if p != old_uid]
                cfg.data_source = ','.join(parts)
                if not cfg.data_source:
                    cfg.enabled = 0
                    logger.warning(f"⚠️ [订阅删除] cfg_id={cfg.id} 的 dataSource 已清空，已自动禁用该配置")
            if configs:
                logger.info(f"✅ [订阅删除] 已清理 {len(configs)} 个配置中对 '{old_uid}' 的引用")
    return {"ok": True}


@router.post("/subscriptions/{sub_id}/run")
@router.post("/subscriptions/{sub_id}/fetch")
async def api_trigger_subscription(sub_id: int):
    """手动触发单个订阅拉取"""
    with get_db() as session:
        sub = session.query(Subscription).filter(Subscription.id == sub_id).first()
        if not sub:
            raise HTTPException(404, "订阅不存在")
        if not sub.enabled:
            raise HTTPException(400, "订阅已禁用")
        sub_uid = sub.uid
        sub_name = sub.name
        sub_url = sub.url
        sub_type = sub.type or "api"

    # URL 为空说明是纯推送型订阅（如 360Quake），无需拉取
    if not sub_url:
        logger.info(f"⏭️ 订阅 {sub_name} 无 URL，跳过拉取（纯推送型订阅）")
        return {"ok": True, "msg": f"跳过拉取：{sub_name}（纯推送型订阅）"}

    if not task_runner.start_fetch(sub_id):
        raise HTTPException(400, f"订阅(id={sub_id})正在拉取中，请稍后")

    async def _run_fetch():
        try:
            logger.info(f"📡 开始拉取订阅 {sub_name}")
            sources = await fetch_subscription_by_type(sub_name, sub_uid, sub_url, sub_type)
            if sources:
                hosts_data = [{"host": s["host"], "geoRegion": s.get("geoRegion", ""), "geoOperator": s.get("geoOperator", "")} for s in sources]
                count = await process_source_data(sub_uid, hosts_data)
                create_message(MSG_TYPE_SUCCESS, f"订阅拉取完成：{sub_name}", f"获取到 {count} 条数据", "订阅管理")
            else:
                create_message(MSG_TYPE_WARNING, f"订阅拉取完成：{sub_name}", "未获取到数据", "订阅管理")
        except Exception as e:
            create_message(MSG_TYPE_ERROR, f"订阅拉取失败：{sub_name}", f"错误: {str(e)}", "订阅管理")
            logger.error(f"❌ [订阅拉取失败] {sub_name}: {e}")
        finally:
            with db_write_lock:
                with get_db() as session:
                    session.query(Subscription).filter(Subscription.id == sub_id).update(
                        {Subscription.last_fetch_at: int(time.time())}, synchronize_session="fetch"
                    )
            task_runner.finish_fetch(sub_id)

    asyncio.create_task(_run_fetch())
    return {"ok": True}


@router.post("/subscriptions/run-all")
@router.post("/subscriptions/fetch-all")
async def api_trigger_all_subscriptions():
    """手动触发所有启用订阅拉取"""
    if task_runner.is_rechecking():
        raise HTTPException(400, "复测进行中，请稍后")

    with get_db() as session:
        subs = session.query(Subscription).filter(Subscription.enabled == 1).all()
        if not subs:
            raise HTTPException(400, "无启用的订阅")
        sub_list = [(s.id, s.name, s.uid, s.url, s.type or "api") for s in subs]

    success_count = 0
    total_count = len(sub_list)

    async def _fetch_one(sub_id, sub_name, sub_uid, sub_url, sub_type):
        nonlocal success_count
        # URL 为空说明是纯推送型订阅，跳过拉取
        if not sub_url:
            logger.info(f"⏭️ [订阅拉取] {sub_name} 无 URL，跳过拉取（纯推送型订阅）")
            return

        if not task_runner.start_fetch(sub_id):
            logger.info(f"⏭️ [订阅拉取] {sub_name}(id={sub_id}) 已在拉取中，跳过")
            return

        try:
            logger.info(f"📡 [订阅拉取] {sub_name}")
            sources = await fetch_subscription_by_type(sub_name, sub_uid, sub_url, sub_type)
            if sources:
                hosts_data = [{"host": s["host"], "geoRegion": s.get("geoRegion", ""), "geoOperator": s.get("geoOperator", "")} for s in sources]
                count = await process_source_data(sub_uid, hosts_data)
                logger.info(f"✅ [订阅拉取] {sub_name}: {count} 条")
                success_count += 1
            else:
                logger.info(f"⏭️ [订阅拉取] {sub_name}: 未获取到数据")
        except Exception as e:
            logger.error(f"❌ [订阅拉取失败] {sub_name}: {e}")
        finally:
            with db_write_lock:
                with get_db() as session:
                    session.query(Subscription).filter(Subscription.id == sub_id).update(
                        {Subscription.last_fetch_at: int(time.time())}, synchronize_session="fetch"
                    )
            task_runner.finish_fetch(sub_id)

    async def _run_all():
        await asyncio.gather(*(_fetch_one(sid, name, uid, url, typ) for sid, name, uid, url, typ in sub_list))
        if success_count > 0:
            create_message(MSG_TYPE_SUCCESS, "批量拉取完成", f"{success_count}/{total_count} 个订阅拉取成功", "订阅管理")

    asyncio.create_task(_run_all())
    return {"ok": True}
