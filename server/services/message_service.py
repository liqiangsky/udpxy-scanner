"""
消息服务：异步操作结果的通知存储与查询
"""
import logging
import time
import math
from typing import Optional
from db.database import get_db, db_write_lock

logger = logging.getLogger("消息中心")

# 消息类型枚举
MSG_TYPE_INFO = "info"
MSG_TYPE_SUCCESS = "success"
MSG_TYPE_WARNING = "warning"
MSG_TYPE_ERROR = "error"


def create_message(msg_type: str, title: str, content: str = "", source: str = ""):
    """创建一条消息并推送到 SSE"""
    now = int(time.time())
    with db_write_lock:
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO notification (type, title, content, source, read, createdAt) VALUES (?, ?, ?, ?, 0, ?)",
                (msg_type, title, content, source, now)
            )
            msg_id = cur.lastrowid
    logger.info(f"📬 [消息] [{msg_type}] {title}")
    # 异步推送到 SSE
    from services.event_bus import event_bus
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(event_bus.publish("notification", {
                "id": msg_id,
                "type": msg_type,
                "title": title,
                "content": content,
                "source": source,
                "createdAt": now,
            }))
    except RuntimeError:
        pass
    return msg_id


def get_messages(
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
    msg_type: Optional[str] = None,
) -> dict:
    """查询消息列表，支持分页和筛选"""
    where = []
    params = []

    if unread_only:
        where.append("read = 0")
    if msg_type:
        where.append("type = ?")
        params.append(msg_type)

    where_sql = " AND ".join(where) if where else "1=1"

    if page < 1:
        page = 1
    page_size = max(1, min(page_size, 100))

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM notification WHERE {where_sql}",
            params
        ).fetchone()["cnt"]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM notification WHERE {where_sql} ORDER BY createdAt DESC, id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        ).fetchall()

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "type": r["type"],
            "title": r["title"],
            "content": r["content"] or "",
            "source": r["source"] or "",
            "read": bool(r["read"]),
            "createdAt": r["createdAt"],
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": math.ceil(total / page_size) if page_size > 0 else 0,
        "unread": get_unread_count(),
    }


def get_unread_count() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM notification WHERE read=0").fetchone()
        return row["cnt"]


def mark_read(message_id: int = None, all: bool = False, msg_type: str = None):
    """标记消息已读，支持按消息类型筛选"""
    with db_write_lock:
        with get_db() as conn:
            if all:
                if msg_type:
                    conn.execute("UPDATE notification SET read=1 WHERE read=0 AND type=?", (msg_type,))
                else:
                    conn.execute("UPDATE notification SET read=1 WHERE read=0")
            elif message_id:
                conn.execute("UPDATE notification SET read=1 WHERE id=?", (message_id,))


def delete_message(message_id: int):
    with db_write_lock:
        with get_db() as conn:
            conn.execute("DELETE FROM notification WHERE id=?", (message_id,))


def delete_all_messages(msg_type: str = None, unread_only: bool = False):
    """批量删除消息，支持按消息类型和未读筛选"""
    with db_write_lock:
        with get_db() as conn:
            where = []
            params = []
            if unread_only:
                where.append("read = 0")
            if msg_type:
                where.append("type = ?")
                params.append(msg_type)
            if where:
                conn.execute(f"DELETE FROM notification WHERE {' AND '.join(where)}", params)
            else:
                conn.execute("DELETE FROM notification")
