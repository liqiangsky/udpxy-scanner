"""
SSE 事件总线：支持推送/订阅，组件解耦
"""
import asyncio
import json
import time
import logging
from typing import AsyncGenerator

logger = logging.getLogger("事件总线")


class EventBus:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._sse_tasks: set[asyncio.Task] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    def register_sse_task(self, task: asyncio.Task):
        self._sse_tasks.add(task)

    def unregister_sse_task(self, task: asyncio.Task):
        self._sse_tasks.discard(task)

    def clear_all(self):
        """关闭所有 SSE 订阅连接，用于服务器优雅关闭"""
        # 发送关闭信号到所有队列（给等待中的生成器）
        for q in self._subscribers:
            try:
                q.put_nowait("__SHUTDOWN__")
            except asyncio.QueueFull:
                pass
        self._subscribers.clear()
        # 直接取消所有 SSE 任务（任务会被 CancelledError 唤醒）
        for task in list(self._sse_tasks):
            if not task.done():
                task.cancel()
        self._sse_tasks.clear()

    async def publish(self, event_type: str, data: dict):
        """向所有订阅者推送事件"""
        payload = json.dumps({"type": event_type, "data": data, "ts": int(time.time())}, ensure_ascii=False)
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)

    async def event_generator(self, check_valid=None) -> AsyncGenerator[str, None]:
        """SSE 生成器
        check_valid: 可选的回调函数，每次心跳时调用，返回 False 则关闭连接
        """
        q = self.subscribe()
        try:
            # 发送初始心跳
            yield f"event: heartbeat\ndata: {json.dumps({'ok': True})}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                    if payload == "__SHUTDOWN__":
                        logger.info("🛑 SSE 连接关闭：服务器正在关闭")
                        break
                    yield f"event: message\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: heartbeat\ndata: {json.dumps({'ok': True})}\n\n"
                except asyncio.CancelledError:
                    logger.info("🛑 SSE 连接关闭：任务已取消")
                    break
                # 每次迭代（消息或心跳）都检查 token 有效性
                if check_valid and not check_valid():
                    logger.info("⛔ SSE 连接关闭：token 已失效")
                    break
        finally:
            self.unsubscribe(q)
            # 从 SSE 任务追踪中移除自己
            current = asyncio.current_task()
            if current:
                self.unregister_sse_task(current)


# 全局单例
event_bus = EventBus()
