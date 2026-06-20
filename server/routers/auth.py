import hashlib
import os
import uuid
import time
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from db.database import get_db, get_setting

router = APIRouter()

# 简单内存存储 session
_sessions: dict[str, dict] = {}

# 登录失败限制：key=IP, value={count, locked_until}
_login_attempts: dict[str, dict] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 分钟
SESSION_TTL = 7 * 24 * 3600  # 7 天


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_rate_limit(client_ip: str):
    """检查是否被锁定"""
    if client_ip not in _login_attempts:
        return
    record = _login_attempts[client_ip]
    if time.time() < record.get("locked_until", 0):
        remaining = int(record["locked_until"] - time.time())
        raise HTTPException(429, f"登录被锁定，请 {remaining} 秒后重试")


def record_failure(client_ip: str):
    """记录登录失败"""
    if client_ip not in _login_attempts:
        _login_attempts[client_ip] = {"count": 0, "locked_until": 0}
    _login_attempts[client_ip]["count"] += 1
    if _login_attempts[client_ip]["count"] >= MAX_FAILED_ATTEMPTS:
        _login_attempts[client_ip]["locked_until"] = time.time() + LOCKOUT_SECONDS


def reset_attempts(client_ip: str):
    """登录成功后重置计数"""
    if client_ip in _login_attempts:
        del _login_attempts[client_ip]


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def api_login(request: Request, req: LoginRequest):
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    stored_hash = get_setting("password_hash", "")
    if not stored_hash:
        raise HTTPException(500, "密码未初始化")

    if hash_password(req.password) != stored_hash:
        record_failure(client_ip)
        raise HTTPException(401, "密码错误")

    reset_attempts(client_ip)
    token = uuid.uuid4().hex
    now = int(time.time())
    _sessions[token] = {
        "created_at": now,
    }
    return {"ok": True, "token": token, "expires_in": SESSION_TTL}


class LogoutRequest(BaseModel):
    token: str = ""


@router.post("/logout")
def api_logout(data: LogoutRequest):
    if data.token in _sessions:
        del _sessions[data.token]
    return {"ok": True}


class ChangePasswordRequest(BaseModel):
    oldPassword: str
    newPassword: str


@router.post("/change-password")
def api_change_password(req: ChangePasswordRequest):
    stored_hash = get_setting("password_hash", "")
    if hash_password(req.oldPassword) != stored_hash:
        raise HTTPException(400, "旧密码错误")
    if len(req.newPassword) < 4:
        raise HTTPException(400, "新密码至少 4 位")
    new_hash = hash_password(req.newPassword)
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('password_hash', ?)", (new_hash,))
    # 清除所有已有 session，强制重新登录
    _sessions.clear()
    return {"ok": True, "msg": "密码已修改，请重新登录"}
