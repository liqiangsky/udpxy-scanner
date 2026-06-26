<template>
  <div class="sc-toast-container">
    <TransitionGroup name="toast-slide" tag="div" class="sc-toast-group">
      <div v-for="item in items" :key="item.id" class="sc-toast-item" :class="`type-${item.type}`">
        <span class="sc-toast-icon material-symbols-outlined">{{ icons[item.type] }}</span>
        <div class="sc-toast-content">{{ item.message }}</div>
        <button class="sc-toast-close" @click="remove(item.id)">
          <span class="material-symbols-outlined">close</span>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'

defineOptions({ name: 'ToastContainer' })

const items = ref([])
let idCounter = 0
const timers = new Set()

const icons = {
  success: 'check_circle',
  error: 'error',
  info: 'info',
  warning: 'warning',
}

const add = (message, type = 'info', duration = 3500) => {
  const id = idCounter++
  items.value.push({ id, message, type })

  if (duration > 0) {
    const timer = setTimeout(() => {
      timers.delete(timer)
      remove(id)
    }, duration)
    timers.add(timer)
  }
}

const remove = (id) => {
  items.value = items.value.filter((item) => item.id !== id)
}

// 组件卸载时清理所有残留 timer
onUnmounted(() => {
  for (const timer of timers) {
    clearTimeout(timer)
  }
  timers.clear()
})

defineExpose({ add })
</script>

<style scoped>
/* 底部居中定位：移动端拇指可达区域 */
.sc-toast-container {
  position: fixed;
  bottom: calc(80px + env(safe-area-inset-bottom));
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  pointer-events: none;
  width: calc(100% - 32px);
  max-width: var(--max-content);
}

.sc-toast-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Toast 卡片：深色毛玻璃风格 */
.sc-toast-item {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  border-radius: 16px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.12),
    0 2px 8px rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(20px);
  pointer-events: auto;
  box-sizing: border-box;
  transition: box-shadow 0.2s ease;
}

/* 核心内容区 */
.sc-toast-content {
  flex: 1;
  margin-left: 10px;
  margin-right: 8px;
  font-size: 13px;
  font-family: var(--font-sans);
  font-weight: 500;
  line-height: 1.4;
  word-break: break-all;
}

/* Material Symbols 图标 */
.sc-toast-icon {
  font-size: 20px !important;
  flex-shrink: 0;
}

/* 关闭按钮 */
.sc-toast-close {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}
.sc-toast-close:hover {
  background-color: rgba(255, 255, 255, 0.1);
}
.sc-toast-close .material-symbols-outlined {
  font-size: 18px !important;
}

/* 状态配色：深色背景 + 彩色图标 */
.type-success {
  background-color: rgba(16, 30, 24, 0.88);
  color: #e8f7f0;
}
.type-success .sc-toast-icon {
  color: var(--color-green);
}
.type-success .sc-toast-close {
  color: rgba(255, 255, 255, 0.4);
}

.type-error {
  background-color: rgba(30, 12, 18, 0.88);
  color: #ffe8eb;
}
.type-error .sc-toast-icon {
  color: var(--color-red);
}
.type-error .sc-toast-close {
  color: rgba(255, 255, 255, 0.4);
}

.type-info {
  background-color: rgba(12, 20, 36, 0.88);
  color: #e8f0ff;
}
.type-info .sc-toast-icon {
  color: var(--color-blue);
}
.type-info .sc-toast-close {
  color: rgba(255, 255, 255, 0.4);
}

.type-warning {
  background-color: rgba(30, 22, 8, 0.88);
  color: #fff3e0;
}
.type-warning .sc-toast-icon {
  color: var(--color-orange);
}
.type-warning .sc-toast-close {
  color: rgba(255, 255, 255, 0.4);
}

/* 动画：底部上浮 + 淡入淡出 */
.toast-slide-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}
.toast-slide-enter-to {
  opacity: 1;
  transform: translateY(0) scale(1);
}
.toast-slide-leave-from {
  opacity: 1;
  transform: translateY(0) scale(1);
}
.toast-slide-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
}
.toast-slide-move {
  transition: transform 0.3s var(--ease-spring);
}
.toast-slide-leave-active {
  position: absolute;
}
</style>
