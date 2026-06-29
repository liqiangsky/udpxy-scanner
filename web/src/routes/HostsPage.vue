<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">主机</h1>
      <div class="header-right">
        <div class="filter-counter-top">
          <span>{{ filteredList.length }}</span> 个可用
        </div>
        <div class="header-filters">
          <div class="select-wrapper-inline">
            <select v-model="filterForm.region" class="apple-select-sm">
              <option value="">全部地区</option>
              <option v-for="opt in regions" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </div>
          <div class="select-wrapper-inline">
            <select v-model="filterForm.operator" class="apple-select-sm">
              <option value="">全部网络</option>
              <option v-for="opt in operators" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </div>
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
        <IptvHostCard
          v-for="source in displayList"
          :key="source.id"
          :item="source"
          :is-authenticated="authStore.isLoggedIn"
          :selected="selection.has(source.id)"
          :select-mode="selectMode"
          @copy="handleCopy"
          @test="handleTestDelay"
          @delete="handleDelete"
          @toggle-select="toggleSelect"
          @longpress="handleLongPress(source)"
        />

        <div v-if="displayList.length < filteredList.length" class="load-more-wrap">
          <button class="load-more-btn" @click="loadMore">
            加载更多（剩余 {{ filteredList.length - displayList.length }} 条）
          </button>
        </div>

        <div
          v-if="displayList.length === filteredList.length && displayList.length >= 50"
          class="all-loaded-hint"
        >
          已加载全部 {{ filteredList.length }} 条
        </div>
      </template>

      <div v-if="!loading && filteredList.length === 0" class="empty-state">
        <p>暂无符合当前筛选条件的组播源</p>
      </div>
    </div>

    <!-- 批量操作栏（替换底部 tabbar） -->
    <Transition name="batch-bar">
      <div v-if="selectMode" class="batch-tabbar">
        <button class="batch-tab-item" @click="selectAll">
          <span class="material-symbols-outlined batch-tab-icon">
            {{ displayList.length > 0 && displayList.every(s => selection.has(s.id)) ? 'deselect' : 'select_all' }}
          </span>
          <span class="batch-tab-text">全选</span>
        </button>
        <div class="batch-tab-divider"></div>
        <button class="batch-tab-item" :class="{ disabled: selection.size === 0 }" :disabled="selection.size === 0" @click="handleBatchDelete">
          <span class="material-symbols-outlined batch-tab-icon delete-color">delete</span>
          <span class="batch-tab-text delete-color">删除</span>
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
import { ref, computed, reactive, onMounted, watch } from 'vue'
import request from '@/api'
import IptvHostCard from '@/components/HostCard.vue'
import { regions, operators } from '@/data.js'
import { toast } from '@/components/Toast'
import { useAuthStore } from '@/stores/auth'
import { batchSelectActive } from '@/shared'

const authStore = useAuthStore()

const filterForm = reactive({
  region: '',
  operator: '',
})

const rawIptvList = ref([])
const loading = ref(false)

// 分页渲染控制
const PAGE_SIZE = 20
const displayCount = ref(PAGE_SIZE)

// 批量选择
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
const handleLongPress = (item) => {
  if (!authStore.isLoggedIn) return
  enterSelectMode(item)
}
const handleBatchDelete = async () => {
  if (selection.size === 0) return
  const confirmed = confirm(`确定要删除选中的 ${selection.size} 个组播源吗？\n\n此操作不可恢复。`)
  if (!confirmed) return

  const ids = [...selection]
  try {
    const res = await request.post('/iptv/batch-delete', { ids })
    if (res.ok) {
      const deletedCount = res.success?.length || 0
      if (deletedCount > 0) {
        toast.success(`成功删除 ${deletedCount} 个组播源`)
        rawIptvList.value = rawIptvList.value.filter((i) => !ids.includes(i.id))
      }
      if (res.failed?.length > 0) {
        toast.warning(`${res.failed.length} 个删除失败`)
      }
    } else {
      toast.error(res.error || '批量删除失败')
    }
  } catch {
    /* 错误由拦截器统一提示 */
  }
  exitSelectMode()
}

