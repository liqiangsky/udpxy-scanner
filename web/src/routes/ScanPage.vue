<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">扫描</h1>
      <button class="action-btn primary-btn" @click="openForm()">
        <span class="material-symbols-outlined icon-g-btn">add</span>
      </button>
    </div>

    <div class="header-spacer"></div>

    <div class="config-list">
      <div v-if="!scanConfigStore.loaded" class="skeleton-list">
        <div v-for="i in 3" :key="i" class="skeleton-card">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-sub"></div>
          <div class="skeleton-line skeleton-sub narrow"></div>
        </div>
      </div>
      <TransitionGroup v-else name="list-fade">
        <div
          v-for="config in configs"
          :key="config.id"
          class="config-card"
          :class="{
            'status-scanning': scanningId === config.id,
            'status-queued': queuedIds.includes(config.id),
            'status-disabled': !config.enabled,
          }"
        >
          <div class="card-top">
            <div class="config-identity">
              <h3 class="config-name">{{ config.name }}</h3>
              <span
                class="status-dot-badge"
                :class="
                  scanningId === config.id
                    ? 'scanning'
                    : queuedIds.includes(config.id)
                      ? 'queued'
                      : config.enabled
                        ? 'idle'
                        : 'disabled'
                "
              >
                {{
                  scanningId === config.id
                    ? '扫描中...'
                    : queuedIds.includes(config.id)
                      ? '排队中'
                      : config.enabled
                        ? '已停止'
                        : '已禁用'
                }}
              </span>
            </div>

            <button
              class="run-toggle-btn"
              :class="
                scanningId === config.id
                  ? 'scanning'
                  : queuedIds.includes(config.id)
                    ? 'queued'
                    : 'idle'
              "
              @click="toggleScan(config)"
              :title="
                scanningId === config.id
                  ? '停止扫描'
                  : queuedIds.includes(config.id)
                    ? '从队列中移除'
                    : '启动扫描'
              "
            >
              <span
                v-if="activeIds.includes(config.id)"
                class="material-symbols-outlined icon-g-toggle"
                >stop</span
              >
              <span v-else class="material-symbols-outlined icon-g-toggle">play_arrow</span>
            </button>
          </div>

          <div class="card-grid">
            <div class="grid-item full-width">
              <span class="lbl">订阅源</span>
              <span class="txt color-blue">{{ dataSourceLabel(config.dataSource) }}</span>
            </div>
            <div class="grid-item">
              <span class="lbl">地区</span>
              <span class="txt color-blue">{{ config.templateRegion || '-' }}</span>
            </div>
            <div class="grid-item">
              <span class="lbl">运营商</span>
              <span class="txt color-blue">{{ config.templateOperator || '-' }}</span>
            </div>
            <div class="grid-item full-width">
              <span class="lbl">目标</span>
              <span class="txt color-dark truncate">{{ config.templateTargetName || '-' }}</span>
            </div>
            <div class="grid-item full-width">
              <span class="lbl">地址</span>
              <span class="txt font-mono color-gray truncate">{{
                config.templateTargetAddress || '-'
              }}</span>
            </div>
          </div>

          <div class="card-actions" v-show="scanningId !== config.id">
            <button
              class="text-btn toggle-enable"
              :class="{ disabled: !config.enabled }"
              @click="handleToggleEnable(config)"
            >
              <span class="material-symbols-outlined icon-g-btn">{{
                config.enabled ? 'toggle_on' : 'toggle_off'
              }}</span>
              {{ config.enabled ? '禁用' : '启用' }}
            </button>
            <button class="text-btn edit" @click="openForm(config)">
              <span class="material-symbols-outlined icon-g-btn">edit</span> 编辑
            </button>
            <button class="text-btn delete" @click="handleDelete(config.id)">
              <span class="material-symbols-outlined icon-g-btn">delete</span> 删除
            </button>
          </div>
        </div>
      </TransitionGroup>

      <div v-if="scanConfigStore.loaded && configs.length === 0" class="empty-state">
        暂无扫描配置，点击右上角新建
      </div>
    </div>

    <div v-if="formState.visible" class="form-overlay" @click="closeForm">
      <div class="form-drawer" @click.stop>
        <div class="drawer-header">
          <h2>{{ formState.isEdit ? '修改配置' : '新增配置' }}</h2>
          <button class="close-x-btn" @click="closeForm">×</button>
        </div>

        <form @submit.prevent="handleSubmit" class="drawer-form">
          <div class="form-item">
            <label>配置名称</label>
            <input v-model="formData.name" type="text" placeholder="如：北京联通" required />
          </div>

          <div class="form-item">
            <label>订阅源</label>
            <div class="source-selector">
              <label
                class="source-tag all-tag"
                :class="{ active: formData.dataSources.length === 0 }"
              >
                <input
                  type="checkbox"
                  :checked="formData.dataSources.length === 0"
                  @change="toggleAllSources"
                />
                全部
              </label>
              <label
                v-for="ds in enabledDataSources"
                :key="ds.value"
                class="source-tag"
                :class="{ active: formData.dataSources.includes(ds.value) }"
              >
                <input
                  type="checkbox"
                  :value="ds.value"
                  :checked="formData.dataSources.includes(ds.value)"
                  @change="toggleSource(ds.value)"
                />
                {{ ds.label }}
              </label>
            </div>
            <p class="field-hint">不选表示扫描全部启用的订阅源</p>
          </div>

          <div class="form-row-2col">
            <div class="form-item">
              <label>地区</label>
              <select v-model="formData.region" required>
                <option value="" disabled>选择地区</option>
                <option v-for="r in regions" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>

            <div class="form-item">
              <label>运营商</label>
              <select v-model="formData.operator" required>
                <option value="" disabled>选择运营商</option>
                <option v-for="o in operators" :key="o" :value="o">{{ o }}</option>
              </select>
            </div>
          </div>

          <div class="form-item">
            <label>目标名称</label>
            <input v-model="formData.targetName" type="text" placeholder="如：CCTV1" required />
          </div>

          <div class="form-item">
            <label>目标地址</label>
            <input
              v-model="formData.targetAddress"
              type="text"
              placeholder="如：239.76.253.104:9000"
              required
            />
          </div>

          <div class="form-buttons">
            <button type="button" class="action-btn cancel-btn" @click="closeForm">取消</button>
            <button type="submit" class="action-btn primary-btn-submit">保存配置</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import request from '@/api'
