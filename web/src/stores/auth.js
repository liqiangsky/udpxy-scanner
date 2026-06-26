import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const isLoggedIn = ref(false)

  const savedToken = localStorage.getItem('auth_token')
  if (savedToken) {
    isLoggedIn.value = true
  }

  const clearSession = () => {
    isLoggedIn.value = false
    localStorage.removeItem('auth_token')
  }

  const login = async (pass) => {
    const res = await request.post('/login', { password: pass })
    isLoggedIn.value = true
    localStorage.setItem('auth_token', res.token)
    return res
  }

  const logout = async () => {
    try {
      const token = localStorage.getItem('auth_token')
      if (token) {
        await request.post('/logout', { token })
      }
    } catch {
    }
    clearSession()
  }

  return { isLoggedIn, clearSession, login, logout }
})
