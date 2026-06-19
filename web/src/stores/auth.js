import { defineStore } from 'pinia'
import { ref } from 'vue'
import request from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const isLoggedIn = ref(false)

  const _doLogout = () => {
    isLoggedIn.value = false
    localStorage.removeItem('auth_token')
  }

  const init = async () => {
    const savedToken = localStorage.getItem('auth_token')
    if (!savedToken) {
      _doLogout();
      return;
    }
    try {
      const res = await request.get('/auth', { params: { token: savedToken } })
      if (res.valid) {
        isLoggedIn.value = true
      } else {
        _doLogout()
      }
    } catch {
      _doLogout()
    }
  }

  const login = async (pass) => {
    const res = await request.post('/login', { password: pass })
    isLoggedIn.value = true
    localStorage.setItem('auth_token', res.token)
    return res
  }

  const logout = async () => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      await request.post('/logout', { token })
    }
    _doLogout()
  }


  return { isLoggedIn, _doLogout, init, login, logout }
})
