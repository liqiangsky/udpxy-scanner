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

from db.database import init_db, init_cache_db, init_iptv_db, get_setting
from services.log_buffer import setup_log_buffer
from routers import settings, configs, iptv, cron, auth, subscriptions  # 导入拆分出去的路由模块

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
    init_cache_db()
    init_iptv_db()
    yield

app = FastAPI(title="udpxy-scanner", lifespan=system_lifespan)

# 跨域设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 内存 session 存储（由 auth 模块导入）
from routers.auth import _sessions as auth_sessions


@app.middleware("http")
async def check_auth(request, call_next):
    """所有接口需要登录 session 认证"""
    # 豁免路径：登录、登出、外部推送
    if request.url.path in ("/api/login", "/api/logout", "/api/source/push", "/api/cron/heartbeat", "/api/source-cache/list", "/api/source-cache/delete"):
        return await call_next(request)

    # 用户登录 session 认证
    auth_token = request.headers.get("X-Auth-Token", "")
    if auth_token and auth_token in auth_sessions:
        return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "未认证"})


# 🔌 像插排一样，把各个子路由插进来
app.include_router(auth.router, prefix="/api", tags=["认证"])
app.include_router(settings.router, prefix="/api", tags=["全局设置"])
app.include_router(configs.router, prefix="/api", tags=["扫描配置"])
app.include_router(iptv.router, prefix="/api", tags=["纯净活源池"])
app.include_router(cron.router, prefix="/api", tags=["定时心跳"])
app.include_router(subscriptions.router, prefix="/api", tags=["数据源订阅"])
