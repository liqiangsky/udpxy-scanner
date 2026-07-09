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

from db.database import init_db, get_setting
from services.log_buffer import setup_log_buffer
from routers import settings, configs, hosts, auth, subscriptions, notifications, heartbeat, recheck

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
    # init_db 已创建全部表
    import asyncio
    from services.event_bus import event_bus
    from services.scheduler import handle_heartbeat

    # 发送启动消息
    asyncio.create_task(event_bus.publish("system", {"message": "服务已启动"}))

    # 内置心跳调度器：每分钟自动触发定时任务检查，无需外部 crontab
    async def heartbeat_scheduler():
        import datetime as _dt
        logger = logging.getLogger("定时任务")
        logger.info("❤️ 内置心跳调度器已启动，每分钟检查定时任务")
        # 对齐到下一分钟起始，确保首次检查落在整分钟边界
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
    # 关闭所有 SSE 连接，让 Uvicorn 能优雅退出，避免按两次 Ctrl+C
    event_bus.clear_all()

app = FastAPI(title="udpxy-scanner", lifespan=system_lifespan)

# 跨域设置（使用 X-Auth-Token 认证，无需 allow_credentials）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 内存 session 存储（由 auth 模块导入）
from routers.auth import _sessions as auth_sessions, SESSION_TTL


@app.middleware("http")
async def check_auth(request, call_next):
    """所有接口需要登录 session 认证"""
    # 豁免路径：登录、登出、外部推送、心跳保活
    if request.url.path in ("/api/login", "/api/logout", "/api/source/push", "/api/heartbeat", "/api/events"):
        return await call_next(request)

    # 用户登录 session 认证
    auth_token = request.headers.get("X-Auth-Token", "")
    if auth_token and auth_token in auth_sessions:
        import time as _time
        session = auth_sessions[auth_token]
        if _time.time() - session.get("created_at", 0) <= SESSION_TTL:
            return await call_next(request)
        else:
            del auth_sessions[auth_token]

    return JSONResponse(status_code=401, content={"detail": "未认证"})


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
        return JSONResponse(content=body.decode(), status_code=200)

    if response.status_code < 400:
        wrapped = {"code": 200, "msg": "success", "data": data}
    else:
        detail = data.get("detail", str(response.status_code)) if isinstance(data, dict) else str(data)
        wrapped = {"code": response.status_code, "msg": detail, "data": None}

    return JSONResponse(content=wrapped, status_code=200)


# 🔌 像插排一样，把各个子路由插进来
app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(settings.router, prefix="/api", tags=["全局设置"])
app.include_router(configs.router, prefix="/api", tags=["扫描配置"])
app.include_router(hosts.router, prefix="/api", tags=["纯净主机池"])
app.include_router(heartbeat.router, prefix="/api", tags=["心跳保活"])
app.include_router(recheck.router, prefix="/api", tags=["复测任务"])
app.include_router(subscriptions.router, prefix="/api", tags=["数据源订阅"])
app.include_router(notifications.router, prefix="/api", tags=["消息中心"])
