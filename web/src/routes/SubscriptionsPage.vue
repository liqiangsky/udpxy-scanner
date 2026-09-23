<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">订阅</h1>
      <div class="header-actions">
        <button
          class="fetch-all-btn"
          :class="{ fetching: fetchingAll }"
          @click="handleFetchAll"
          :title="fetchingAll ? '停止全部拉取' : '一键拉取所有订阅'"
        >
          <span class="material-symbols-outlined icon-g-btn">
            {{ fetchingAll ? 'stop' : 'cloud_download' }}
          </span>
        </button>
        <button class="action-btn primary-btn" @click="startAddSub">
          <span class="material-symbols-outlined icon-g-btn">add</span>
        </button>
      </div>
    </div>

    <div class="header-spacer"></div>

    <div class="config-list">
      <div v-if="!loaded" class="skeleton-list">
        <div v-for="i in 3" :key="i" class="skeleton-card">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-sub"></div>
          <div class="skeleton-line skeleton-sub narrow"></div>
        </div>
      </div>
      <TransitionGroup v-else name="list-fade">
        <div
          v-for="sub in subscriptions"
          :key="sub.id"
          class="config-card"
          :class="{
            'status-fetching': fetchingIds.includes(sub.id),
            'status-disabled': !sub.enabled,
          }"
        >
          <div class="card-top">
            <div class="config-identity">
              <h3 class="config-name">{{ sub.name }}</h3>
              <div class="identity-sub">
                <span class="uid-tag">{{ sub.uid }}</span>
                <span
                  class="status-dot-badge"
                  :class="
                    fetchingIds.includes(sub.id)
                      ? 'fetching'
                      : sub.enabled
                        ? 'idle'
                        : 'disabled'
                  "
                >
                  {{
                    fetchingIds.includes(sub.id)
                      ? '拉取中...'
                      : sub.enabled
                        ? '已停止'
                        : '已禁用'
                  }}
                </span>
              </div>
            </div>

            <div class="card-top-actions">
              <button
                class="run-toggle-btn"
                :class="fetchingIds.includes(sub.id) ? 'fetching' : 'idle'"
                @click="toggleFetch(sub)"
                :title="fetchingIds.includes(sub.id) ? '停止拉取' : '立即拉取'"
              >
                <span
                  v-if="fetchingIds.includes(sub.id)"
                  class="material-symbols-outlined icon-g-toggle">stop</span
                >
                <span v-else class="material-symbols-outlined icon-g-toggle">cloud_download</span>
              </button>
            </div>
          </div>

          <div class="card-grid">
            <div class="grid-item">
              <span class="lbl">订阅类型</span>
              <span class="txt">{{ sub.type === 'text' ? '文本' : 'API' }}</span>
            </div>
            <div class="grid-item">
              <span class="lbl">订阅 URL</span>
              <span class="txt mono truncate">{{ sub.url }}</span>
            </div>
            <div class="grid-item">
              <span class="lbl">定时拉取</span>
              <span class="txt">{{ sub.fetchCron || '未设置' }}</span>
            </div>
            <div class="grid-item">
              <span class="lbl">上次拉取</span>
              <span class="txt">{{
                sub.lastFetchAt ? formatTime(sub.lastFetchAt) : '未拉取'
              }}</span>
            </div>
          </div>

          <div class="card-actions" v-show="!fetchingIds.includes(sub.id)">
            <button
              class="text-btn toggle-enable"
              :class="{ disabled: !sub.enabled }"
              @click="handleToggleEnabled(sub)"
            >
              <span class="material-symbols-outlined icon-g-btn">{{
                sub.enabled ? 'toggle_on' : 'toggle_off'
              }}</span>
              {{ sub.enabled ? '禁用' : '启用' }}
            </button>
            <button class="text-btn edit" @click="startEditSub(sub)">
              <span class="material-symbols-outlined icon-g-btn">edit</span> 编辑
            </button>
            <button class="text-btn delete" @click="handleDeleteSub(sub)">
              <span class="material-symbols-outlined icon-g-btn">delete</span> 删除
            </button>
          </div>
        </div>
      </TransitionGroup>

      <div v-if="loaded && subscriptions.length === 0" class="empty-state">
        暂无订阅，点击右上角添加
      </div>
    </div>

    <!-- 添加/编辑 弹窗 -->
    <div class="form-overlay" v-if="formVisible" @click="cancelForm">
      <div class="form-drawer" @click.stop>
        <div class="drawer-header">
          <h2>{{ editingId ? '编辑订阅' : '添加订阅' }}</h2>
          <button class="close-x-btn" @click="cancelForm">×</button>
        </div>
        <div class="drawer-form">
          <div class="form-item">
            <label>订阅名称</label>
            <input v-model="formData.name" type="text" placeholder="例：鹰图平台" />
          </div>
          <div class="form-item">
            <label>订阅 ID（数据源标识）</label>
            <input v-model="formData.uid" type="text" placeholder="例：github，多个订阅可共用同一 ID" />
          </div>
          <div class="form-item">
            <label>订阅类型</label>
            <div class="type-selector">
              <select v-model="formData.type">
                <option value="api">API（JSON）</option>
                <option value="text">文本（m3u/txt）</option>
              </select>
              <button
                v-if="formData.type === 'api'"
                class="view-json-btn"
                @click="openJsonPreview()"
                title="查看 JSON 格式示例"
              >
                <span class="material-symbols-outlined icon-g-btn">visibility</span>
                查看
              </button>
            </div>
          </div>
          <div class="form-item">
            <label>订阅 URL</label>
            <input
              v-model="formData.url"
              type="text"
              placeholder="https://example.com/api/hunt?key=xxx"
            />
          </div>
          <div class="form-item">
            <label>定时拉取 (Cron)，留空不执行</label>
            <input v-model="formData.fetchCron" type="text" placeholder="留空不执行" />
          </div>
          <div class="drawer-actions">
            <button type="button" class="drawer-btn drawer-btn-primary" @click="handleSaveSub">
              {{ editingId ? '保存' : '添加' }}
            </button>
            <button type="button" class="drawer-btn drawer-btn-cancel" @click="cancelForm">
              取消
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- JSON 预览弹窗 -->
    <div class="form-overlay" v-if="jsonPreview.visible" @click="jsonPreview.visible = false">
      <div class="form-drawer json-preview-drawer" @click.stop>
        <div class="drawer-header">
          <h2>返回示例</h2>
          <button class="close-x-btn" @click="jsonPreview.visible = false">×</button>
        </div>
        <pre class="json-preview-body">{{ jsonPreview.formatted }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { toast } from '@/components/Toast'
import { formatTime } from '@/shared'
import request from '@/api'
import { useSubscriptionStore } from '@/stores/subscription'
import { useNotificationListener } from '@/composables/useNotifications'

const subscriptionStore = useSubscriptionStore()

const subscriptions = computed(() => subscriptionStore.subscriptions)
const loaded = computed(() => subscriptionStore.loaded)
const progress = computed(() => subscriptionStore.progress)

const fetchingIds = computed(() => (progress.value.running ? progress.value.fetchingIds : []))
const activeIds = computed(() => [...fetchingIds.value])
const fetchingAll = computed(() => progress.value.running)

const formVisible = ref(false)
const editingId = ref(null)
const formData = reactive({ name: '', uid: '', url: '', type: 'api', fetchCron: '' })

// JSON 预览
const jsonPreview = reactive({ visible: false, formatted: '' })

const openJsonPreview = () => {
  jsonPreview.visible = true
  jsonPreview.formatted = JSON.stringify(
    {
      uid: 'hunter',
      hosts: [
        { host: '1.2.3.4:8080', geoRegion: '北京', geoOperator: '电信' },
        { host: '5.6.7.8:9000', geoRegion: '上海', geoOperator: '联通' },
      ],
    },
    null,
    2
  )
}

const loadSubscriptions = async () => {
  try {
    await subscriptionStore.fetch()
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

// 拉取完成的通知会更新 lastFetchAt（订阅配置变了），需要刷新列表
const handleSubscriptionNotification = () => {
  loadSubscriptions()
}

useNotificationListener('SUBSCRIPTION', handleSubscriptionNotification)

const startAddSub = () => {
  editingId.value = null
  formData.name = ''
  formData.uid = ''
  formData.url = ''
  formData.type = 'api'
  formData.fetchCron = ''
  formVisible.value = true
}

const startEditSub = (sub) => {
  editingId.value = sub.id
  // 回填时先 trim，避免历史数据里的首尾空格残留到表单
  formData.name = (sub.name || '').trim()
  formData.uid = (sub.uid || '').trim()
  formData.url = (sub.url || '').trim()
  formData.type = sub.type || 'api'
  formData.fetchCron = (sub.fetchCron || '').trim()
  formVisible.value = true
}

const cancelForm = () => {
  formVisible.value = false
  editingId.value = null
}

const handleSaveSub = async () => {
  // 入库前统一 trim，避免首尾空格写进配置
  formData.name = (formData.name || '').trim()
  formData.uid = (formData.uid || '').trim()
  formData.url = (formData.url || '').trim()
  formData.fetchCron = (formData.fetchCron || '').trim()

  if (!formData.name || !formData.uid || !formData.url) {
    toast.warning('请填写完整')
    return
  }
  try {
    if (editingId.value) {
      await request.put(`/subscriptions/${editingId.value}`, {
        name: formData.name,
        uid: formData.uid,
        url: formData.url,
        type: formData.type,
        fetchCron: formData.fetchCron,
      })
      toast.success('已更新')
    } else {
      await request.post('/subscriptions', {
        name: formData.name,
        uid: formData.uid,
        url: formData.url,
        type: formData.type,
        fetchCron: formData.fetchCron,
      })
      toast.success('已添加')
    }
    formVisible.value = false
    editingId.value = null
    await loadSubscriptions()
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

const handleDeleteSub = async (sub) => {
  if (activeIds.value.includes(sub.id)) {
    toast.info('订阅拉取中，无法删除')
    return
  }
  if (!confirm(`确定删除订阅「${sub.name}」？将同时清除该订阅的缓存。`)) return
  try {
    await request.delete(`/subscriptions/${sub.id}`)
    toast.success('已删除')
    await loadSubscriptions()
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

const handleToggleEnabled = async (sub) => {
  if (activeIds.value.includes(sub.id)) {
    toast.info('订阅拉取中，无法停用')
    return
  }
  const wasEnabled = sub.enabled
  try {
    await request.put(`/subscriptions/${sub.id}`, {
      name: sub.name?.trim(),
      uid: sub.uid?.trim(),
      url: sub.url?.trim(),
      type: sub.type || 'api',
      fetchCron: (sub.fetchCron || '').trim(),
      enabled: !wasEnabled,
    })
    toast.success(wasEnabled ? '已停用' : '已启用')
    await loadSubscriptions()
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

const handleFetchAll = async () => {
  if (fetchingAll.value) {
    // 停止全部
    try {
      await request.post('/subscriptions/stop-all')
      toast.info('正在停止全部拉取...')
    } catch {
      /* 错误由拦截器统一提示 */
    }
  } else {
    // 启动全部
    try {
      await request.post('/subscriptions/fetch-all')
      toast.success('批量拉取已启动')
      subscriptionStore.startPolling()
    } catch {
      /* 错误由拦截器统一提示 */
    }
  }
}

const toggleFetch = async (sub) => {
  if (!sub.enabled) {
    toast.info('订阅已禁用，无法拉取')
    return
  }
  const isActive = activeIds.value.includes(sub.id)

  try {
    if (isActive) {
      await request.post(`/subscriptions/${sub.id}/stop`)
      toast.info('已终止拉取，进行中的请求收尾后丢弃结果')
    } else {
      await request.post(`/subscriptions/${sub.id}/fetch`)
      subscriptionStore.addToQueue(sub.id)
      toast.success(subscriptionStore.progress.running ? '已加入拉取' : '拉取已启动')
      subscriptionStore.startPolling()
    }
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

onMounted(async () => {
  await subscriptionStore.startPolling()
  await loadSubscriptions()
})

onUnmounted(() => {
  subscriptionStore.stopPolling()
  document.body.style.overflow = ''
})

// 弹窗打开时锁定 body 滚动，关闭时恢复（两个弹窗任一打开即锁）
watch(
  () => formVisible.value || jsonPreview.visible,
  (anyOpen) => {
    document.body.style.overflow = anyOpen ? 'hidden' : ''
  }
)
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
  min-height: 56px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 100vw;
}
@media (min-width: 768px) {
  .page-header {
    max-width: 720px;
    left: 50%;
    transform: translateX(-50%);
  }
}
@media (min-width: 1024px) {
  .page-header {
    max-width: 1100px;
  }
}
@media (min-width: 1440px) {
  .page-header {
    max-width: 1400px;
  }
}

/* ===== 列表 Grid ===== */
.config-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  width: 100%;
  max-width: var(--max-content);
  padding-bottom: 70px;
}
@media (min-width: 768px) {
  .config-list {
    max-width: 720px;
  }
}
@media (min-width: 1024px) {
  .config-list {
    max-width: 1100px;
  }
}
@media (min-width: 1440px) {
  .config-list {
    max-width: 1400px;
  }
}

/* ===== 卡片 ===== */
.config-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 20px;
  box-shadow: var(--shadow-md);
  border: 1px solid rgba(0, 0, 0, 0.01);
  display: flex;
  flex-direction: column;
  transition: all 0.3s var(--ease-spring);
}
.config-card.status-fetching {
  border-color: rgba(52, 199, 89, 0.3);
  box-shadow: 0 4px 24px rgba(52, 199, 89, 0.08);
  position: relative;
  overflow: hidden;
}
.config-card.status-fetching::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, #34c759, transparent);
}
.config-card.status-disabled {
  opacity: 0.5;
}

/* ===== 卡片顶部 ===== */
.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.config-identity {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 75%;
  min-width: 0;
}
.config-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.identity-sub {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.uid-tag {
  font-size: 10px;
  font-weight: 600;
  color: #8e8e93;
  background: var(--bg-neutral);
  padding: 2px 8px;
  border-radius: 10px;
  font-family: var(--font-mono);
  letter-spacing: -0.2px;
}

/* ===== 状态徽标（对齐扫描页） ===== */
.status-dot-badge {
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 10px;
  width: max-content;
}
.status-dot-badge::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot-badge.idle {
  color: var(--text-muted);
  background: var(--bg-neutral);
}
.status-dot-badge.idle::before {
  background: var(--text-muted);
}
.status-dot-badge.fetching {
  color: #fff;
  background: #34c759;
}
.status-dot-badge.fetching::before {
  background: #fff;
  animation: pulse 1.5s infinite;
}
.status-dot-badge.disabled {
  color: #fff;
  background: #8e8e93;
}
.status-dot-badge.disabled::before {
  background: #fff;
  opacity: 0.7;
}

/* ===== 启停按钮（对齐扫描页） ===== */
.card-top-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.run-toggle-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}
.run-toggle-btn.idle {
  background: var(--bg-status-good);
  color: var(--color-green);
}
.run-toggle-btn.fetching {
  background: var(--bg-status-error);
  color: var(--color-red);
}
.run-toggle-btn:active {
  transform: scale(0.9);
}
.icon-g-toggle {
  font-size: 20px !important;
  font-variation-settings:
    'FILL' 0,
    'wght' 600,
    'GRAD' 0,
    'opsz' 24;
}

/* ===== 信息网格 ===== */
.card-grid {
  margin-top: 14px;
  border-top: 1px solid var(--bg-neutral);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.grid-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.lbl {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
  font-weight: 500;
}
.txt {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.txt.mono {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: -0.2px;
}
.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===== 操作按钮 ===== */
.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed var(--bg-neutral);
}
.text-btn {
  background: none;
  border: none;
  outline: none;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  -webkit-tap-highlight-color: transparent;
  transition: all 0.2s ease;
}
.text-btn:active {
  transform: scale(0.94);
}
.text-btn.edit {
  color: var(--color-blue);
}
.text-btn.delete {
  color: var(--color-red);
}
.text-btn.toggle-enable {
  color: var(--color-green);
}
.text-btn.toggle-enable.disabled {
  color: var(--color-orange);
}

/* ===== 头部按钮 ===== */
.action-btn {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  font-weight: 600;
  -webkit-tap-highlight-color: transparent;
}
.primary-btn {
  background: var(--color-blue);
  color: #fff;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.icon-g-btn {
  font-size: 18px !important;
}

/* 页头操作区 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.primary-btn:active {
  transform: scale(0.9);
  background: #0066d6;
}

/* 一键拉取按钮 */
.fetch-all-btn {
  background: var(--color-green);
  color: #fff;
  border: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.fetch-all-btn.fetching {
  background: var(--color-red);
}
.fetch-all-btn:active {
  transform: scale(0.9);
}

/* ===== 空状态 ===== */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
  font-size: 14px;
}

@keyframes pulse {
  0% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.3);
    opacity: 0.5;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

/* ===== Drawer ===== */
.form-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(10px);
  z-index: 100;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
@media (min-width: 768px) {
  .form-overlay {
    align-items: center;
  }
}
.form-drawer {
  background: var(--bg-card);
  width: 100%;
  max-width: 420px;
  max-height: 90vh;
  border-top-left-radius: var(--radius-card);
  border-top-right-radius: var(--radius-card);
  display: flex;
  flex-direction: column;
  padding: 24px 24px calc(24px + env(safe-area-inset-bottom)) 24px;
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.1);
  animation: slide-up 0.35s var(--ease-spring);
  overflow: hidden;
}
@media (min-width: 768px) {
  .form-drawer {
    border-radius: var(--radius-card);
    max-height: 85vh;
  }
}
.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-shrink: 0;
}
.drawer-header h2 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}
.close-x-btn {
  background: var(--bg-neutral);
  border: none;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-size: 18px;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.drawer-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
}
.drawer-form input {
  appearance: none;
  -webkit-appearance: none;
  background: var(--bg-neutral);
  border: none;
  outline: none;
  padding: 12px;
  border-radius: var(--radius-input);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  width: 100%;
  box-sizing: border-box;
}
.drawer-form select {
  appearance: none;
  -webkit-appearance: none;
  background: var(--bg-neutral);
  border: none;
  outline: none;
  padding: 12px;
  border-radius: var(--radius-input);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  width: 100%;
  box-sizing: border-box;
  cursor: pointer;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='%238E8E93' d='M0 0h10L5 6z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 14px center;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-item label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.form-hint {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
.form-hint-code {
  font-family: var(--font-mono);
  background: var(--bg-neutral);
  padding: 4px 6px;
  border-radius: 4px;
  display: inline-block;
  margin-top: 4px;
  word-break: break-all;
}
.drawer-actions {
  display: flex;
  gap: 10px;
  margin-top: 6px;
  flex-shrink: 0;
}
.drawer-btn {
  flex: 1;
  padding: 12px;
  border: none;
  border-radius: var(--radius-input);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.drawer-btn:active {
  transform: scale(0.97);
}
.drawer-btn-primary {
  background: var(--color-blue);
  color: #fff;
}
.drawer-btn-cancel {
  background: var(--bg-neutral);
  color: var(--text-secondary);
}

@keyframes slide-up {
  from {
    transform: translateY(100%);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

/* ===== JSON 预览弹窗 ===== */
.json-preview-drawer {
  max-width: 480px;
}
.json-preview-body {
  max-height: none;
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: #1e1e1e;
  border-radius: var(--radius-input);
  padding: 14px 16px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

/* ===== 查看按钮 ===== */
.type-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}
.view-json-btn {
  background: none;
  border: none;
  outline: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-blue);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 6px 10px;
  border-radius: var(--radius-input);
  background: var(--bg-neutral);
  transition: all 0.15s ease;
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
  white-space: nowrap;
}
.view-json-btn:active {
  background: rgba(0, 122, 255, 0.12);
  transform: scale(0.94);
}

/* ===== Transition ===== */
.list-fade-enter-active,
.list-fade-leave-active {
  transition: all 0.3s ease;
}
.list-fade-enter-from,
.list-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
