import axios from 'axios'
import { toast } from '@/components/Toast'
import { useAuthStore } from '@/stores/auth'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

const request = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
})

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
    if (status === 401) {
      const authStore = useAuthStore()
      authStore._doLogout()
      toast.error('登录已过期，请重新登录')
      const currentPath = window.location.pathname
      const redirect = currentPath !== '/login' ? currentPath : ''
      window.location.href = redirect ? `/login?redirect=${encodeURIComponent(redirect)}` : '/login'
      return Promise.reject(error)
    }
    const msg = error.response?.data?.detail || error.message || '请求失败'
    toast.error(msg)
    console.error('API 请求失败:', error)
    return Promise.reject(error)
  },
)

export default request
