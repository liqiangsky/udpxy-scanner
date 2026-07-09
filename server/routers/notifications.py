"""
消息中心路由：SSE 实时推送 + 消息 CRUD
"""
import asyncio
import logging
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from services.event_bus import event_bus
from services.message_service import (
    get_messages, mark_read, delete_message, delete_all_messages, get_unread_count
)
from routers.auth import _sessions, SESSION_TTL

logger = logging.getLogger("消息中心")
router = APIRouter()


def _verify_token(token: str) -> bool:
    """SSE 端点自己验证 token，因为 main.py 豁免了该路径。
    使用查询参数 ?token=xxx 传 token（EventSource 不支持自定义请求头）。
    """
    if token in _sessions:
        import time as _time
        session = _sessions[token]
        if _time.time() - session.get("created_at", 0) <= SESSION_TTL:
            return True
        if token in _sessions:
            del _sessions[token]
    return False


@router.get("/events")
async def sse_events(token: str = Query("")):
    """SSE 实时事件推送。前端用 EventSource('/api/events?token=xxx') 连接"""
    if not _verify_token(token):
        raise HTTPException(401, "未认证")

    # 注册当前任务以便服务器关闭时能强制取消
    current_task = asyncio.current_task()
    if current_task:
        event_bus.register_sse_task(current_task)

    # 传入 token 校验回调，每 30s 心跳时自动重验
    return StreamingResponse(
        event_bus.event_generator(check_valid=lambda: _verify_token(token)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/messages")
def api_get_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    msg_type: str = Query(None),
):
    """获取消息列表"""
    return get_messages(page=page, page_size=page_size, unread_only=unread_only, msg_type=msg_type)


@router.get("/messages/unread-count")
def api_unread_count():
    """获取未读消息数"""
    return {"unread": get_unread_count()}


@router.post("/messages/{msg_id}/read")
def api_mark_read(msg_id: int):
    """标记单条已读"""
    mark_read(message_id=msg_id)
    return {"ok": True}


@router.post("/messages/read-all")
def api_mark_read_all(msg_type: str = Query(None)):
    """标记全部已读，可选按消息类型筛选"""
    mark_read(all=True, msg_type=msg_type)
    return {"ok": True}


@router.delete("/messages/{msg_id}")
def api_delete_message(msg_id: int):
    """删除单条消息"""
    delete_message(msg_id)
    return {"ok": True}


@router.post("/messages/delete-all")
def api_delete_all_messages(msg_type: str = Query(None), unread_only: bool = Query(False)):
    """批量删除消息，可选按消息类型/未读筛选"""
    delete_all_messages(msg_type=msg_type, unread_only=unread_only)
    return {"ok": True}
