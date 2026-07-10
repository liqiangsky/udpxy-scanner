<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">主机</h1>
      <div class="header-right">
        <div class="filter-counter-top">
          <span>{{ totalCount }}</span> 个
        </div>
        <div class="header-filters">
          <RegionFilter v-model="filterForm.region" />
          <OperatorFilter v-model="filterForm.operator" />
        </div>
        <div class="header-actions">
          <button class="recheck-btn" @click="handleRecheck" title="手动复测">
            <span class="material-symbols-outlined icon-g-btn">autorenew</span>
          </button>
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
          v-for="source in displayList"
          :key="source.id"
          class="hosts-grid-card"
          :class="{ 'card-selected': selection.has(source.id) }"
          @pointerdown="onPointerDown($event, source)"
          @pointerup="onPointerUp"
          @pointerleave="onPointerUp"
          @contextmenu.prevent
          @click="onCardClick(source)"
        >
          <div class="section-host">
            <div class="host-ip font-mono">{{ source.host }}</div>
            <div class="host-actions">
              <button
                v-if="authStore.isLoggedIn"
                class="action-btn delete-btn"
                @click.stop="handleDelete(source)"
              >
                <span class="material-symbols-outlined icon-g">delete</span>
              </button>
              <button class="copy-btn" @click.stop="handleCopy(source.host)">
                <span class="material-symbols-outlined icon-g">content_copy</span>
              </button>
            </div>
          </div>

          <div class="section-metrics-grid">
            <div class="grid-item">
              <span class="badge-lbl">地区</span>
              <span class="badge-txt color-blue">{{ source.region }}</span>
            </div>
            <div class="grid-item">
              <span class="badge-lbl">运营商</span>
              <span class="badge-txt color-blue">{{ source.operator }}</span>
            </div>
            <div class="grid-item">
              <span class="badge-lbl">状态</span>
              <div
                class="delay-interactive-badge"
                :class="{ 'state-error': source.delay < 0 }"
                @click.stop="handleTestDelay(source)"
              >
                <span class="material-symbols-outlined icon-g">bolt</span>
                <span class="badge-txt font-mono">{{ source.delay }} ms</span>
              </div>
            </div>
            <div class="grid-item">
              <span class="badge-lbl">来源</span>
              <span class="badge-txt">{{ source.sourceName }}</span>
            </div>
            <div class="grid-item time-column full-width">
              <span class="badge-lbl">发现</span>
              <div class="time-wrapper">
                <span class="material-symbols-outlined icon-g">history</span>
                <span class="badge-txt color-gray font-mono">{{
                  formatTime(source.createdAt)
                }}</span>
              </div>
            </div>
            <div class="grid-item time-column full-width">
              <span class="badge-lbl">验证</span>
              <div class="time-wrapper">
                <span class="material-symbols-outlined icon-g">update</span>
                <span class="badge-txt color-gray font-mono">{{
                  formatTime(source.updatedAt)
                }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-show="displayList.length < totalCount" class="load-more-wrap">
          <button
            class="load-more-btn"
            :class="{ loading: loadingMore }"
            :disabled="loadingMore"
            @click="loadMore"
          >
            <span v-if="loadingMore" class="material-symbols-outlined spinner-icon spinning"
              >sync</span
            >
            加载更多（剩余 {{ totalCount - displayList.length }} 条）
          </button>
        </div>

        <div v-if="displayList.length >= totalCount" class="all-loaded-hint">
          已加载全部 {{ totalCount }} 条
        </div>
      </template>

      <div v-if="!loading && totalCount === 0" class="empty-state">
        <p>暂无符合当前筛选条件的主机</p>
      </div>
    </div>

    <!-- 批量操作栏（替换底部 tabbar） -->
    <Transition name="batch-bar">
      <div v-if="selectMode" class="batch-tabbar">
        <button class="batch-tab-item" @click="selectAll">
          <span class="material-symbols-outlined batch-tab-icon">
            {{ allCurrentSelected ? 'deselect' : 'select_all' }}
          </span>
          <span class="batch-tab-text">{{
            allCurrentSelected ? `取消(${displayList.length})` : `全选(${displayList.length})`
          }}</span>
        </button>
        <div class="batch-tab-divider"></div>
        <button
          class="batch-tab-item"
          :class="{ disabled: selection.size === 0 }"
          :disabled="selection.size === 0"
          @click="handleBatchDelete"
        >
          <span class="material-symbols-outlined batch-tab-icon delete-color">delete</span>
          <span class="batch-tab-text delete-color">{{
            selection.size > 0 ? `删除(${selection.size})` : '删除'
          }}</span>
        </button>
        <div class="batch-tab-divider"></div>
        <button class="batch-tab-item" @click="exitSelectMode">
          <span class="material-symbols-outlined batch-tab-icon cancel-color">close</span>
          <span class="batch-tab-text cancel-color">取消</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import request from '@/api'
import RegionFilter from '@/components/RegionFilter.vue'
import OperatorFilter from '@/components/OperatorFilter.vue'
import { toast } from '@/components/Toast'
import { useAuthStore } from '@/stores/auth'
import { batchSelectActive, formatTime, copyToClipboard } from '@/shared'

const authStore = useAuthStore()

const filterForm = reactive({
  region: '',
  operator: '',
})

const rawHostsList = ref([])
const loading = ref(false)
const loadingMore = ref(false)

// 分页渲染控制
const PAGE_SIZE = 20
const currentPage = ref(1)
const totalCount = ref(0)
const totalPages = ref(0)

// 批量选择
const LONG_PRESS_MS = 500
let pressTimer = null
let longPressed = false
let pressTarget = null

const selectMode = ref(false)
const selection = reactive(new Set())

const enterSelectMode = (item) => {
  selectMode.value = true
  batchSelectActive.value = true
  if (item) selection.add(item.id)
}
const exitSelectMode = () => {
  selectMode.value = false
  batchSelectActive.value = false
  selection.clear()
}
const toggleSelect = (item) => {
  if (selection.has(item.id)) {
    selection.delete(item.id)
  } else {
    selection.add(item.id)
  }
}
const selectAll = () => {
  const allIds = displayList.value.map((s) => s.id)
  const allSelected = allIds.length > 0 && allIds.every((id) => selection.has(id))
  if (allSelected) {
    allIds.forEach((id) => selection.delete(id))
  } else {
    allIds.forEach((id) => selection.add(id))
  }
}

const onPointerDown = (e, item) => {
  if (e.button !== 0) return
  longPressed = false
  pressTarget = item
  pressTimer = setTimeout(() => {
    longPressed = true
    enterSelectMode(pressTarget)
  }, LONG_PRESS_MS)
}
const onPointerUp = () => {
  if (pressTimer) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
}
const onCardClick = (item) => {
  if (longPressed) {
    longPressed = false
    return
  }
  if (selectMode.value) {
    toggleSelect(item)
  }
}
const handleBatchDelete = async () => {
  if (selection.size === 0) return
  const selectedCount = selection.size
  const loadedCount = displayList.value.length
  // 明确告知"全选"实际只作用于已加载项，避免与跨页"全选所有"的预期混淆
  const scopeHint =
    totalCount.value > loadedCount
      ? `\n\n（当前已加载 ${loadedCount} / 共 ${totalCount.value} 项，本次仅删除已加载项中已选中的部分）`
      : ''
  const confirmed = confirm(
    `确定要删除 ${selectedCount} 个主机吗？${scopeHint}\n\n此操作不可恢复。`,
  )
  if (!confirmed) return

  const ids = [...selection]
  try {
    const res = await request.post('/hosts/batch-delete', { ids })
    if (res.ok) {
      const successIds = res.success || []
      const failedItems = res.failed || []
      const deletedCount = successIds.length

      if (deletedCount > 0) {
        toast.success(`成功删除 ${deletedCount} 个主机`)
        // 仅从本地列表中移除真正成功的项，避免与失败项不一致
        rawHostsList.value = rawHostsList.value.filter((i) => !successIds.includes(i.id))
        totalCount.value = Math.max(0, totalCount.value - deletedCount)
        successIds.forEach((id) => selection.delete(id))
      }
      if (failedItems.length > 0) {
        // 失败项保留在选中集，便于用户直接重试；host 字符串便于诊断
        const failedHosts = failedItems.map((f) => {
          const target = rawHostsList.value.find((i) => i.id === f.id)
          return target ? target.host : `#${f.id}`
        })
        toast.warning(`${failedItems.length} 个删除失败: ${failedHosts.join(', ')}`)
      }

      // 关键：当前页被删空且仍有数据时，重置到第一页重新拉取。
      // 不能 currentPage++：删除后 offset 偏移，简单 +1 会跳过原本紧邻的下一页数据
      if (rawHostsList.value.length === 0 && totalCount.value > 0) {
        await loadPool(true)
      }
    } else {
      toast.error(res.error || '批量删除失败')
    }
  } catch {
    /* 错误由拦截器统一提示 */
  }
  // 仅当选中集为空时退出选择模式（保留失败项以便重试）
  if (selection.size === 0) exitSelectMode()
}

const loadPool = async (reset = false) => {
  if (reset) {
    currentPage.value = 1
    rawHostsList.value = []
    loading.value = true
  } else {
    loadingMore.value = true
    await nextTick()
  }
  try {
    const params = { page: currentPage.value, page_size: PAGE_SIZE }
    if (filterForm.region) params.region = filterForm.region
    if (filterForm.operator) params.operator = filterForm.operator

    const res = await request.get('/hosts', { params })
    const items = res.items || []

    if (reset) {
      rawHostsList.value = items
    } else {
      rawHostsList.value.push(...items)
    }

    totalCount.value = res.total
    totalPages.value = res.totalPages
  } catch (e) {
    console.error('加载主机池失败:', e)
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

const displayList = computed(() => rawHostsList.value)

// 当前已加载项是否全部处于选中状态（用于 tabbar 全选/取消标签）
const allCurrentSelected = computed(
  () => displayList.value.length > 0 && displayList.value.every((s) => selection.has(s.id)),
)

const loadMore = () => {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
    loadPool()
  }
}

// 筛选变化时重置分页并退出选择模式
watch(
  () => ({ region: filterForm.region, operator: filterForm.operator }),
  () => {
    loadPool(true)
    exitSelectMode()
  },
)

const handleRecheck = async () => {
  try {
    await request.post('/recheck')
    toast.success('已启动复测')
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

const handleCopy = async (host) => {
  const ok = await copyToClipboard(host)
  if (ok) {
    toast.success(`已复制: ${host}`)
  } else {
    toast.error('复制失败')
  }
}

const handleTestDelay = async (item) => {
  if (!authStore.isLoggedIn) {
    return
  }
  try {
    const res = await request.post(`/hosts/${item.id}/test-delay`)
    if (res.ok) {
      item.delay = res.delay
      item.updatedAt = res.updatedAt
      toast.success(`延迟: ${res.delay}ms`)
    } else {
      item.delay = -1
      item.updatedAt = res.updatedAt
      toast.warning('超时或不可达')
    }
  } catch {
    item.delay = -1
  }
}

const handleDelete = async (item) => {
  if (!authStore.isLoggedIn) {
    return
  }
  const confirmed = confirm(`确定要删除主机 ${item.host} 吗？\n\n此操作不可恢复。`)
  if (!confirmed) {
    return
  }
  try {
    const res = await request.delete(`/hosts/${item.id}`)
    if (res.ok) {
      toast.success('已删除')
      // 从列表中移除
      rawHostsList.value = rawHostsList.value.filter((i) => i.id !== item.id)
      totalCount.value = Math.max(0, totalCount.value - 1)
      // 同步清理选择集
      selection.delete(item.id)
      // 单条删除同样避免页面变空白：当前页空了且仍有数据 → 重置第一页重新拉取
      if (rawHostsList.value.length === 0 && totalCount.value > 0) {
        await loadPool(true)
      }
    } else {
      toast.error(res.error || '删除失败')
    }
  } catch {
    /* 错误由拦截器统一提示 */
  }
}

onMounted(() => {
  loadPool()
})

onBeforeUnmount(() => {
  selectMode.value = false
  batchSelectActive.value = false
  selection.clear()
})
</script>

<style scoped>
/* 页面顶部 */
.page-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  background: rgba(245, 245, 247, 0.92);
  backdrop-filter: blur(20px);
  padding: 12px 16px;
  min-height: 58px;
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
  .header-right {
    max-width: 720px;
  }
}

@media (min-width: 1024px) {
  .page-header {
    max-width: 1100px;
  }
  .header-right {
    max-width: 1100px;
  }
}

@media (min-width: 1440px) {
  .page-header {
    max-width: 1400px;
  }
  .header-right {
    max-width: 1400px;
  }
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  white-space: nowrap;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  justify-content: flex-end;
}
.filter-counter-top {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.filter-counter-top span {
  color: var(--color-green);
  font-weight: 700;
}
.header-filters {
  display: flex;
  gap: 8px;
}
.apple-select-sm {
  appearance: none;
  -webkit-appearance: none;
  background-color: var(--bg-neutral);
  color: var(--text-primary);
  border: none;
  padding: 6px 28px 6px 10px;
  border-radius: var(--radius-input);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  outline: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='%238E8E93' d='M0 0h10L5 6z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 10px center;
}
.apple-select-sm:active,
.apple-select-sm:hover {
  background-color: #e8e8ed;
}

/* 列表 */
.list-wrapper {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  width: 100%;
  max-width: var(--max-content);
  padding-bottom: 40px;
}

@media (min-width: 768px) {
  .list-wrapper {
    max-width: 720px;
  }
}

@media (min-width: 1024px) {
  .list-wrapper {
    max-width: 1100px;
  }
}

@media (min-width: 1440px) {
  .list-wrapper {
    max-width: 1400px;
  }
}

/* 批量操作 tabbar */
.batch-tabbar {
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
.batch-tab-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  -webkit-tap-highlight-color: transparent;
  transition: all 0.2s ease;
}
.batch-tab-item:active {
  transform: scale(0.92);
}
.batch-tab-item.disabled {
  opacity: 0.3;
  pointer-events: none;
}
.batch-tab-icon {
  font-size: 22px !important;
  color: var(--color-blue);
  font-variation-settings:
    'FILL' 0,
    'wght' 400;
}
.batch-tab-icon.delete-color {
  color: var(--color-red);
}
.batch-tab-icon.cancel-color {
  color: var(--text-muted);
}
.batch-tab-text {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-blue);
  font-family: var(--font-sans);
}
.batch-tab-text.delete-color {
  color: var(--color-red);
}
.batch-tab-text.cancel-color {
  color: var(--text-muted);
}
.batch-tab-divider {
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

/* 卡片样式 */
.hosts-grid-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 18px;
  box-shadow: var(--shadow-md);
  border: 1px solid rgba(0, 0, 0, 0.01);
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.2s ease;
}
.hosts-grid-card.card-selected {
  border-color: var(--color-blue);
  box-shadow:
    0 0 0 1px rgba(0, 122, 255, 0.15),
    var(--shadow-md);
}

.section-host {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.host-ip {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.font-mono {
  font-family: var(--font-mono);
  letter-spacing: -0.3px;
}

.host-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.action-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border: none;
  cursor: pointer;
}

.delete-btn {
  background: #fdecea;
  color: #e5484d;
}
.delete-btn:active {
  transform: scale(0.9);
  background: #f5d6d3;
}
.delete-btn .icon-g {
  color: #e5484d;
}

.copy-btn {
  background: #e3f2fd;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
}
.copy-btn:active {
  transform: scale(0.9);
  background: #bbdefb;
}

.section-metrics-grid {
  border-top: 1px solid #f1f5f9;
  padding-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
}

.grid-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.grid-item.full-width {
  grid-column: span 2;
}

.badge-lbl {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  width: 38px;
  flex-shrink: 0;
}

.badge-txt {
  font-size: 12px;
  font-weight: 600;
}

.color-blue {
  color: var(--color-blue);
}
.color-gray {
  color: var(--text-secondary);
}

.delay-interactive-badge {
  background: var(--bg-status-good);
  color: var(--color-green);
  padding: 3px 8px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.delay-interactive-badge:active {
  transform: scale(0.95);
}
.delay-interactive-badge.state-error {
  background: #fdecea;
  color: #e5484d;
}
.delay-interactive-badge.state-error .icon-g {
  color: #e5484d;
}

.time-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
}

.icon-g {
  font-size: 16px !important;
  font-variation-settings:
    'FILL' 0,
    'wght' 400,
    'GRAD' 0,
    'opsz' 24;
  display: inline-block;
  vertical-align: middle;
}
.copy-btn .icon-g {
  color: var(--color-blue);
}
.delay-interactive-badge .icon-g {
  color: var(--color-green);
}
.time-wrapper .icon-g {
  color: var(--text-muted);
}

/* 页头操作区 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* 复测按钮 */
.recheck-btn {
  background: var(--color-orange);
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
.recheck-btn:active {
  transform: scale(0.9);
}
.recheck-btn .icon-g-btn {
  font-size: 18px !important;
}

/* 加载更多 */
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
.load-more-btn:active {
  transform: scale(0.96);
  background: #e8e8ed;
}
.load-more-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}
.spinner-icon {
  font-size: 16px !important;
  vertical-align: middle;
  margin-right: 4px;
}
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
.spinning {
  animation: spin 1s linear infinite;
}
.all-loaded-hint {
  grid-column: 1 / -1;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 0;
}
</style>
