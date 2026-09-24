"""API 订阅管理路由"""
import logging
import time
from fastapi import APIRouter, HTTPException
from db.database import get_db, db_write_lock
from db.models import ApiSubscriptionCreate, Subscription, Cache
from core.status import sub_runner
from core.engine import trigger_subscription_queue, enqueue_subscription

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
                # 同 uid 组：只有当没有其他订阅还用 old_uid 时才迁移 cache 数据，
                # 否则同组其他订阅的取数会因此断裂
                others = session.query(Subscription).filter(
                    Subscription.uid == old_uid, Subscription.id != sub_id
                ).count()
                if others == 0:
                    session.query(Cache).filter(Cache.uid == old_uid).update(
                        {Cache.uid: data.uid}, synchronize_session="fetch"
                    )
                    logger.info(f"✅ [订阅更新] uid '{old_uid}' -> '{data.uid}'，cache 数据已跟随迁移")
                else:
                    logger.info(f"ℹ️ [订阅更新] uid '{old_uid}' 还有 {others} 个订阅共用，cache 数据保持原 uid 不动")
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
            # 拉取中的订阅不允许删除
            if sub_runner.is_running() and sub_runner.is_stopped(sub_id) is False:
                progress = sub_runner.get_progress()
                active = next((s for s in progress["subs"] if s["id"] == sub_id and s["status"] in ("queued", "fetching")), None)
                if active:
                    raise HTTPException(400, "订阅正在拉取中，请先停止")
            session.delete(sub)
            # 同 uid 组：只有删除组内最后一个订阅时才清 cache 和配置引用，
            # 否则同 uid 其他订阅的数据/取数关系不受影响
            others = session.query(Subscription).filter(
                Subscription.uid == old_uid, Subscription.id != sub_id
            ).count()
            if others == 0:
                session.query(Cache).filter(Cache.uid == old_uid).delete(synchronize_session="fetch")
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
            else:
                logger.info(f"ℹ️ [订阅删除] uid '{old_uid}' 还有 {others} 个订阅共用，保留 cache 数据与配置引用")
    return {"ok": True}


@router.post("/subscriptions/{sub_id}/run")
@router.post("/subscriptions/{sub_id}/fetch")
async def api_trigger_subscription(sub_id: int):
    """手动触发单个订阅拉取（队列模式：空闲启动队列，运行中则排队）"""
    with get_db() as session:
        sub = session.query(Subscription).filter(Subscription.id == sub_id).first()
        if not sub:
            raise HTTPException(404, "订阅不存在")
        if not sub.enabled:
            raise HTTPException(400, "订阅已禁用")

    # URL 为空说明是纯推送型订阅（如 360Quake），无需拉取
    if not sub.url:
        logger.info(f"⏭️ 订阅 {sub.name} 无 URL，跳过拉取（纯推送型订阅）")
        return {"ok": True, "msg": f"跳过拉取：{sub.name}（纯推送型订阅）"}

    if sub_runner.is_idle():
        logger.info(f"▶️ [手动运行] 空闲状态，启动整轮 sub_id={sub_id}")
        trigger_subscription_queue([sub_id])
    else:
        if not enqueue_subscription(sub_id, sub.name):
            raise HTTPException(400, f"订阅 {sub.name} 已在拉取中")
        logger.info(f"▶️ [手动运行] 运行中，追加 sub_id={sub_id} 到下一波")
    return {"ok": True}


@router.post("/subscriptions/{sub_id}/stop")
def api_stop_single_subscription(sub_id: int):
    """提前终止单个订阅：拉取中/待启动的丢弃结果不再处理后续请求"""
    if sub_runner.is_idle():
        raise HTTPException(400, "无运行中的拉取任务")

    action = sub_runner.cancel(sub_id)
    logger.info(f"🛑 [订阅终止] sub_id={sub_id}, action={action}")

    if action == "none":
        raise HTTPException(400, "订阅不在拉取中")
    return {"ok": True, "msg": "已终止"}


@router.post("/subscriptions/stop-all")
def api_stop_all_subscriptions():
    """停止整轮订阅拉取"""
    if sub_runner.is_idle():
        raise HTTPException(400, "无运行中的拉取任务")
    sub_runner.stop()
    logger.info("🛑 [订阅全部停止] 已请求停止整轮拉取")
    return {"ok": True}


@router.post("/subscriptions/run-all")
@router.post("/subscriptions/fetch-all")
async def api_trigger_all_subscriptions():
    """手动触发所有启用订阅拉取（空闲启动整轮，运行中追加到下一波）"""
    with get_db() as session:
        subs = session.query(Subscription).filter(Subscription.enabled == 1).all()
        if not subs:
            raise HTTPException(400, "无启用的订阅")
        sub_ids = [s.id for s in subs]

    if sub_runner.is_idle():
        logger.info(f"▶️ [订阅全部拉取] 空闲状态，启动整轮 sub_ids={sub_ids}")
        trigger_subscription_queue(sub_ids)
    else:
        logger.info(f"▶️ [订阅全部拉取] 运行中，追加 sub_ids={sub_ids}")
        for sid in sub_ids:
            enqueue_subscription(sid)
    return {"ok": True}


@router.get("/subscriptions/progress")
def api_get_subscription_progress():
    """获取订阅拉取进度（含每个订阅的状态）"""
    p = sub_runner.get_progress()
    return {
        "running": p["running"],
        "fetchingIds": p["fetchingIds"],
    }
