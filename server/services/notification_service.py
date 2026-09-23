"""
通知服务：创建通知并推送到 SSE（不落库，仅实时推送 + 后端日志记录）
"""
import logging
import asyncio
import time

logger = logging.getLogger("通知服务")

MSG_TYPE_SUCCESS = "success"
MSG_TYPE_ERROR = "error"
MSG_TYPE_INFO = "info"
MSG_TYPE_WARNING = "warning"

# 通知来源标识（用于前端事件名）
NOTIFICATION_SOURCE_SCAN_ENGINE = "SCAN_ENGINE"
NOTIFICATION_SOURCE_SUBSCRIPTION = "SUBSCRIPTION"
NOTIFICATION_SOURCE_RECHECK = "RECHECK"

# 主 event loop 引用（由 startup 事件设置）
_main_loop = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """在主线程中调用，保存 uvicorn 的 event loop 引用"""
    global _main_loop
    _main_loop = loop


def create_notification(msg_type: str, title: str, content: str = "", source: str = "", trigger_event: bool = False):
    """创建通知并推送到 SSE（不落库）
    Args:
        msg_type: 消息类型 (success/error/info/warning)
        title: 通知标题
        content: 通知内容
        source: 来源标识，用于前端事件名（如 SCAN_ENGINE），为空则不派发前端事件
        trigger_event: 是否触发前端自定义事件，默认 False
    """
    now = int(time.time())
    logger.info(f"📬 [通知] [{msg_type}] {title} | {content} | source={source}")
    data = {
        "type": msg_type,
        "title": title,
        "content": content,
        "source": source,
        "triggerEvent": trigger_event,
        "createdAt": now,
    }
    _publish_async(msg_type, data)


def _publish_async(event_type: str, data: dict):
    """在任何线程中安全地发布事件到主 event loop"""
    if _main_loop and _main_loop.is_running():
        from services.event_bus import event_bus
        asyncio.run_coroutine_threadsafe(event_bus.publish(event_type, data), _main_loop)
    else:
        # 兜底：尝试在当前线程运行（开发环境等无主 loop 的场景）
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_do_publish(event_type, data))
        except Exception as e:
            logger.warning(f"通知推送失败: {e}")


async def _do_publish(event_type: str, data: dict):
    from services.event_bus import event_bus
    await event_bus.publish(event_type, data)
