from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from db.database import get_db, get_iptv_db, get_setting
from db.models import GlobalSettingsUpdate
from services.log_buffer import get_recent_logs
import hashlib

router = APIRouter()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@router.get("/settings")
def api_get_settings():
    return {
        "engine": {
            "concurrency": int(get_setting("concurrency", "64")),
            "timeout": int(get_setting("timeout", "2000")),
            "configDelay": int(get_setting("config_delay", "3"))
        },
        "scheduling": {
            "scanCron": get_setting("scan_cron", ""),
            "janitorCron": get_setting("janitor_cron", "")
        },
        "pushApiKey": get_setting("push_api_key", "")
    }


@router.put("/settings")
def api_update_settings(data: GlobalSettingsUpdate):
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('concurrency', ?)", (str(data.concurrency),))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('timeout', ?)", (str(data.timeout),))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('config_delay', ?)", (str(data.configDelay),))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('janitor_cron', ?)", (data.janitorCron,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('scan_cron', ?)", (data.scanCron,))
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('push_api_key', ?)", (data.pushApiKey,))
    return {"ok": True}


@router.get("/logs")
def api_get_logs(
    lines: int = Query(100, ge=10, le=500),
    level: str = Query(None)
):
    """获取最近日志，可选按级别过滤 (INFO/WARNING/ERROR)"""
    logs = get_recent_logs(lines=lines, level=level)
    return {"logs": logs, "total": len(logs)}


class IptvImportItem(BaseModel):
    id: int = None
    host: str
    ip: str
    port: int
    sourceType: str = ""
    sourceName: str = ""
    region: str = ""
    operator: str = ""
    geoRegion: str = ""
    geoOperator: str = ""
    delay: int = 0
    protocol: str = ""
    target: str = ""
    channelName: str = ""
    createTime: int = 0
    updateTime: int = 0


@router.get("/iptv-db/list")
def api_iptv_db_list():
    """
    查询 iptv_list.db 中的活源数据。
    """
    with get_iptv_db() as conn:
        rows = conn.execute("SELECT * FROM iptv_list ORDER BY id").fetchall()
    return {"total": len(rows), "data": [dict(r) for r in rows]}


@router.post("/iptv-db/import")
def api_iptv_db_import(items: list[IptvImportItem]):
    """
    批量导入活源数据到 iptv_list.db。
    支持 ON CONFLICT 覆盖更新。
    """
    now = int(__import__("time").time() * 1000)
    with get_iptv_db() as conn:
        imported = 0
        for item in items:
            conn.execute("""
                INSERT OR REPLACE INTO iptv_list (
                    id, host, ip, port, sourceType, sourceName,
                    region, operator, geoRegion, geoOperator,
                    delay, protocol, target, channelName,
                    createTime, updateTime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.id, item.host, item.ip, item.port,
                item.sourceType, item.sourceName,
                item.region, item.operator,
                item.geoRegion, item.geoOperator,
                item.delay, item.protocol, item.target, item.channelName,
                item.createTime or now, item.updateTime or now
            ))
            imported += 1
    return {"ok": True, "imported": imported}
