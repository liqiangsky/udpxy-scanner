"""
内存日志 buffer：捕获最近 N 条日志，供前端查看
"""
import logging
from collections import deque

MAX_LOGS = 500
log_buffer = deque(maxlen=MAX_LOGS)

_LEVEL_NO = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class LogBufferHandler(logging.Handler):
    def emit(self, record):
        try:
            log_buffer.append((record.levelno, self.format(record)))
        except Exception:
            pass


def setup_log_buffer():
    handler = LogBufferHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logging.getLogger().addHandler(handler)


def get_recent_logs(lines: int = 100, level: str = None) -> list:
    result = list(log_buffer)[-lines:]
    if level:
        min_level = _LEVEL_NO.get(level.upper(), 0)
        result = [text for lvl, text in result if lvl >= min_level]
    else:
        result = [text for _, text in result]
    return result
