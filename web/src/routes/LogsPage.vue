<template>
  <div class="page-container">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">
        <span class="material-symbols-outlined">chevron_left</span>
      </button>
      <h1 class="page-title">后台日志</h1>
      <button class="refresh-btn" @click="refreshLogs" :class="{ fetching: refreshing }">
        <span class="material-symbols-outlined" :class="{ spin: refreshing }">refresh</span>
      </button>
    </div>

    <div class="header-spacer"></div>

    <div class="log-viewer">
      <div v-if="!initialized" class="log-empty">加载中...</div>
      <div v-else-if="logs.length === 0" class="log-empty">暂无日志</div>
      <div
        v-else
        v-for="(parsed, i) in parsedLogs"
        :key="i"
        class="log-line"
        :class="getLogLevelClass(parsed.display)"
      >
        <span class="log-time">{{ parsed.time }}</span>
        <span class="log-text">{{ parsed.display }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import request from '@/api'

const logs = ref([])
const refreshing = ref(false)
const initialized = ref(false)

let pollTimer = null

const parseLogLine = (line) => {
  const match = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[\w+\]\s+\[([^\]]+)\]\s+(.*)$/)
  if (match) {
    return { time: match[1], display: `[${match[2]}] ${match[3]}` }
  }
  const fallback = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(.*)$/)
  if (fallback) return { time: fallback[1], display: fallback[2] }
  return { time: '', display: line }
}

const parsedLogs = computed(() =>
  logs.value.map((line) => parseLogLine(line)).reverse()
)

const fetchLogs = async () => {
  try {
    const res = await request.get('/logs', { params: { lines: 500 } })
    logs.value = res.logs || []
    initialized.value = true
  } catch {
    /* 静默 */
  }
}

const refreshLogs = async () => {
  refreshing.value = true
  logs.value = []
  initialized.value = false
  await fetchLogs()
  refreshing.value = false
}

const getLogLevelClass = (display) => {
  if (display.includes('[ERROR]') || display.includes('[EXCEPTION]') || display.includes('[CRITICAL]'))
    return 'log-error'
  if (display.includes('[WARNING]')) return 'log-warning'
  return ''
}

onMounted(() => {
  fetchLogs()
  pollTimer = setInterval(fetchLogs, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.page-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  background: rgba(245, 245, 247, 0.92);
  backdrop-filter: blur(20px);
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100vw;
}
@media (min-width: 768px) {
  .page-header {
    max-width: 720px;
    margin-left: auto;
    margin-right: auto;
  }
}

.page-title {
  flex: 1;
  text-align: center;
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}

.back-btn {
  background: #e5e5ea;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.back-btn .material-symbols-outlined {
  font-size: 20px !important;
  color: var(--text-primary);
}
.back-btn:active {
  transform: scale(0.9);
}

.refresh-btn {
  background: #e5e5ea;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.refresh-btn .material-symbols-outlined {
  font-size: 20px !important;
  color: var(--text-muted);
}
.refresh-btn:active {
  transform: scale(0.9);
}
.refresh-btn.fetching {
  opacity: 0.5;
  pointer-events: none;
}

.header-spacer {
  height: 56px;
  flex-shrink: 0;
}

.log-viewer {
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 720px;
}

.log-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 40px 0;
}

.log-line {
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 11px;
  line-height: 1.6;
  display: flex;
  flex-direction: column;
}

.log-time {
  color: var(--text-muted);
  flex-shrink: 0;
}

.log-text {
  color: var(--text-primary);
  word-break: break-all;
}

.log-error .log-text {
  color: var(--color-red);
}

.log-warning .log-text {
  color: var(--color-orange);
}

.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
