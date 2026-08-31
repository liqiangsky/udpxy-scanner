from fastapi import APIRouter, Query
from db.database import get_db, get_setting, _settings_cache, _settings_cache_lock, db_write_lock
from db.models import GlobalSettingsUpdate, Parameter
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
    with db_write_lock:
        with get_db() as session:
            settings_map = {
                "concurrency": str(data.concurrency),
                "timeout": str(data.timeout),
                "config_delay": str(data.config_delay),
                "janitor_cron": data.janitor_cron,
                "scan_cron": data.scan_cron,
                "push_api_key": data.push_api_key,
            }
            for key, value in settings_map.items():
                row = session.query(Parameter).filter(Parameter.key == key).first()
                if row:
                    row.value = value
                else:
                    session.add(Parameter(key=key, value=value))
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
