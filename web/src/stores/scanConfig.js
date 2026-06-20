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
    if (loaded.value) return configs.value
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

  return {
    configs,
    loaded,
    progress,
    fetch,
    loadProgress,
    startPolling,
    stopPolling,
    refresh,
  }
})
