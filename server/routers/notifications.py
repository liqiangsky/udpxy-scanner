"""
通知路由：SSE 实时推送
"""
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from services.event_bus import event_bus

logger = logging.getLogger("通知路由")
router = APIRouter()


@router.get("/events")
async def sse_events():
    """SSE 实时事件推送。前端用 EventSource('/api/events') 连接"""
    return StreamingResponse(
        event_bus.event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
