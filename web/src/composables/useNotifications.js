/**
 * 全局通知 composable - SSE 连接
 * 在 App.vue 中调用 connect() 即可全局订阅通知
 * 结构对齐 migu-scanner
 */
import { onMounted, onUnmounted } from 'vue'
import { toast } from '@/components/Toast'
import { API_BASE } from '@/shared'

let eventSource = null
export const notificationEvent = new EventTarget()

/**
 * 连接到 SSE 事件流（全局只连接一次）
 * payload 结构: {type: "success"/"error"/"info"/"warning", data: {...}, ts: ...}
 * 所有 SSE 事件的 type 统一为消息类型，前端直接按 type 弹 toast
 */
export function connect() {
  if (eventSource) {
    eventSource.close()
  }

  eventSource = new EventSource(API_BASE + '/events')

  eventSource.addEventListener('message', (event) => {
    try {
      const payload = JSON.parse(event.data)
      const type = payload.type || 'info'
      const data = payload.data || {}

      // 按消息类型显示 toast（只展示 title，关键数据由后端折叠进 title）
      if (type === 'success') {
        toast.success(data.title)
      } else if (type === 'error') {
        toast.error(data.title)
      } else {
        toast.notify(data.title || '通知', type)
      }
      // 派发自定义事件，供页面监听刷新（如复测完成刷新 hosts）
      // triggerEvent 为 true 且 source 有值时，以 source 为事件名派发
      if (data?.triggerEvent && data?.source) {
        notificationEvent.dispatchEvent(new CustomEvent(data.source, { detail: { type, data } }))
      }
    } catch {
      // 忽略解析失败
    }
  })

  eventSource.addEventListener('heartbeat', () => {
    // 心跳保持连接
  })

  eventSource.onerror = () => {
    console.warn('[SSE] 连接错误，尝试重连...')
  }
}

/**
 * 断开 SSE 连接
 */
export function disconnect() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

/**
 * 通知监听 composable
 * 用于组件监听特定来源的 SSE 通知事件
 *
 * @param {string} source - 通知来源标识，如 'SCAN_ENGINE'、'SUBSCRIPTION'、'RECHECK'
 * @param {Function} onNotify - 收到通知时的回调函数
 */
export function useNotificationListener(source, onNotify) {
  onMounted(() => {
    notificationEvent.addEventListener(source, onNotify)
  })

  onUnmounted(() => {
    notificationEvent.removeEventListener(source, onNotify)
  })
}
