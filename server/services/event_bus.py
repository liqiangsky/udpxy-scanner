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

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

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
                    yield f"event: message\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: heartbeat\ndata: {json.dumps({'ok': True})}\n\n"
                # 每次迭代（消息或心跳）都检查 token 有效性
                if check_valid and not check_valid():
                    logger.info("⛔ SSE 连接关闭：token 已失效")
                    break
        finally:
            self.unsubscribe(q)


# 全局单例
event_bus = EventBus()
