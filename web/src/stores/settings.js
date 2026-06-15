import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/api'

export const useSettingsStore = defineStore('settings', () => {
  const data = ref(null)
  const loaded = ref(false)

  const fetch = async (force = false) => {
    if (!force && loaded.value) return data.value
    const res = await request.get('/settings')
    data.value = res
    loaded.value = true
    return res
  }

  const update = async (payload) => {
    await request.put('/settings', payload)
    if (!data.value) return data.value
    if (payload.concurrency !== undefined) data.value.engine.concurrency = payload.concurrency
    if (payload.timeout !== undefined) data.value.engine.timeout = payload.timeout
    if (payload.configDelay !== undefined) data.value.engine.configDelay = payload.configDelay
    if (payload.scanCron !== undefined) data.value.scheduling.scanCron = payload.scanCron
    if (payload.janitorCron !== undefined) data.value.scheduling.janitorCron = payload.janitorCron
    if (payload.pushApiKey !== undefined) data.value.pushApiKey = payload.pushApiKey
    return data.value
  }

  return { data, loaded, fetch, update }
})