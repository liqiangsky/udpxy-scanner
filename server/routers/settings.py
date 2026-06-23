from fastapi import APIRouter, Query
from db.database import get_db, get_setting, _settings_cache, _settings_cache_lock
from db.models import GlobalSettingsUpdate
from services.log_buffer import get_recent_logs

router = APIRouter()


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
    with _settings_cache_lock:
        _settings_cache.clear()
    return {"ok": True}


@router.get("/logs")
def api_get_logs(
    lines: int = Query(100, ge=10, le=500),
    level: str = Query(None)
):
    logs = get_recent_logs(lines=lines, level=level)
    return {"logs": logs, "total": len(logs)}
