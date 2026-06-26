"""API 订阅管理路由"""
import logging
import threading
import asyncio
from fastapi import APIRouter, HTTPException
from db.database import get_db, get_cache_db
from db.models import ApiSubscriptionCreate
from services.source_cache import process_source_data
from services.subscription_fetcher import fetch_subscription

logger = logging.getLogger("订阅管理")
router = APIRouter()


@router.get("/subscriptions")
def api_list_subscriptions():
    """获取所有 API 订阅"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM api_subscriptions ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/subscriptions")
def api_create_subscription(data: ApiSubscriptionCreate):
    """创建 API 订阅"""
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO api_subscriptions (name, uid, url, enabled, fetchCron) VALUES (?, ?, ?, ?, ?)",
                (data.name, data.uid, data.url, 1 if data.enabled else 0, data.fetchCron)
            )
            sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        except Exception as e:
            raise HTTPException(400, f"创建失败（uid 可能重复）: {e}")
    return {"ok": True, "id": sub_id}


@router.put("/subscriptions/{sub_id}")
def api_update_subscription(sub_id: int, data: ApiSubscriptionCreate):
    """更新 API 订阅"""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM api_subscriptions WHERE id=?", (sub_id,)).fetchone()
        if not row:
            raise HTTPException(404, "订阅不存在")
        old = conn.execute("SELECT uid FROM api_subscriptions WHERE id=?", (sub_id,)).fetchone()
        old_uid = old["uid"]
        conn.execute(
            "UPDATE api_subscriptions SET name=?, uid=?, url=?, enabled=?, fetchCron=?, updatedAt=datetime('now') WHERE id=?",
            (data.name, data.uid, data.url, 1 if data.enabled else 0, data.fetchCron, sub_id)
        )
        # uid 变更时同步更新 source_cache 中的 sourceType
        if old_uid != data.uid:
            with get_cache_db() as cconn:
                cconn.execute(
                    "UPDATE source_cache SET sourceType=? WHERE sourceType=?",
                    (data.uid, old_uid)
                )
    return {"ok": True}


@router.delete("/subscriptions/{sub_id}")
def api_delete_subscription(sub_id: int):
    """删除 API 订阅并清除对应的 source_cache"""
    with get_db() as conn:
        row = conn.execute("SELECT uid FROM api_subscriptions WHERE id=?", (sub_id,)).fetchone()
        if not row:
            raise HTTPException(404, "订阅不存在")
        uid = row["uid"]
        conn.execute("DELETE FROM api_subscriptions WHERE id=?", (sub_id,))
    with get_cache_db() as conn:
        conn.execute("DELETE FROM source_cache WHERE sourceType=?", (uid,))
    logger.info(f"🗑️ [订阅删除] uid={uid}")
    return {"ok": True}


@router.post("/subscriptions/{sub_id}/fetch")
def api_fetch_subscription(sub_id: int):
    """手动触发单个订阅拉取，后台异步执行"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM api_subscriptions WHERE id=? AND enabled=1",
            (sub_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "订阅不存在或未启用")

    sub_info = dict(row)

    def run_fetch():
        async def _do():
            logger.info(f"📡 开始拉取订阅 {sub_info['name']}")
            sources = await fetch_subscription(sub_info["name"], sub_info["uid"], sub_info["url"])
            if sources:
                hosts_data = [{"host": s["host"], "geoRegion": s.get("geoRegion", ""), "geoOperator": s.get("geoOperator", "")} for s in sources]
                await process_source_data(sub_info["uid"], hosts_data)
            from datetime import datetime
            with get_db() as conn:
                conn.execute(
                    "UPDATE api_subscriptions SET lastFetchAt=? WHERE id=?",
                    (datetime.now().isoformat(), sub_info["id"])
                )
            logger.info(f"✅ 订阅 {sub_info['name']} 拉取完成")
        # Python 3.10+ 中 asyncio.run() 可安全地从非主线程调用（自动创建新事件循环）
        asyncio.run(_do())

    threading.Thread(target=run_fetch, daemon=True).start()
    return {"ok": True, "msg": f"订阅「{sub_info['name']}」拉取任务已在后台启动"}


@router.post("/subscriptions/fetch-all")
async def api_fetch_all_subscriptions():
    """手动触发所有已启用订阅拉取"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM api_subscriptions WHERE enabled=1"
        ).fetchall()

    async def _fetch_one(row):
        logger.info(f"📡 开始拉取订阅 {row['name']}")
        try:
            sources = await fetch_subscription(row["name"], row["uid"], row["url"])
            fetched = 0
            if sources:
                hosts_data = [{"host": s["host"], "geoRegion": s.get("geoRegion", ""), "geoOperator": s.get("geoOperator", "")} for s in sources]
                fetched = await process_source_data(row["uid"], hosts_data)
            return {"uid": row["uid"], "name": row["name"], "fetched": fetched}
        except Exception as e:
            logger.error(f"❌ 拉取订阅 {row['name']} 失败: {e}")
            return {"uid": row["uid"], "name": row["name"], "fetched": 0, "error": str(e)}

    results = await asyncio.gather(*(_fetch_one(dict(r)) for r in rows))
    results = list(results)

    from datetime import datetime
    now = datetime.now().isoformat()
    with get_db() as conn:
        for row in rows:
            conn.execute(
                "UPDATE api_subscriptions SET lastFetchAt=? WHERE id=?",
                (now, row["id"])
            )

    return {"ok": True, "results": results}