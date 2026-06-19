<template>
  <div class="page-container">

    <div class="page-header">
      <button class="back-btn" @click="$router.back()">
        <span class="material-symbols-outlined">chevron_left</span>
      </button>
      <h1 class="page-title">后台日志</h1>
      <button class="refresh-btn" @click="refreshLogs">
        <span class="material-symbols-outlined" :class="{ spin: refreshing }">refresh</span>
      </button>
    </div>

    <div class="header-spacer"></div>

    <div class="log-page">
      <div class="log-filters">
        <div class="log-level-chips">
          <span
            v-for="lv in ['ALL', 'INFO', 'WARNING', 'ERROR']"
            :key="lv"
            class="log-level-chip"
            :class="{ active: logLevel === lv }"
            @click="logLevel = lv"
          >{{ lv === 'ALL' ? '全部' : lv }}</span>
          <span class="log-count">{{ filteredLogs.length }} / {{ logs.length }} 条</span>
        </div>

        <div class="log-module-chips" v-if="modules.length > 0">
          <span
            class="log-module-chip"
            :class="{ active: moduleFilter === '' }"
            @click="moduleFilter = ''"
          >全部模块</span>
          <span
            v-for="m in modules"
            :key="m"
            class="log-module-chip"
            :class="{ active: moduleFilter === m }"
            @click="moduleFilter = m"
          >{{ m }}</span>
        </div>

      </div>

      <div class="log-viewer" ref="logViewerRef">
        <div v-if="logs.length === 0 && !initialized" class="log-empty">
          <span class="material-symbols-outlined log-empty-icon">receipt_long</span>
          <p>正在加载日志...</p>
        </div>
        <div v-else-if="logs.length === 0" class="log-empty">
          <span class="material-symbols-outlined log-empty-icon">inbox</span>
          <p>暂无日志</p>
        </div>
        <div v-else-if="filteredLogs.length === 0" class="log-empty">
          <span class="material-symbols-outlined log-empty-icon">search_off</span>
          <p>无匹配日志</p>
        </div>
        <div v-else v-for="(line, i) in filteredLogs" :key="i" class="log-line" :class="getLogLevelClass(line)">
          <span class="log-time">{{ parseLogLine(line).time }}</span>
          <span class="log-text">{{ parseLogLine(line).display }}</span>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import request from '@/api'

const logs = ref([])
const logLevel = ref('ALL')
const moduleFilter = ref('')
const refreshing = ref(false)
const initialized = ref(false)
const logViewerRef = ref(null)

let pollTimer = null

const parseLogLine = (line) => {
  // 格式: 2026-06-17 12:34:56 [LEVEL] [模块名] 内容
  const match = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[\w+\]\s+\[([^\]]+)\]\s+(.*)$/)
  if (match) {
    return {
      time: match[1],
      module: match[2],
      content: match[3],
      display: `[${match[2]}] ${match[3]}`
    }
  }
  // 回退：只解析时间
  const fallback = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(.*)$/)
  if (fallback) return { time: fallback[1], module: '', content: fallback[2], display: fallback[2] }
  return { time: '', module: '', content: line, display: line }
}

const modules = computed(() => {
  const set = new Set()
  for (const line of logs.value) {
    const parsed = parseLogLine(line)
    if (parsed.module) set.add(parsed.module)
  }
  return [...set].sort()
})

const filteredLogs = computed(() => {
  let result = logs.value

  // 模块过滤
  if (moduleFilter.value) {
    result = result.filter(line => {
      const parsed = parseLogLine(line)
      return parsed.module === moduleFilter.value
    })
  }

  return result
})

const fetchLogs = async () => {
  try {
    const params = { lines: 500 }
    if (logLevel.value !== 'ALL') params.level = logLevel.value
    const res = await request.get('/logs', { params })
    const newLogs = res.logs || []

    if (!initialized.value) {
      logs.value = newLogs
      initialized.value = true
      // 首次加载滚动到底部
      setTimeout(() => {
        if (logViewerRef.value) {
          logViewerRef.value.scrollTop = logViewerRef.value.scrollHeight
        }
      }, 100)
    } else {
      // 增量追加新日志
      const lastLine = logs.value[logs.value.length - 1]
      const lastIdx = newLogs.indexOf(lastLine)
      if (lastIdx >= 0 && lastIdx < newLogs.length - 1) {
        const appended = newLogs.slice(lastIdx + 1)
        logs.value.push(...appended)
        // 用户在底部时自动滚动
        const el = logViewerRef.value
        if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
          el.scrollTop = el.scrollHeight
        }
      }
    }
  } catch {
    // 静默
  }
}

