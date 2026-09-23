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

    def is_rechecking(self) -> bool:
        with self._lock:
            return self._rechecking

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
            
    def clear_rechecking(self):
        with self._lock:
            self._rechecking = False
            self._pause_recheck = False

    def should_pause_recheck(self) -> bool:
        with self._lock:
            return self._pause_recheck


class SubscriptionRunnerStatus:
    """
    订阅拉取状态管理（波次并发模型）。

    每个订阅有独立生命周期状态：
      queued    排队中（尚未开始拉取）
      fetching  执行中（HTTP 拉取/入库进行中）
      done      已完成
      failed    失败（拉取或入库抛异常）
      stopped   已终止（被单个 stop 提前取消，或随 stop-all 取消）
      skipped   已跳过（无 URL 的纯推送型订阅）

    并发规则：同一波内所有 queued 订阅一次性并发拉取，
    运行中追加的订阅进入下一波。HTTP 并发由共享连接池（limit=concurrency 设置）控制。
    """

    STATUS_QUEUED = "queued"
    STATUS_FETCHING = "fetching"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_STOPPED = "stopped"
    STATUS_SKIPPED = "skipped"

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._should_stop = False
        # sub_id -> {"status": str, "name": str, "message": str}
        self._sub_states = {}
        # 待启动订阅（运行中追加的进入下一波，展示上直接算"拉取中"）
        self._pending_ids = []
        self._total = 0

    # ---- 生命周期 ----

    def start(self, sub_ids: list = None):
        """启动一轮拉取（首波 = sub_ids，展示层只有 拉取中/已停止 两态）"""
        with self._lock:
            self._running = True
            self._should_stop = False
            self._sub_states = {}
            self._pending_ids = []
            for sid in (sub_ids or []):
                self._sub_states[sid] = {
                    "status": self.STATUS_FETCHING, "name": "", "message": ""
                }
                self._pending_ids.append(sid)
            self._total = len(self._sub_states)

    def append(self, sub_id: int, name: str = ""):
        """运行中追加订阅：立即标记为"拉取中"（下一波启动，连接池全局限流）"""
        with self._lock:
            if not self._running:
                return False
            state = self._sub_states.get(sub_id)
            if state and state["status"] not in (
                self.STATUS_DONE, self.STATUS_FAILED, self.STATUS_STOPPED, self.STATUS_SKIPPED
            ):
                return False  # 已在本轮中
            self._sub_states[sub_id] = {
                "status": self.STATUS_FETCHING, "name": name, "message": ""
            }
            self._pending_ids.append(sub_id)
            self._total = len(self._sub_states)
            return True

    def stop(self):
        """停止整轮拉取：所有未结束的订阅标记 stopped（处理循环逐请求检查后丢弃结果）"""
        with self._lock:
            self._should_stop = True
            self._pending_ids = []
            for state in self._sub_states.values():
                if state["status"] in (self.STATUS_QUEUED, self.STATUS_FETCHING):
                    state["status"] = self.STATUS_STOPPED
                    state["message"] = "整轮已终止"

    def cancel(self, sub_id: int) -> str:
        """单个订阅提前终止。
        返回动作："dequeue"（已启动但尚未开拉，直接标记 stopped）、
        "cancel"（处理中，已标记 stopped，处理循环逐请求检查后丢弃结果）、
        "none"（不在本轮或已结束）。"""
        with self._lock:
            state = self._sub_states.get(sub_id)
            if not state or state["status"] in (
                self.STATUS_DONE, self.STATUS_FAILED, self.STATUS_STOPPED, self.STATUS_SKIPPED
            ):
                return "none"
            state["status"] = self.STATUS_STOPPED
            state["message"] = "已手动终止"
            if sub_id in self._pending_ids:
                self._pending_ids.remove(sub_id)
                return "dequeue"
            return "cancel"

    # ---- 状态流转（由执行器调用） ----

    def set_name(self, sub_id: int, name: str):
        with self._lock:
            if sub_id in self._sub_states:
                self._sub_states[sub_id]["name"] = name

    def set_fetching(self, sub_id: int):
        with self._lock:
            if sub_id in self._sub_states:
                self._sub_states[sub_id]["status"] = self.STATUS_FETCHING

    def set_result(self, sub_id: int, status: str, message: str = ""):
        """写入终态；终止态（stopped）不可被其他状态覆盖，但允许更新消息（如补充已入库条数）"""
        with self._lock:
            state = self._sub_states.get(sub_id)
            if not state:
                return
            if state["status"] == self.STATUS_STOPPED and status != self.STATUS_STOPPED:
                return
            state["status"] = status
            state["message"] = message

    # ---- 查询 ----

    def should_stop(self) -> bool:
        with self._lock:
            return self._should_stop

    def is_stopped(self, sub_id: int) -> bool:
        """单个订阅是否已被终止（供处理循环逐请求协作检查，
        命中后立即停止后续 host 请求并丢弃结果）"""
        with self._lock:
            state = self._sub_states.get(sub_id)
            return bool(state and state["status"] == self.STATUS_STOPPED)

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def is_idle(self) -> bool:
        with self._lock:
            return not self._running

    def take_pending(self) -> list:
        """取出一批待启动的订阅（下一波并发执行），跳过已被终止的"""
        with self._lock:
            if self._should_stop:
                self._pending_ids = []
                return []
            batch = []
            remaining = []
            for sid in self._pending_ids:
                state = self._sub_states.get(sid)
                if state and state["status"] == self.STATUS_FETCHING:
                    batch.append(sid)
                else:
                    remaining.append(sid)
            self._pending_ids = remaining
            return batch

    def finish(self):
        """整轮结束，清理状态（progress 仍可读到最终状态摘要）"""
        with self._lock:
            self._running = False
            self._should_stop = False
            self._pending_ids = []
            self._last_finished_states = {
                sid: dict(state) for sid, state in self._sub_states.items()
            }
            self._sub_states = {}
            self._total = 0

    def get_progress(self) -> dict:
        with self._lock:
            states = dict(self._sub_states)
            running = self._running
            total = self._total
            if not running:
                states = dict(getattr(self, "_last_finished_states", {}) or {})
            fetching_ids = [
                sid for sid, state in states.items()
                if state["status"] in (self.STATUS_QUEUED, self.STATUS_FETCHING)
            ]
        return {
            "running": running,
            "total": total,
            "fetchingIds": fetching_ids,
            "subs": [
                {
                    "id": sid,
                    "name": state["name"],
                    "status": state["status"],
                    "message": state["message"],
                }
                for sid, state in states.items()
            ],
        }


# 扫描队列状态
task_runner = TaskRunnerStatus()
# 订阅拉取状态（波次并发）
sub_runner = SubscriptionRunnerStatus()
