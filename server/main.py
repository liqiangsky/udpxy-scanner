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
from routers import settings, configs, hosts, cron, auth, subscriptions

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
    yield

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
    # 豁免路径：登录、登出、外部推送、cron心跳
    if request.url.path in ("/api/login", "/api/logout", "/api/source/push", "/api/cron/heartbeat", "/api/source-cache/list"):
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
app.include_router(hosts.router, prefix="/api", tags=["纯净活源池"])
app.include_router(cron.router, prefix="/api", tags=["定时心跳"])
app.include_router(subscriptions.router, prefix="/api", tags=["数据源订阅"])
