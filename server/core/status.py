import threading
import time

class TaskRunnerStatus:
    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._should_stop = False
        self._current_index = 0
        self._total = 0
        self._current_name = ""
        self._config_ids = []
        self._skip_config_ids = set()
        self._scanning_config_id = None

        # 复测协调
        self._rechecking = False
        self._pause_recheck = False

    def start(self, total_count: int, config_ids: list = None):
        # 等待复测完成（最多等 5 分钟）
        with self._lock:
            self._pause_recheck = True  # 先标记暂停，复测 worker 收到后进入等待
        waited = 0
        while waited < 300:
            with self._lock:
                if not self._rechecking:
                    break
            time.sleep(2)
            waited += 2

        with self._lock:
            self._rechecking = False
            self._pause_recheck = False
            self._running = True
            self._should_stop = False
            self._current_index = 0
            self._total = total_count
            self._current_name = ""
            self._skip_config_ids = set()
            self._scanning_config_id = None
            if config_ids:
                self._config_ids = config_ids

    def stop(self):
        """停止整个任务队列"""
        with self._lock:
            self._should_stop = True

    def stop_current_and_continue(self, config_id: int):
        """停止当前扫描，并标记该配置为跳过，剩余配置继续执行"""
        with self._lock:
            self._skip_config_ids.add(config_id)
            self._should_stop = True
            self._scanning_config_id = config_id

    def should_stop(self) -> bool:
        with self._lock:
            # 如果配置已停止，worker 应该退出
            if self._scanning_config_id is not None:
                return True
            return self._should_stop

    def clear_interrupt(self):
        """清除中断标记，允许下一个配置正常执行"""
        with self._lock:
            self._scanning_config_id = None

    def get_scanning_config_id(self):
        with self._lock:
            return self._scanning_config_id

    def is_config_skipped(self, config_id: int) -> bool:
        with self._lock:
            return config_id in self._skip_config_ids

    def pop_skipped_configs(self) -> list:
        """获取被跳过的配置 ID，并清空列表"""
        with self._lock:
            ids = list(self._skip_config_ids)
            self._skip_config_ids.clear()
            self._scanning_config_id = None
            return ids

    def remove_from_queue(self, config_id: int):
        """从队列中移除配置"""
        with self._lock:
            if config_id in self._config_ids:
                self._config_ids.remove(config_id)
                self._total = len(self._config_ids)
                return True
            return False

    def finish(self):
        with self._lock:
            # 当前项之后是否还有排队任务
            remaining = len(self._config_ids) - self._current_index - 1
            self._scanning_config_id = None
            self._current_index = 0
            self._total = 0
            self._current_name = ""
            self._pause_recheck = False
            self._running = remaining > 0
            # 无剩余任务时清空队列，避免残留ID影响progress接口
            if remaining <= 0:
                self._config_ids = []

    def is_idle(self) -> bool:
        with self._lock: return not self._running

    def set_rechecking(self):
        """标记复测开始"""
        with self._lock:
            self._rechecking = True
            self._pause_recheck = False

    def clear_rechecking(self):
        """标记复测结束"""
        with self._lock:
            self._rechecking = False
            self._pause_recheck = False

    def should_pause_recheck(self) -> bool:
        """复测 worker 检查是否应该暂停"""
        with self._lock:
            return self._pause_recheck

    def enqueue(self, config_ids: list):
        """运行时追加配置到队列末尾，跳过已在队列中的"""
        with self._lock:
            existing = set(self._config_ids)
            new_ids = [cid for cid in config_ids if cid not in existing]
            self._config_ids.extend(new_ids)
            self._total = len(self._config_ids)
            return self._total

    def update_progress(self, index: int, name: str):
        with self._lock:
            self._current_index = index
            self._current_name = name

    def get_progress(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "should_stop": self._should_stop,
                "current_index": self._current_index,
                "total": self._total,
                "current_config_name": self._current_name,
                "config_ids": list(self._config_ids)
            }

task_runner = TaskRunnerStatus()
