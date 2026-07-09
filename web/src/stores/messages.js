import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/api'
import { toast } from '@/components/Toast'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export const useMessagesStore = defineStore('messages', () => {
  const messages = ref([])
  const total = ref(0)
  const unreadCount = ref(0)
  const currentPage = ref(1)
  const totalPages = ref(0)

  let eventSource = null

  const connectSSE = () => {
    const token = localStorage.getItem('auth_token')
    if (!token) return

    // 关闭旧连接
    if (eventSource) {
      eventSource.close()
    }

    // EventSource 不支持自定义请求头，用查询参数传 token
    const url = `${API_BASE}/events?token=${token}`
    eventSource = new EventSource(url)

    eventSource.addEventListener('message', (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'notification') {
          const data = payload.data
          // 新消息插入到列表头部
          messages.value.unshift(data)
          total.value++
          unreadCount.value++
          // 通知 Toast（带顶部彩色边框 + 加粗标题，区别于普通操作反馈）
          toast.notify(data.title, data.type || 'info')
        }
      } catch {
        // 忽略解析失败
      }
    })

    eventSource.addEventListener('heartbeat', () => {
      // 心跳保持连接
    })

    // 浏览器 EventSource 自带自动重连，无需手动处理
  }

  const disconnectSSE = () => {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  const fetchMessages = async (page = 1, unreadOnly = false, msgType = null) => {
    const params = { page, page_size: 30 }
    if (unreadOnly) params.unread_only = true
    if (msgType) params.msg_type = msgType

    const res = await request.get('/messages', { params })
    if (page === 1) {
      messages.value = res.items || []
    } else {
      messages.value.push(...(res.items || []))
    }
    total.value = res.total || 0
    currentPage.value = res.page || 1
    totalPages.value = res.totalPages || 0
    unreadCount.value = res.unread || 0
    return res
  }

  const fetchUnreadCount = async () => {
    try {
      const res = await request.get('/messages/unread-count')
      unreadCount.value = res.unread || 0
    } catch {
      // 忽略
    }
  }

  const markRead = async (msgId) => {
    await request.post(`/messages/${msgId}/read`)
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) {
      msg.read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
  }

  const markAllRead = async (msgType = null) => {
    const params = {}
    if (msgType) params.msg_type = msgType
    await request.post('/messages/read-all', null, { params })
    if (msgType) {
      messages.value.forEach(m => { if (m.type === msgType) m.read = true })
    } else {
      messages.value.forEach(m => { m.read = true })
    }
    await fetchUnreadCount()
  }

  const deleteMessage = async (msgId) => {
    await request.delete(`/messages/${msgId}`)
    messages.value = messages.value.filter(m => m.id !== msgId)
    total.value = Math.max(0, total.value - 1)
    const wasUnread = messages.value.find(m => m.id === msgId && !m.read)
    if (wasUnread) {
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    }
  }

  const deleteAllMessages = async (msgType = null, unreadOnly = false) => {
    const params = {}
    if (msgType) params.msg_type = msgType
    if (unreadOnly) params.unread_only = true
    await request.post('/messages/delete-all', null, { params })
    if (msgType) {
      messages.value = messages.value.filter(m => m.type !== msgType)
    } else {
      messages.value = []
    }
    total.value = 0
    currentPage.value = 1
    totalPages.value = 0
    await fetchUnreadCount()
  }

  return {
    messages,
    total,
    unreadCount,
    currentPage,
    totalPages,
    connectSSE,
    disconnectSSE,
    fetchMessages,
    fetchUnreadCount,
    markRead,
    markAllRead,
    deleteMessage,
    deleteAllMessages,
  }
})
