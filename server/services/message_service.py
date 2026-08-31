"""
消息服务：异步操作结果的通知存储与查询
"""
import logging
import time
import math
from typing import Optional
from db.database import get_db, db_write_lock, _row_to_dict
from db.models import Notification

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
        with get_db() as session:
            msg = Notification(
                type=msg_type,
                title=title,
                content=content,
                source=source,
                read=0,
                created_at=now,
            )
            session.add(msg)
            session.flush()
            msg_id = msg.id
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
    with get_db() as session:
        query = session.query(Notification)

        if unread_only:
            query = query.filter(Notification.read == 0)
        if msg_type:
            query = query.filter(Notification.type == msg_type)

        total = query.count()

        if page < 1:
            page = 1
        page_size = max(1, min(page_size, 100))

        offset = (page - 1) * page_size
        rows = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(page_size).offset(offset).all()

        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "type": r.type,
                "title": r.title,
                "content": r.content or "",
                "source": r.source or "",
                "read": bool(r.read),
                "createdAt": r.created_at,
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
    with get_db() as session:
        return session.query(Notification).filter(Notification.read == 0).count()


def mark_read(message_id: int = None, all: bool = False, msg_type: str = None):
    """标记消息已读，支持按消息类型筛选"""
    with db_write_lock:
        with get_db() as session:
            if all:
                query = session.query(Notification).filter(Notification.read == 0)
                if msg_type:
                    query = query.filter(Notification.type == msg_type)
                query.update({"read": 1}, synchronize_session="fetch")
            elif message_id:
                session.query(Notification).filter(Notification.id == message_id).update(
                    {"read": 1}, synchronize_session="fetch"
                )


def delete_message(message_id: int):
    with db_write_lock:
        with get_db() as session:
            session.query(Notification).filter(Notification.id == message_id).delete(synchronize_session="fetch")


def delete_all_messages(msg_type: str = None, unread_only: bool = False):
    """批量删除消息，支持按消息类型和未读筛选"""
    with db_write_lock:
        with get_db() as session:
            query = session.query(Notification)
            if unread_only:
                query = query.filter(Notification.read == 0)
            if msg_type:
                query = query.filter(Notification.type == msg_type)
            query.delete(synchronize_session="fetch")
