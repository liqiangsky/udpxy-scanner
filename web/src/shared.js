import { ref } from 'vue'

/** 主机页面批量选择模式是否激活 */
export const batchSelectActive = ref(false)

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
