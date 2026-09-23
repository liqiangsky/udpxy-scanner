import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/api'

export const useSubscriptionStore = defineStore('subscription', () => {
  const subscriptions = ref([])
  const loaded = ref(false)

  const progress = ref({
    running: false,
    currentId: null,
    queuedIds: [],
  })
  let pollTimer = null

  const fetch = async () => {
    subscriptions.value = await request.get('/subscriptions')
    loaded.value = true
    return subscriptions.value
  }

  const loadProgress = async () => {
    const res = await request.get('/subscriptions/progress')
    progress.value = {
      running: res.running,
      fetchingIds: res.fetchingIds || [],
    }

    if (res.running) {
      if (!pollTimer) {
        pollTimer = setInterval(loadProgress, 2000)
      }
    } else {
      stopPolling()
      // 拉取结束后刷新列表（lastFetchAt 已更新）
      if (loaded.value) {
        fetch().catch(() => {})
      }
    }
  }

  const startPolling = async () => {
    if (pollTimer) return
    await loadProgress()
  }

  const stopPolling = () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const refresh = async () => {
    subscriptions.value = await request.get('/subscriptions')
    loaded.value = true
  }

  /**
   * 原子化更新 progress：将订阅标记为拉取中
   * 避免组件层直接修改 progress 导致竞态条件
   */
  const addToQueue = (subId) => {
    if (progress.value.running) {
      if (!progress.value.fetchingIds.includes(subId)) {
        progress.value.fetchingIds.push(subId)
      }
    } else {
      progress.value.running = true
      progress.value.fetchingIds = [subId]
    }
  }

  return {
    subscriptions,
    loaded,
    progress,
    fetch,
    loadProgress,
    startPolling,
    stopPolling,
    refresh,
    addToQueue,
  }
})