const refreshLogs = async () => {
  refreshing.value = true
  logs.value = []
  initialized.value = false
  await fetchLogs()
  refreshing.value = false
}

const getLogLevelClass = (line) => {
  if (line.includes('[ERROR]') || line.includes('[EXCEPTION]') || line.includes('[CRITICAL]')) return 'log-error'
  if (line.includes('[WARNING]')) return 'log-warning'
  return ''
}

watch(logLevel, () => {
  logs.value = []
  initialized.value = false
  fetchLogs()
})

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
  .page-header { max-width: 720px; margin-left: auto; margin-right: auto; }
}
@media (min-width: 1024px) {
  .page-header { max-width: 1100px; }
}
@media (min-width: 1440px) {
  .page-header { max-width: 1400px; }
}
.page-title {
  flex: 1;
  text-align: center;
}
.back-btn {
  background: var(--bg-neutral);
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
.back-btn:active { transform: scale(0.9); }
.header-spacer {
  height: 56px;
  flex-shrink: 0;
}

.refresh-btn {
  background: var(--bg-neutral);
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}
.refresh-btn .material-symbols-outlined {
  font-size: 20px !important;
  color: var(--text-muted);
}
.refresh-btn:active { transform: scale(0.9); }

.log-page {
  width: 100%;
  max-width: var(--max-content);
  padding-bottom: 90px;
}

@media (min-width: 768px) {
  .log-page { max-width: 720px; }
}
@media (min-width: 1024px) {
  .log-page { max-width: 1100px; }
}
@media (min-width: 1440px) {
  .log-page { max-width: 1400px; }
}

.log-filters {
  padding: 0 16px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.log-level-chips {
  display: flex;
  align-items: center;
  gap: 6px;
}
.log-level-chip {
  font-size: 12px;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 14px;
  background: var(--bg-neutral);
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  transition: all 0.15s ease;
}
.log-level-chip.active {
  background: rgba(0, 122, 255, 0.12);
  color: var(--color-blue);
}
.log-count {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
  white-space: nowrap;
}

.log-module-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.log-module-chip {
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 10px;
  background: rgba(0, 122, 255, 0.06);
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  transition: all 0.15s ease;
  border: 1px solid rgba(0, 0, 0, 0.06);
}
.log-module-chip.active {
  background: rgba(0, 122, 255, 0.12);
  color: var(--color-blue);
  border-color: rgba(0, 122, 255, 0.2);
}

.log-viewer {
  background: #1e1e1e;
  border-radius: var(--radius-card);
  margin: 0 16px;
  padding: 12px;
  height: calc(100vh - 160px);
  max-height: 600px;
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: 10.5px;
  line-height: 1.6;
  color: #d4d4d4;
  word-break: break-all;
}

@media (min-width: 768px) {
  .log-viewer { margin: 0; }
}
.log-viewer::-webkit-scrollbar { width: 4px; }
.log-viewer::-webkit-scrollbar-track { background: transparent; }
.log-viewer::-webkit-scrollbar-thumb { background: #555; border-radius: 2px; }

.log-line { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.log-line:last-child { border-bottom: none; }
.log-time {
  display: block;
  font-size: 10px;
  color: #666;
  margin-bottom: 2px;
}
.log-text { white-space: pre-wrap; }
.log-error .log-text { color: #f48771; }
.log-warning .log-text { color: #dcdcaa; }

.log-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: #888;
}
.log-empty-icon {
  font-size: 40px !important;
  margin-bottom: 12px;
  color: #555;
}
.log-empty p {
  margin: 0;
  font-size: 13px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.spin { animation: spin 1s linear infinite; }
</style>