// 地区与运营商动态字典
const regionMap = reactive({})
const operatorMap = reactive({})

const loadPool = async () => {
  loading.value = true
  try {
    const params = {}
    if (filterForm.region) {
      params.region = filterForm.region
    }
    if (filterForm.operator) {
      params.operator = filterForm.operator
    }
    const res = await request.get('/iptv-pool', { params })
    const flatList = []

    res.groups.forEach((group) => {
      group.heads.forEach((item) => {
        flatList.push({
          id: item.id,

          host: item.host,

          delay: item.latencyMs,

          time: item.lastSeen,

          //
          // 业务归属
          //
          region: item.region,
          operator: item.operator,

          //
          // GEOIP
          //
          geoRegion: item.geoRegion,
          geoOperator: item.geoOperator,

          //
          // 播放
          //
          playUrl: item.url,

          protocol: item.protocol,
          target: item.target,

          //
          // 频道
          //
          channelName: item.channelName,

          //
          // 时间
          //
          createTime: item.createTime,
          lastSeen: item.lastSeen,

          //
          // 来源
          //
          sourceType: item.sourceType,
          sourceName: item.sourceName,
        })

        //
        // 动态筛选字典
        //
        if (item.region) {
          regionMap[item.region] = item.region
        }

        if (item.operator) {
          operatorMap[item.operator] = item.operator
        }
      })
    })
    rawIptvList.value = flatList
  } catch (e) {
    console.error('加载组播池失败:', e)
  } finally {
    loading.value = false
  }
}
const filteredList = computed(() => {
  return rawIptvList.value.filter((item) => {
    const matchRegion = !filterForm.region || item.region === filterForm.region

    const matchOperator = !filterForm.operator || item.operator === filterForm.operator

    return matchRegion && matchOperator
  })
})

const displayList = computed(() => {
  return filteredList.value.slice(0, displayCount.value)
})

const loadMore = () => {
  displayCount.value = Math.min(displayCount.value + PAGE_SIZE, filteredList.value.length)
}

// 筛选变化时重置分页并退出选择模式
watch(
  () => ({ region: filterForm.region, operator: filterForm.operator }),
  () => {
    displayCount.value = PAGE_SIZE
    exitSelectMode()
  },
)

const handleCopy = async (host) => {
  try {
    await navigator.clipboard.writeText(host)
    toast.success(`HOST 已复制: ${host}`)
  } catch {
    toast.error('复制失败')
  }
}

const handleTestDelay = async (item) => {
  if (!authStore.isLoggedIn) {
    return
  }
  try {
    const res = await request.post(`/iptv/${item.id}/test-delay`)
    if (res.ok) {
      item.delay = res.delay
      toast.success(`延迟: ${res.delay}ms`)
    } else {
      item.delay = -1
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
  const confirmed = confirm(`确定要删除组播源 ${item.host} 吗？\n\n此操作不可恢复。`)
  if (!confirmed) {
    return
  }
  try {
    const res = await request.delete(`/iptv/${item.id}`)
    if (res.ok) {
      toast.success('删除成功')
      // 从列表中移除
      rawIptvList.value = rawIptvList.value.filter((i) => i.id !== item.id)
      // 同步清理选择集
      selection.delete(item.id)
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
  padding-bottom: 50px;
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

/* 卡片动画 */
.card-fade-enter-active,
.card-fade-leave-active {
  transition: all 0.3s var(--ease-spring);
}
.card-fade-enter-from,
.card-fade-leave-to {
  opacity: 0;
  transform: scale(0.92) translateY(10px);
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
  font-variation-settings: 'FILL' 0, 'wght' 400;
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
.all-loaded-hint {
  grid-column: 1 / -1;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 0;
}
</style>
