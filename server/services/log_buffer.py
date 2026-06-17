"""
内存日志 buffer：捕获最近 N 条日志，供前端查看
"""
import logging
from collections import deque

# 全局环形 buffer，最多保留 500 条
MAX_LOGS = 500
log_buffer = deque(maxlen=MAX_LOGS)


class LogBufferHandler(logging.Handler):
    """自定义日志 Handler，把日志写入 deque"""

    def emit(self, record):
        try:
            log_buffer.append(self.format(record))
        except Exception:
            pass


def setup_log_buffer():
    """将自定义 Handler 挂载到根 logger，捕获所有模块日志"""
    handler = LogBufferHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logging.getLogger().addHandler(handler)


def get_recent_logs(lines: int = 100, level: str = None) -> list:
    """获取最近 N 条日志，可选按级别过滤"""
    result = list(log_buffer)[-lines:]
    if level:
        level_upper = level.upper()
        result = [line for line in result if f"[{level_upper}]" in line]
    return result