import { toast } from '@/components/Toast'
import { useScanConfigStore } from '@/stores/scanConfig'
import { regions, operators } from '@/data.js'

const scanConfigStore = useScanConfigStore()

const configs = computed(() => scanConfigStore.configs)
const progress = computed(() => scanConfigStore.progress)

const scanningId = computed(() => (progress.value.running ? progress.value.currentId : null))
const queuedIds = computed(() => (progress.value.running ? progress.value.queuedIds : []))
const activeIds = computed(() => {
  const ids = [...queuedIds.value]
  if (scanningId.value) ids.unshift(scanningId.value)
  return ids
})

// 订阅源标签
const dataSourceLabel = (ds) => {
  if (!ds) return '全部'
  const found = enabledDataSources.value.find((s) => s.value === ds)
  return found ? found.label : ds
}

const toggleSource = (val) => {
  const idx = formData.dataSources.indexOf(val)
  if (idx >= 0) formData.dataSources.splice(idx, 1)
  else formData.dataSources.push(val)
}

const toggleAllSources = () => {
  formData.dataSources = []
}

// 订阅源列表（从 API 查询订阅列表）
const enabledDataSources = ref([])

const loadDataSources = async () => {
  try {
    const res = await request.get('/data-sources')
    if (res?.sources) {
      enabledDataSources.value = res.sources
    }
  } catch {
    // 静默失败
  }
}

// 表单状态
const formState = reactive({
  visible: false,
  isEdit: false,
  currentId: null,
})

