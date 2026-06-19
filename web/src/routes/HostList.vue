<template>
  <div class="page-container">

    <div class="page-header">
      <h1 class="page-title">组播源</h1>
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
          @copy="handleCopy"
          @test="handleTestDelay"
          @delete="handleDelete"
        />

        <div v-if="displayList.length < filteredList.length" class="load-more-wrap">
          <button class="load-more-btn" @click="loadMore">
            加载更多（剩余 {{ filteredList.length - displayList.length }} 条）
          </button>
        </div>

        <div v-if="displayList.length === filteredList.length && displayList.length >= 50" class="all-loaded-hint">
          已加载全部 {{ filteredList.length }} 条
        </div>
      </template>

      <div v-if="!loading && filteredList.length === 0" class="empty-state">
        <p>暂无符合当前筛选条件的组播源</p>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, watch } from 'vue'
import request from '@/api'
import IptvHostCard from '@/components/HostCard.vue'
import {regions, operators} from '@/data.js'
import { toast } from '@/components/Toast'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const filterForm = reactive({
  region: '',
  operator: ''
})

const rawIptvList = ref([])
const loading = ref(false)

// 分页渲染控制
const PAGE_SIZE = 20
const displayCount = ref(PAGE_SIZE)

// 地区与运营商动态字典
const regionMap = reactive({})
const operatorMap = reactive({})





const loadPool = async () => {
  loading.value = true
  try {
    authStore.init()
    const params = {}
    if (filterForm.region) {
      params.region = filterForm.region
    }
    if (filterForm.operator) {
      params.operator = filterForm.operator
    }
    const res = await request.get('/iptv-pool', { params })
    const flatList = []

    res.groups.forEach(group => {

      group.heads.forEach(item => {

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
          sourceName: item.sourceName
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
  return rawIptvList.value.filter(item => {
    const matchRegion =
      !filterForm.region ||
      item.region === filterForm.region

    const matchOperator =
      !filterForm.operator ||
      item.operator === filterForm.operator

    return matchRegion && matchOperator
  })
})

const displayList = computed(() => {
  return filteredList.value.slice(0, displayCount.value)
})

const loadMore = () => {
  displayCount.value = Math.min(displayCount.value + PAGE_SIZE, filteredList.value.length)
}

// 筛选变化时重置分页
watch(
  () => ({ region: filterForm.region, operator: filterForm.operator }),
  () => { displayCount.value = PAGE_SIZE }
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
    toast.error('测试失败')
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
      rawIptvList.value = rawIptvList.value.filter(i => i.id !== item.id)
    } else {
      toast.error(res.error || '删除失败')
    }
  } catch {
    toast.error('删除失败')
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
  background-color: #E8E8ED;
}

/* 筛选栏 */
.header-spacer {
  height: 56px;
  flex-shrink: 0;
}

/* 列表 */
.list-wrapper {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  width: 100%;
  max-width: var(--max-content);
  padding-bottom: 60px;
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

/* 骨架屏 */
.skeleton-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.skeleton-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.skeleton-line {
  height: 16px;
  border-radius: 8px;
  background: linear-gradient(90deg, var(--bg-neutral) 25%, #E8E8ED 50%, var(--bg-neutral) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s infinite;
}
.skeleton-title { width: 60%; }
.skeleton-sub { width: 40%; }
@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
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
  background: #E8E8ED;
}
.all-loaded-hint {
  grid-column: 1 / -1;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 0;
}
</style>
