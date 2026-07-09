<template>
  <div class="page-container">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">
        <span class="material-symbols-outlined">arrow_back</span>
      </button>
      <h1 class="page-title">通知</h1>
      <div class="header-right">
        <div class="filter-counter-top">
          <span>{{ store.total }}</span> 条
        </div>
      </div>
    </div>

    <div class="header-spacer"></div>

    <div class="list-wrapper">
      <div v-if="loading" class="skeleton-list">
        <div v-for="i in 5" :key="i" class="skeleton-card">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-sub"></div>
        </div>
      </div>

      <template v-else>
        <div
          v-for="msg in store.messages"
          :key="msg.id"
          class="notif-card"
          :class="{ unread: !msg.read }"
          @click="handleClick(msg)"
        >
          <div class="card-top-row">
            <div class="card-left">
              <span class="notif-icon" :class="'icon--' + msg.type">
                <span class="material-symbols-outlined">{{ iconMap[msg.type] || 'info' }}</span>
              </span>
              <div class="card-body">
                <div class="card-title" :class="{ 'title-unread': !msg.read }">{{ msg.title }}</div>
                <div class="card-time">{{ formatTime(msg.createdAt) }}</div>
              </div>
            </div>
            <div class="card-actions" @click.stop>
              <button class="action-sm delete" @click="handleDelete(msg)" title="删除">
                <span class="material-symbols-outlined">delete</span>
              </button>
            </div>
          </div>
          <div v-if="msg.content" class="card-content">{{ msg.content }}</div>
          <div v-if="msg.source" class="card-source">{{ msg.source }}</div>
        </div>

        <div v-if="store.messages.length === 0 && !loading" class="empty-state">
          <p>暂无通知</p>
        </div>

        <div v-if="store.currentPage < store.totalPages" class="load-more-wrap">
          <button
            class="load-more-btn"
            :class="{ loading: loadingMore }"
            :disabled="loadingMore"
            @click="loadMore"
          >
            <span v-if="loadingMore" class="material-symbols-outlined spinner-icon spinning">sync</span>
            加载更多（剩余 {{ store.total - store.messages.length }} 条）
          </button>
        </div>
        <div v-if="store.messages.length >= store.total && store.total > 0" class="all-loaded-hint">
          已加载全部 {{ store.total }} 条
        </div>
      </template>
    </div>

    <!-- 底部操作栏 -->
    <Transition name="batch-bar">
      <div v-if="store.total > 0" class="bottom-actions">
        <button class="bottom-action-btn" @click="handleMarkAllRead">
          <span class="material-symbols-outlined">checklist</span>
          <span>全部已读</span>
        </button>
        <div class="bottom-action-divider"></div>
        <button class="bottom-action-btn delete-color" @click="handleDeleteAll">
          <span class="material-symbols-outlined">delete_sweep</span>
          <span>全部删除</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useMessagesStore } from '@/stores/messages'
import { toast } from '@/components/Toast'

const store = useMessagesStore()
const loading = ref(false)
const loadingMore = ref(false)

const iconMap = {
  success: 'check_circle',
  warning: 'warning',
  error: 'error',
  info: 'info',
}

const formatTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const handleClick = async (msg) => {
  if (!msg.read) {
    await store.markRead(msg.id)
    toast.success('已标为已读')
  }
}

const loadMore = async () => {
  loadingMore.value = true
  try {
    const nextPage = store.currentPage + 1
    await store.fetchMessages(nextPage)
  } catch {
    // 错误由拦截器处理
  } finally {
    loadingMore.value = false
  }
}

const handleMarkAllRead = async () => {
  await store.markAllRead()
  toast.success('已全部已读')
}

const handleDelete = async (msg) => {
  await store.deleteMessage(msg.id)
  toast.success('已删除')
}

const handleDeleteAll = async () => {
  const count = store.total
  if (!confirm(`确定要删除全部 ${count} 条消息吗？\n\n此操作不可恢复。`)) return
  await store.deleteAllMessages()
  toast.success('已删除全部消息')
}

onMounted(() => {
  store.fetchMessages()
})
</script>

<style scoped>
/* 页面顶部 — 与 OrphanHostsPage 一致 */
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
@media (min-width: 1024px) {
  .page-header { max-width: 1100px; }
}
@media (min-width: 1440px) {
  .page-header { max-width: 1400px; }
}