const getDefaultFormData = () => ({
  name: '',
  region: '',
  operator: '',
  targetName: '',
  targetAddress: '',
  dataSources: [],
  dataSource: '',
  enabled: true,
})

const formData = reactive(getDefaultFormData())

const toggleScan = async (config) => {
  if (!config.enabled) {
    toast.info('该配置已禁用，无法扫描')
    return
  }
  const isActive = activeIds.value.includes(config.id)

  try {
    if (isActive) {
      await request.post(`/configs/${config.id}/stop`)
      toast.info('已停止扫描')
    } else {
      await request.post(`/configs/${config.id}/run`)
      scanConfigStore.addToQueue(config.id)
      toast.success(scanConfigStore.progress.running ? '已加入队列' : '扫描任务已启动')
      scanConfigStore.startPolling()
    }
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

const openForm = (editTarget = null) => {
  if (editTarget) {
    formState.isEdit = true
    formState.currentId = editTarget.id
    const rawDs = editTarget.dataSource || ''
    Object.assign(formData, {
      name: editTarget.name,
      region: editTarget.templateRegion || '',
      operator: editTarget.templateOperator || '',
      targetName: editTarget.templateTargetName || '',
      targetAddress: editTarget.templateTargetAddress || '',
      dataSources: rawDs ? rawDs.split(',').filter(Boolean) : [],
      dataSource: rawDs,
      enabled: editTarget.enabled,
    })
  } else {
    formState.isEdit = false
    formState.currentId = null
    Object.assign(formData, getDefaultFormData())
  }
  formState.visible = true
}

const closeForm = () => {
  formState.visible = false
}

const handleSubmit = async () => {
  if (!formData.name?.trim()) {
    toast.error('配置名称不能为空')
    return
  }
  if (!formData.region) {
    toast.error('请选择地区')
    return
  }
  if (!formData.operator) {
    toast.error('请选择运营商')
    return
  }
  if (!formData.targetName?.trim()) {
    toast.error('请输入目标名称')
    return
  }
  if (!formData.targetAddress?.trim()) {
    toast.error('请输入目标地址')
    return
  }

  const payload = {
    ...formData,
    dataSource: formData.dataSources.join(','),
  }
  delete payload.dataSources

  try {
    if (formState.isEdit) {
      await request.put(`/configs/${formState.currentId}`, payload)
    } else {
      await request.post('/configs', payload)
    }
    await scanConfigStore.refresh()
    closeForm()
    toast.success('保存成功')
  } catch (e) {
    console.error(e)
  }
}

const handleDelete = async (id) => {
  if (!confirm('确定删除该配置？')) return

  try {
    await request.delete(`/configs/${id}`)
    toast.success('已删除')
    await scanConfigStore.refresh()
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

const handleToggleEnable = async (config) => {
  if (activeIds.value.includes(config.id)) {
    toast.info('该配置正在运行或排队中，无法禁用')
    return
  }
  const newEnabled = !config.enabled
  try {
    const { name, templateRegion, templateOperator, templateTargetName, templateTargetAddress, dataSource = '' } = config
    await request.put(`/configs/${config.id}`, {
      name,
      region: templateRegion || '',
      operator: templateOperator || '',
      targetName: templateTargetName || '',
      targetAddress: templateTargetAddress || '',
      dataSource,
      enabled: newEnabled,
    })
    toast.success(newEnabled ? '已启用' : '已禁用')
    await scanConfigStore.refresh()
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

onMounted(async () => {
  await loadDataSources()
  await scanConfigStore.startPolling()
  await scanConfigStore.fetch()
})

onUnmounted(() => {
  scanConfigStore.stopPolling()
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
.action-btn {
  border: none;
  outline: none;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s ease;
  -webkit-tap-highlight-color: transparent;
}
.primary-btn {
  background: var(--color-blue);
  color: #ffffff;
  padding: 8px;
  border-radius: 50%;
  font-size: 13.5px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.primary-btn:active {
  transform: scale(0.96);
  background: #0066d6;
}
.icon-g-btn {
  font-size: 18px !important;
  font-variation-settings:
    'FILL' 0,
    'wght' 600,
    'GRAD' 0,
    'opsz' 24;
}

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
.config-card.status-scanning {
  border-color: rgba(52, 199, 89, 0.3);
  box-shadow: 0 4px 24px rgba(52, 199, 89, 0.08);
  position: relative;
  overflow: hidden;
}
.config-card.status-scanning::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, #34c759, transparent);
}
.config-card.status-queued {
  border-color: rgba(255, 149, 0, 0.3);
  box-shadow: 0 4px 24px rgba(255, 149, 0, 0.08);
  position: relative;
  overflow: hidden;
}
.config-card.status-queued::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, #ff9500, transparent);
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}
.config-identity {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 75%;
}
.config-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
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
.status-dot-badge.scanning {
  color: #fff;
  background: #34c759;
}
.status-dot-badge.scanning::before {
  background: #fff;
  animation: pulse 1.5s infinite;
}
.status-dot-badge.queued {
  color: #fff;
  background: #ff9500;
}
.status-dot-badge.queued::before {
  background: #fff;
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
.run-toggle-btn.scanning {
  background: var(--bg-status-error);
  color: var(--color-red);
}
.run-toggle-btn.queued {
  background: var(--bg-status-warn);
  color: var(--color-orange);
}
.run-toggle-btn:active {
  transform: scale(0.9);
}

.config-card.status-disabled {
  background: #f0f0f2;
  border-color: rgba(0, 0, 0, 0.06);
}
.config-card.status-disabled .config-name {
  color: #8e8e93;
}
.status-dot-badge.disabled {
  color: #fff;
  background: #8e8e93;
}
.status-dot-badge.disabled::before {
  background: #fff;
  opacity: 0.7;
}

.card-grid {
  border-top: 1px solid var(--bg-neutral);
  padding-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
}
.grid-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.grid-item.full-width {
  grid-column: span 2;
}
.lbl {
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
  width: 48px;
}
.txt {
  font-size: 13.5px;
  font-weight: 600;
}
.color-blue {
  color: var(--color-blue);
}
.color-dark {
  color: var(--text-primary);
}
.color-gray {
  color: #515154;
  font-weight: 500;
}
.font-mono {
  font-family: var(--font-mono);
  letter-spacing: -0.3px;
}
.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

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
.form-row-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
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

.drawer-form input,
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
}
.drawer-form select {
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='%238E8E93' d='M0 0h10L5 6z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 14px center;
}
.drawer-form input::placeholder {
  color: var(--text-disabled);
}

.source-selector {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.source-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: var(--radius-input);
  background: var(--bg-neutral);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  transition: all 0.15s ease;
  border: 1.5px solid transparent;
}
.source-tag input {
  display: none;
}
.source-tag.active {
  background: rgba(0, 122, 255, 0.12);
  color: var(--color-blue);
  border-color: var(--color-blue);
}
.source-tag.all-tag.active {
  background: var(--color-blue);
  color: #fff;
  border-color: var(--color-blue);
}
.field-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
}

.form-buttons {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 12px;
  margin-top: 12px;
}
.primary-btn-submit {
  background: var(--color-blue);
  color: #ffffff;
  padding: 12px;
  border: none;
  border-radius: var(--radius-btn);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}
.primary-btn-submit:active {
  transform: scale(0.98);
  background: #0066d6;
}

.cancel-btn {
  background: var(--bg-neutral);
  color: var(--text-muted);
  padding: 12px;
  border-radius: var(--radius-btn);
  font-size: 15px;
  width: 100%;
}
.cancel-btn:active {
  background: #e8e8ed;
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
@keyframes slide-up {
  from {
    transform: translateY(100%);
  }
  to {
    transform: translateY(0);
  }
}

.list-fade-enter-active,
.list-fade-leave-active {
  transition: all 0.3s var(--ease-spring);
}
.list-fade-enter-from,
.list-fade-leave-to {
  opacity: 0;
  transform: scale(0.93) translateY(12px);
}
</style>
