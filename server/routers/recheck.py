from fastapi import APIRouter


router = APIRouter()


@router.post("/recheck")
async def api_recheck():
    """
    手动触发活源复测（二次验证模式）。
    后台异步执行，不阻塞返回。
    """
    from fastapi import HTTPException
    from core.status import task_runner
    from services.scheduler import execute_recheck
    import threading
    import asyncio

    if not task_runner.is_idle():
        raise HTTPException(400, "扫描任务运行中")

    def run_recheck():
        asyncio.run(execute_recheck())

    threading.Thread(target=run_recheck, daemon=True).start()
    return {"ok": True, "msg": "已启动复测"}
