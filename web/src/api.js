import axios from 'axios'
import { toast } from '@/components/Toast'
import { API_BASE } from '@/shared'

const request = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
})

request.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body.code !== 200) {
      toast.error(body.msg || '请求失败')
      console.error('API 请求失败:', body)
      return Promise.reject(body)
    }
    return body.data
  },
  (error) => {
    const msg = error.message || '网络错误'
    toast.error(msg)
    console.error('请求异常:', error)
    return Promise.reject(error)
  },
)

export default request