.page-title {
  flex: 1;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.back-btn {
  background: var(--bg-neutral);
  border: none;
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 50%;
  color: var(--text-primary);
  flex-shrink: 0;
  transition: all 0.2s ease;
}
.back-btn:active { background: var(--bg-neutral); transform: scale(0.9); }
.back-btn .material-symbols-outlined {
  font-size: 18px !important;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.filter-counter-top {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.filter-counter-top span {
  color: var(--color-blue);
  font-weight: 700;
}

/* 列表 — 与 OrphanHostsPage 一致的 grid 布局 */
.list-wrapper {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  width: 100%;
  max-width: var(--max-content);
  padding-bottom: 80px;
}
@media (min-width: 768px) {
  .list-wrapper { max-width: 720px; }
}
@media (min-width: 1024px) {
  .list-wrapper { max-width: 1100px; }
}
@media (min-width: 1440px) {
  .list-wrapper { max-width: 1400px; }
}

/* 通知卡片 — 风格与 hosts-grid-card 一致 */
.notif-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 16px;
  box-shadow: var(--shadow-md);
  border: 1px solid rgba(0, 0, 0, 0.01);
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.notif-card.unread {
  background: #f0f7ff;
  border-color: rgba(0, 122, 255, 0.25);
}

/* 未读标题加粗 */
.title-unread {
  font-weight: 700 !important;
}

.card-top-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.card-left {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.notif-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.notif-icon .material-symbols-outlined {
  font-size: 18px !important;
}
.icon--success { background: #e8f5e9; color: var(--color-green); }
.icon--warning { background: #fff3e0; color: var(--color-orange); }
.icon--error { background: #fdecea; color: var(--color-red); }
.icon--info { background: #e3f2fd; color: var(--color-blue); }

.card-body {
  flex: 1;
  min-width: 0;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}
.card-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 3px;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.action-sm {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: var(--bg-neutral);
  cursor: pointer;
  color: var(--text-muted);
  transition: all 0.15s;
}
.action-sm:active { transform: scale(0.9); }
.action-sm .material-symbols-outlined { font-size: 16px; }

.action-sm.delete {
  background: #fdecea;
  color: #e5484d;
}
.action-sm.delete:active {
  transform: scale(0.9);
  background: #f5d6d3;
}

.card-content {
  font-size: 13px;
  color: var(--text-secondary);
  padding-top: 8px;
  border-top: 1px solid var(--bg-neutral);
  line-height: 1.4;
}

.card-source {
  font-size: 11px;
  color: var(--text-muted);
}

/* 加载更多 — 与 OrphanHostsPage 一致 */
.load-more-wrap {
  grid-column: 1 / -1;
  text-align: center;
  padding: 16px 0;
}
.load-more-btn {
  background: var(--bg-neutral);
  color: var(--color-blue);
  border: none;
  padding: 10px 24px;
  border-radius: var(--radius-input);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.load-more-btn:active { transform: scale(0.96); background: #e8e8ed; }
.load-more-btn:disabled { cursor: not-allowed; opacity: 0.7; }
.spinner-icon { font-size: 16px !important; vertical-align: middle; margin-right: 4px; }

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.spinning { animation: spin 1s linear infinite; }

.all-loaded-hint {
  grid-column: 1 / -1;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 0;
}

/* 底部操作栏 — 与 OrphanHostsPage 的 batch-tabbar 一致 */
.bottom-actions {
  position: fixed;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  width: auto;
  min-width: 240px;
  height: 52px;
  padding: 0 8px;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(40px) saturate(180%);
  border-radius: 20px;
  box-shadow: var(--shadow-tabbar);
  border: 1px solid rgba(0, 0, 0, 0.02);
  display: flex;
  justify-content: space-around;
  align-items: center;
  z-index: 99;
  margin-bottom: env(safe-area-inset-bottom);
}
.bottom-action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  background: none;
  border: none;
  padding: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-blue);
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  font-family: var(--font-sans);
}
.bottom-action-btn:active {
  transform: scale(0.92);
}
.bottom-action-btn.delete-color {
  color: var(--color-red);
}
.bottom-action-btn .material-symbols-outlined {
  font-size: 22px !important;
}
.bottom-action-divider {
  width: 1px;
  height: 24px;
  background: rgba(0, 0, 0, 0.06);
}

.batch-bar-enter-active,
.batch-bar-leave-active {
  transition: all 0.3s cubic-bezier(0.25, 1, 0.5, 1);
}
.batch-bar-enter-from,
.batch-bar-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(20px);
}
</style>
