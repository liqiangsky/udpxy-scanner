import axios from 'axios'
import { toast } from '@/components/Toast'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

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
  (response) => {
    const body = response.data
    if (body.code !== 200) {
      if (body.code === 401) {
        const authStore = useAuthStore()
        authStore.clearSession()
        toast.error('登录已过期，请重新登录')
        const currentPath = window.location.pathname
        const redirect = currentPath !== '/login' ? currentPath : ''
        setTimeout(() => {
          router.push(redirect ? `/login?redirect=${encodeURIComponent(redirect)}` : '/login')
        }, 1500)
      } else {
        toast.error(body.msg || '请求失败')
        console.error('API 请求失败:', body)
      }
      return Promise.reject(body)
    }
    return body.data
  },
  (error) => {
    // 网络错误或 HTTP 非 200（理论上不会发生，保底）
    const msg = error.message || '网络错误'
    toast.error(msg)
    console.error('请求异常:', error)
    return Promise.reject(error)
  },
)

export default request
