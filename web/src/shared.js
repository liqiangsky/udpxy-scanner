import { ref } from 'vue'

/**
 * API 基础路径
 * 优先级：运行时注入（Docker env.sh）> 编译时注入（CF Pages）> 默认 ''
 * 最终结果会自动追加 /api 后缀
 */
export const API_BASE = (window.__ENV__?.VITE_BACKEND_URL || import.meta.env.VITE_BACKEND_URL || '') + '/api'

/** 主机页面批量选择模式是否激活 */
export const batchSelectActive = ref(false)

/** 复制文本到剪贴板，兼容 HTTPS 和 HTTP */
export async function copyToClipboard(text) {
  // 方式 1: 现代 Clipboard API（需要 HTTPS 或 localhost）
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // fallthrough
    }
  }

  // 方式 2: 传统 document.execCommand('copy')（兼容 HTTP 和旧浏览器）
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  textarea.style.pointerEvents = 'none'
  document.body.appendChild(textarea)
  try {
    textarea.select()
    document.execCommand('copy')
    return true
  } catch {
    return false
  } finally {
    document.body.removeChild(textarea)
  }
}

/**
 * 格式化毫秒级时间戳 → YYYY-MM-DD HH:mm:ss
 * @param {number|string|null|undefined} ts - 毫秒级时间戳
 * @param {string} [fallback='--'] - 无效时的回退文字
 * @returns {string}
 */
export function formatTime(ts, fallback = '--') {
  if (ts === null || ts === undefined || ts === 0 || ts === '0' || ts === '') return fallback
  const n = Number(ts)
  if (isNaN(n) || n <= 0) return fallback
  const d = new Date(n < 1e12 ? n * 1000 : n)
  if (isNaN(d)) return fallback
  const pad = (v) => String(v).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
