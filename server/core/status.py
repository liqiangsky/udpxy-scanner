import threading
import time


class TaskRunnerStatus:
    """
    扫描队列状态管理。
    - _should_stop: 停止整个队列（stop），循环退出后不再自动续跑
    - _interrupt_current: 中断当前正在执行的配置，跳到下一个（stop_current）
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._should_stop = False
        self._interrupt_current = False
        self._interrupt_target = None  # 中断针对的配置 ID（用于区分 "停止当前任务" 和 "跳过下一个"）
        self._current_index = 0
        self._total = 0
        self._current_name = ""
        self._config_ids = []

        # 复测协调
        self._rechecking = False
        self._pause_recheck = False
        self._recheck_stop_requested = False

    def start(self, total_count: int, config_ids: list = None):
        # 请求复测暂停，等待已有复测 worker 退出（最多等 10 秒）
        with self._lock:
            self._pause_recheck = True
        waited = 0
        while waited < 10:
            with self._lock:
                if not self._rechecking:
                    break
            time.sleep(0.5)
            waited += 0.5

        with self._lock:
            self._rechecking = False
            self._pause_recheck = False
            self._running = True
            self._should_stop = False
            self._interrupt_current = False
            self._current_index = 0
            self._total = total_count
            self._current_name = ""
            if config_ids:
                self._config_ids = list(config_ids)

    def stop(self):
        """停止整个队列：当前任务和所有排队任务都停止"""
        with self._lock:
            self._should_stop = True
            self._interrupt_current = True
            self._interrupt_target = "__all__"  # 特殊标记，表示停止整个队列

    def stop_current_and_continue(self):
        """中断当前正在执行的配置，队列继续执行下一个"""
        with self._lock:
            # 获取当前正在执行的配置 ID
            if self._config_ids and 0 <= self._current_index < len(self._config_ids):
                self._interrupt_target = self._config_ids[self._current_index]
            self._interrupt_current = True

    def should_stop(self) -> bool:
        """整个队列是否已停止"""
        with self._lock:
            return self._should_stop

    def should_interrupt(self) -> bool:
        """当前配置是否需要被中断（整个队列停止 或 当前配置被跳过）"""
        with self._lock:
            return self._interrupt_current

    def get_interrupt_target(self):
        """获取中断针对的配置 ID"""
        with self._lock:
            return self._interrupt_target

    def clear_interrupt(self):
        """清除中断标记，允许下一个配置正常执行"""
        with self._lock:
            self._interrupt_current = False
            self._interrupt_target = None

    def remove_from_queue(self, config_id: int):
        """从队列中移除排队中的配置（同 ID 多个时移除最后一个）。不允许移除已完成或正在执行的。"""
        with self._lock:
            if config_id not in self._config_ids:
                return False
            # 从后往前找，移除最后一个匹配项（避免误删已执行的同 ID 配置）
            for idx in range(len(self._config_ids) - 1, -1, -1):
                if self._config_ids[idx] == config_id:
                    if idx < self._current_index:
                        return False  # 所有匹配项都在已执行区间
                    if idx == self._current_index:
                        return False  # 正在执行，用 stop_current
                    self._config_ids.pop(idx)
                    self._total = len(self._config_ids)
                    return True
            return False

    def get_current_config_id(self) -> int | None:
        """获取当前正在执行的配置 ID"""
        with self._lock:
            if self._config_ids and 0 <= self._current_index < len(self._config_ids):
                return self._config_ids[self._current_index]
            return None

    def get_remaining_ids(self) -> list:
        """获取当前及之后所有排队的配置 ID"""
        with self._lock:
            return list(self._config_ids[self._current_index:])

    def append_to_queue(self, config_id: int):
        """追加配置到队列尾部（线程安全）"""
        with self._lock:
            self._config_ids.append(config_id)
            self._total = len(self._config_ids)

    def get_config_ids(self) -> list:
        """获取当前队列快照（线程安全）"""
        with self._lock:
            return list(self._config_ids)

    def is_idle(self) -> bool:
        with self._lock:
            return not self._running and not self._rechecking

    def finish(self):
        """当前队列执行结束，清理状态"""
        with self._lock:
            self._running = False
            self._interrupt_current = False
            self._current_index = 0
            self._total = 0
            self._current_name = ""
            self._config_ids = []

    def update_progress(self, index: int, name: str):
        with self._lock:
            self._current_index = index
            self._current_name = name

    def get_progress(self) -> dict:
        with self._lock:
            queued_after = self._config_ids[self._current_index + 1:] if self._config_ids and self._current_index < len(self._config_ids) else []
            return {
                "running": self._running,
                "should_stop": self._should_stop,
                "current_index": self._current_index,
                "total": self._total,
                "current_config_name": self._current_name,
                "config_ids": list(self._config_ids),
                "rechecking": self._rechecking
            }

    # ---- 复测协调 ----

    def set_rechecking(self):
        with self._lock:
            self._rechecking = True
            self._pause_recheck = False
            self._recheck_stop_requested = False

    def clear_rechecking(self):
        with self._lock:
            self._rechecking = False
            self._pause_recheck = False
            self._recheck_stop_requested = False

    def stop_recheck(self):
        with self._lock:
            self._recheck_stop_requested = True

    def should_stop_recheck(self) -> bool:
        with self._lock:
            return self._recheck_stop_requested or self._pause_recheck

    def should_pause_recheck(self) -> bool:
        with self._lock:
            return self._pause_recheck


task_runner = TaskRunnerStatus()
