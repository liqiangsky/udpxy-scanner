"""API 订阅管理路由"""
import logging
import threading
import asyncio
import time
from fastapi import APIRouter, HTTPException
from db.database import get_db, db_write_lock
from db.models import ApiSubscriptionCreate
from core.status import task_runner
from services.source_cache import process_source_data
from services.subscription_fetcher import fetch_subscription
from services.message_service import create_message, MSG_TYPE_SUCCESS, MSG_TYPE_WARNING, MSG_TYPE_ERROR

logger = logging.getLogger("订阅管理")
router = APIRouter()


@router.get("/subscriptions")
def api_list_subscriptions():
    """获取所有 API 订阅"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM subscription ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/subscriptions")
def api_create_subscription(data: ApiSubscriptionCreate):
    """创建 API 订阅"""
    with db_write_lock:
        with get_db() as conn:
            try:
                conn.execute(
                    "INSERT INTO subscription (name, uid, url, enabled, fetchCron) VALUES (?, ?, ?, ?, ?)",
                    (data.name, data.uid, data.url, 1 if data.enabled else 0, data.fetchCron)
                )
                sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            except Exception as e:
                raise HTTPException(400, f"创建失败: {e}")
    return {"ok": True, "id": sub_id}


@router.put("/subscriptions/{sub_id}")
def api_update_subscription(sub_id: int, data: ApiSubscriptionCreate):
    """更新 API 订阅"""
    with db_write_lock:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM subscription WHERE id=?", (sub_id,)).fetchone()
            if not row:
                raise HTTPException(404, "订阅不存在")
            old = conn.execute("SELECT uid FROM subscription WHERE id=?", (sub_id,)).fetchone()
            old_uid = old["uid"]
            conn.execute(
                "UPDATE subscription SET name=?, uid=?, url=?, enabled=?, fetchCron=?, updatedAt=? WHERE id=?",
                (data.name, data.uid, data.url, 1 if data.enabled else 0, data.fetchCron, int(time.time()), sub_id)
            )
            if old_uid != data.uid:
                conn.execute(
                    "UPDATE cache SET sourceType=? WHERE sourceType=?",
                    (data.uid, old_uid)
                )
    return {"ok": True}


@router.delete("/subscriptions/{sub_id}")
def api_delete_subscription(sub_id: int):
    """删除 API 订阅并清除对应的 cache"""
    with db_write_lock:
        with get_db() as conn:
            row = conn.execute("SELECT uid FROM subscription WHERE id=?", (sub_id,)).fetchone()
            if not row:
                raise HTTPException(404, "订阅不存在")
            uid = row["uid"]
            conn.execute("DELETE FROM subscription WHERE id=?", (sub_id,))
            conn.execute("DELETE FROM cache WHERE sourceType=?", (uid,))
    logger.info(f"🗑️ [订阅删除] uid={uid}")
    return {"ok": True}


@router.post("/subscriptions/{sub_id}/fetch")
def api_fetch_subscription(sub_id: int):
    """手动触发单个订阅拉取，后台异步执行"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM subscription WHERE id=? AND enabled=1",
            (sub_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "订阅未启用或不存在")

    if not task_runner.start_fetch(sub_id):
        raise HTTPException(400, f"订阅(id={sub_id})正在拉取中，请稍后")

    sub_info = dict(row)

    # URL 为空说明是纯推送型订阅（如 360Quake），无需拉取
    if not sub_info.get("url", ""):
        logger.info(f"⏭️ 订阅 {sub_info['name']} 无 URL，跳过拉取（纯推送型订阅）")
        task_runner.finish_fetch(sub_id)
        return {"ok": True, "msg": f"跳过拉取：{sub_info['name']}（纯推送型订阅）"}

    def run_fetch():
        try:
            async def _do():
                logger.info(f"📡 开始拉取订阅 {sub_info['name']}")
                sources = await fetch_subscription(sub_info["name"], sub_info["uid"], sub_info["url"])
                if sources:
                    hosts_data = [{"host": s["host"], "geoRegion": s.get("geoRegion", ""), "geoOperator": s.get("geoOperator", "")} for s in sources]
                    await process_source_data(sub_info["uid"], hosts_data)
                with db_write_lock:
                    with get_db() as conn:
                        conn.execute(
                            "UPDATE subscription SET lastFetchAt=? WHERE id=?",
                            (int(time.time()), sub_info["id"])
                        )
                logger.info(f"✅ 订阅 {sub_info['name']} 拉取完成")
                if sources:
                    create_message(MSG_TYPE_SUCCESS, f"订阅拉取完成：{sub_info['name']}", f"获取到 {len(sources)} 条数据", "订阅管理")
            # Python 3.10+ 中 asyncio.run() 可安全地从非主线程调用（自动创建新事件循环）
            asyncio.run(_do())
        finally:
            task_runner.finish_fetch(sub_id)

    threading.Thread(target=run_fetch, daemon=True).start()
    return {"ok": True, "msg": f"已启动拉取：{sub_info['name']}"}


@router.post("/subscriptions/fetch-all")
def api_fetch_all_subscriptions():
    """手动触发所有已启用订阅拉取，后台异步执行，不阻塞返回"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM subscription WHERE enabled=1"
        ).fetchall()

    if not rows:
        raise HTTPException(400, "无启用订阅")

    # 预检查所有订阅是否不在拉取中
    for r in rows:
        if not task_runner.start_fetch(r["id"]):
            # 回滚已标记的
            for r2 in rows:
                if r2["id"] == r["id"]:
                    break
                task_runner.finish_fetch(r2["id"])
            raise HTTPException(400, f"订阅(id={r['id']})正在拉取中，请稍后")

    def run_all():
        try:
            async def _do_all():
                results = await asyncio.gather(*(
                    _fetch_single(dict(r)) for r in rows
                ), return_exceptions=True)

                now = int(time.time())
                with db_write_lock:
                    with get_db() as conn:
                        for row in rows:
                            conn.execute(
                                "UPDATE subscription SET lastFetchAt=? WHERE id=?",
                                (now, row["id"])
                            )
                success = sum(1 for r in results if isinstance(r, int))
                logger.info(f"✅ 全部拉取完成: {success}/{len(rows)} 个成功")
                if success > 0:
                    create_message(MSG_TYPE_SUCCESS, f"批量拉取完成", f"{success}/{len(rows)} 个订阅拉取成功", "订阅管理")

            asyncio.run(_do_all())
        finally:
            for r in rows:
                task_runner.finish_fetch(r["id"])

    threading.Thread(target=run_all, daemon=True).start()
    return {"ok": True, "msg": "已启动全部拉取"}


async def _fetch_single(row: dict) -> int:
    """拉取单个订阅，返回成功数量"""
    # URL 为空说明是纯推送型订阅，跳过拉取
    if not row.get("url", ""):
        logger.info(f"⏭️ 订阅 {row['name']} 无 URL，跳过拉取（纯推送型订阅）")
        return 0

    logger.info(f"📡 开始拉取订阅 {row['name']}")
    try:
        sources = await fetch_subscription(row["name"], row["uid"], row["url"])
        fetched = 0
        if sources:
            hosts_data = [{"host": s["host"], "geoRegion": s.get("geoRegion", ""), "geoOperator": s.get("geoOperator", "")} for s in sources]
            fetched = await process_source_data(row["uid"], hosts_data)
        return fetched
    except Exception as e:
        logger.error(f"❌ 拉取订阅 {row['name']} 失败: {e}")
        return 0