from fastapi import APIRouter


router = APIRouter()


@router.post("/heartbeat")
async def api_heartbeat():
    """
    心跳保活接口。
    定时任务已由内置调度器每分钟自动处理，此接口仅用于防止服务器休眠（如 HF Spaces）。
    """
    return {"ok": True}
