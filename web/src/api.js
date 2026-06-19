import axios from 'axios'
import { toast } from '@/components/Toast'
import { useAuthStore } from '@/stores/auth'

// 运行时 API 基础地址：优先取 VITE_API_BASE，默认 /api（同域代理）
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const request = axios.create({
  baseURL: API_BASE,
  timeout: 15000
})

// 请求拦截器：每次请求自动带上认证 token
request.interceptors.request.use((config) => {
  const authToken = localStorage.getItem('auth_token')
  if (authToken) {
    config.headers['X-Auth-Token'] = authToken
  }
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    // 未认证 → 清除状态并跳转登录
    if (status === 401 || status === 403) {
      const authStore = useAuthStore()
      const hadToken = !!localStorage.getItem('auth_token')
      authStore.isLoggedIn = false
      localStorage.removeItem('auth_token')
      if (hadToken) {
        toast.error('登录已过期，请重新登录')
      }
      const currentPath = window.location.pathname
      const redirect = currentPath !== '/login' ? currentPath : ''
      window.location.href = redirect ? `/login?redirect=${encodeURIComponent(redirect)}` : '/login'
      return Promise.reject(error)
    }
    const msg = error.response?.data?.detail || error.message || '请求失败'
    toast.error(msg)
    console.error('API 请求失败:', error)
    return Promise.reject(error)
  }
)

export default request
