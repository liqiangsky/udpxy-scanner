from fastapi import APIRouter
from services.cron_heartbeat import handle_heartbeat

router = APIRouter()


@router.post("/cron/heartbeat")
async def api_cron_heartbeat():
    """
    手动触发一次 cron 任务检查。
    应用启动后内置调度器会自动运行，此端点用于手动触发或调试。
    """
    triggered = await handle_heartbeat()
    return {
        "ok": True,
        "triggered": len(triggered),
        "tasks": triggered
    }


@router.post("/cron/recheck")
async def api_cron_recheck():
    """
    手动触发活源复测（二次验证模式）。
    后台异步执行，不阻塞返回。
    """
    from fastapi import HTTPException
    from core.status import task_runner
    from services.cron_heartbeat import execute_recheck
    import threading
    import asyncio

    if not task_runner.is_idle():
        raise HTTPException(400, "当前有运行中的扫描任务")

    def run_recheck():
        asyncio.run(execute_recheck())

    threading.Thread(target=run_recheck, daemon=True).start()
    return {"ok": True, "msg": "复测任务已在后台启动"}
