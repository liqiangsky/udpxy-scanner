# main.py
import os
import time
os.environ["TZ"] = "Asia/Shanghai"
if hasattr(time, "tzset"):
    time.tzset()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import json

from db.database import init_db
from services.log_buffer import setup_log_buffer
from routers import settings, configs, hosts, subscriptions, notifications, heartbeat, recheck

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

@asynccontextmanager
async def system_lifespan(app: FastAPI):
    # 启动
    setup_log_buffer()
    init_db()
    import asyncio
    from services.scheduler import handle_heartbeat
    from services.notification_service import set_main_loop

    # 保存主 event loop 引用，供后台线程安全发布 SSE 事件
    set_main_loop(asyncio.get_running_loop())

    # 内置心跳调度器：每分钟自动触发定时任务检查
    async def heartbeat_scheduler():
        import datetime as _dt
        logger = logging.getLogger("定时任务")
        logger.info("❤️ 内置心跳调度器已启动，每分钟检查定时任务")
        now = _dt.datetime.now()
        await asyncio.sleep(60 - now.second)
        while True:
            try:
                triggered = await handle_heartbeat()
                if triggered:
                    logger.info(f"❤️ 心跳触发 {len(triggered)} 个任务: {[t['task'] for t in triggered]}")
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❤️ 心跳调度异常: {e}")

    task = asyncio.create_task(heartbeat_scheduler())
    yield
    task.cancel()
    from services.event_bus import event_bus
    event_bus.clear_all()

app = FastAPI(title="udpxy-scanner", lifespan=system_lifespan)

# 跨域设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def wrap_api_response(request, call_next):
    """统一接口返回格式：{code, msg, data}，全部返回 200，通过 code 区分"""
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    if not ct.startswith("application/json"):
        return response

    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(content=json.loads(body), status_code=200)

    if response.status_code < 400:
        wrapped = {"code": 200, "msg": "success", "data": data}
    else:
        detail = data.get("detail", str(response.status_code)) if isinstance(data, dict) else str(data)
        wrapped = {"code": response.status_code, "msg": detail, "data": None}

    return JSONResponse(content=wrapped, status_code=200)


# 🔌 像插排一样，把各个子路由插进来
app.include_router(settings.router, prefix="/api", tags=["全局设置"])
app.include_router(configs.router, prefix="/api", tags=["扫描配置"])
app.include_router(hosts.router, prefix="/api", tags=["纯净主机池"])
app.include_router(heartbeat.router, prefix="/api", tags=["心跳保活"])
app.include_router(recheck.router, prefix="/api", tags=["复测任务"])
app.include_router(subscriptions.router, prefix="/api", tags=["数据源订阅"])
app.include_router(notifications.router, prefix="/api", tags=["实时通知"])
