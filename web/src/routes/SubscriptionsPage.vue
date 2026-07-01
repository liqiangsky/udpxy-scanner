<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">订阅</h1>
      <button class="action-btn primary-btn" @click="startAddSub">
        <span class="material-symbols-outlined icon-g-btn">add</span>
      </button>
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
          :class="{ 'status-disabled': !sub.enabled }"
        >
          <div class="card-top">
            <div class="config-identity">
              <h3 class="config-name">{{ sub.name }}</h3>
              <span class="uid-tag">{{ sub.uid }}</span>
            </div>
            <label class="toggle-switch" @click.stop>
              <input type="checkbox" :checked="sub.enabled" @change="handleToggleEnabled(sub)" />
              <span class="slider"></span>
            </label>
          </div>

          <div class="card-grid">
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

          <div class="card-actions">
            <button
              class="text-btn fetch-btn"
              @click="handleFetchSub(sub)"
              :class="{ fetching: fetchingMap[sub.id] }"
            >
              <span class="material-symbols-outlined icon-g-btn">cloud_download</span>
              {{ fetchingMap[sub.id] ? '拉取中' : '拉取' }}
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
            <label>订阅唯一 ID</label>
            <input v-model="formData.uid" type="text" placeholder="例：hunter，用于 sourceType" />
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { toast } from '@/components/Toast'
import { formatTime } from '@/shared'
import request from '@/api'

const subscriptions = ref([])
const loaded = ref(false)
const fetchingMap = ref({})
const formVisible = ref(false)
const editingId = ref(null)
const formData = reactive({ name: '', uid: '', url: '', fetchCron: '' })

const loadSubscriptions = async () => {
  try {
    const res = await request.get('/subscriptions')
    subscriptions.value = Array.isArray(res) ? res : []
  } catch {
    subscriptions.value = []
  }
  loaded.value = true
}

const startAddSub = () => {
  editingId.value = null
  formData.name = ''
  formData.uid = ''
  formData.url = ''
  formData.fetchCron = ''
  formVisible.value = true
}

const startEditSub = (sub) => {
  editingId.value = sub.id
  formData.name = sub.name
  formData.uid = sub.uid
  formData.url = sub.url
  formData.fetchCron = sub.fetchCron || ''
  formVisible.value = true
}

const cancelForm = () => {
  formVisible.value = false
  editingId.value = null
}

const handleSaveSub = async () => {
  if (!formData.name || !formData.uid || !formData.url) {
    toast.warning('请填写完整信息')
    return
  }
  try {
    if (editingId.value) {
      await request.put(`/subscriptions/${editingId.value}`, formData)
      toast.success('已更新')
    } else {
      await request.post('/subscriptions', formData)
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
  try {
    const { name, uid, url, fetchCron = '' } = sub
    await request.put(`/subscriptions/${sub.id}`, {
      name, uid, url, fetchCron,
      enabled: !sub.enabled,
    })
    await loadSubscriptions()
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

const handleFetchSub = async (sub) => {
  fetchingMap.value[sub.id] = true
  try {
    await request.post(`/subscriptions/${sub.id}/fetch`)
    toast.success('拉取任务已在后台启动')
    await loadSubscriptions()
  } catch {
    /* 错误由拦截器统一提示 */
  } finally {
    fetchingMap.value[sub.id] = false
  }
}

onMounted(loadSubscriptions)
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
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.config-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
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

/* ===== Toggle Switch ===== */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 42px;
  height: 24px;
  flex-shrink: 0;
}
.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #e8e8ed;
  transition: 0.3s;
  border-radius: 24px;
}
.slider:before {
  position: absolute;
  content: '';
  height: 20px;
  width: 20px;
  left: 2px;
  bottom: 2px;
  background: white;
  transition: 0.3s;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}
input:checked + .slider {
  background: #34c759;
}
input:checked + .slider:before {
  transform: translateX(18px);
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
.text-btn.fetch-btn {
  color: var(--color-blue);
}
.text-btn.fetch-btn.fetching {
  opacity: 0.5;
  pointer-events: none;
}
.text-btn.edit {
  color: var(--color-blue);
}
.text-btn.delete {
  color: var(--color-red);
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
  padding: 8px;
  border-radius: 50%;
}
.icon-g-btn {
  font-size: 18px !important;
}

/* ===== 空状态 ===== */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
  font-size: 14px;
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
.form-drawer {
  background: var(--bg-card);
  width: 100%;
  max-width: 420px;
  border-top-left-radius: var(--radius-card);
  border-top-right-radius: var(--radius-card);
  padding: 24px 24px calc(24px + env(safe-area-inset-bottom)) 24px;
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.1);
  animation: slide-up 0.35s var(--ease-spring);
}
.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
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
.drawer-actions {
  display: flex;
  gap: 10px;
  margin-top: 6px;
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
