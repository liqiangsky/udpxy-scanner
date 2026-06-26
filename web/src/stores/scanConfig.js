import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/api'

export const useScanConfigStore = defineStore('scanConfig', () => {
  const configs = ref([])
  const loaded = ref(false)

  const progress = ref({
    running: false,
    currentId: null,
    queuedIds: [],
  })
  let pollTimer = null

  const fetch = async () => {
    configs.value = await request.get('/configs')
    loaded.value = true
    return configs.value
  }

  const loadProgress = async () => {
    const res = await request.get('/configs/progress')
    progress.value = {
      running: res.running,
      currentId: res.currentId,
      queuedIds: res.queuedIds || [],
    }

    if (res.running) {
      if (!pollTimer) {
        pollTimer = setInterval(loadProgress, 2000)
      }
    } else {
      stopPolling()
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
    configs.value = await request.get('/configs')
    loaded.value = true
  }

  /**
   * 原子化更新 progress：将配置加入扫描队列
   * 避免组件层直接修改 progress 导致竞态条件
   */
  const addToQueue = (configId) => {
    if (progress.value.running) {
      progress.value.queuedIds.push(configId)
    } else {
      progress.value.running = true
      progress.value.currentId = configId
      progress.value.queuedIds = []
    }
  }

  const removeFromQueue = (configId) => {
    progress.value.queuedIds = progress.value.queuedIds.filter((id) => id !== configId)
    if (progress.value.currentId === configId) {
      progress.value.currentId = null
      progress.value.running = false
    }
  }

  return {
    configs,
    loaded,
    progress,
    fetch,
    loadProgress,
    startPolling,
    stopPolling,
    refresh,
    addToQueue,
    removeFromQueue,
  }
})
