<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">
        <span class="material-symbols-outlined">radar</span>
        <h1>UDPxy Scanner</h1>
      </div>

      <form @submit.prevent="handleLogin">
        <div class="form-item">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="请输入密码" required autocomplete="current-password" />
        </div>

        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

        <button type="submit" class="login-btn" :disabled="submitting">
          {{ submitting ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { toast } from '@/components/Toast'

defineOptions({ name: 'LoginPage' })

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({ password: '' })
const submitting = ref(false)
const errorMsg = ref('')

const handleLogin = async () => {
  submitting.value = true
  errorMsg.value = ''
  try {
    await authStore.login(form.password)
    toast.success('登录成功')
    router.replace('/')
  } catch (e) {
    errorMsg.value = e?.response?.data?.detail || '登录失败，请检查用户名和密码'
    toast.error(errorMsg.value)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-page);
  padding: 16px;
}

.login-card {
  background: var(--bg-card);
  border-radius: 28px;
  padding: 40px 32px 32px;
  width: 100%;
  max-width: 360px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.08);
}

.login-logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-bottom: 32px;
}

.login-logo .material-symbols-outlined {
  font-size: 48px !important;
  color: var(--color-blue);
}

.login-logo h1 {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.form-item label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.form-item input {
  appearance: none;
  -webkit-appearance: none;
  background: var(--bg-neutral);
  border: none;
  outline: none;
  padding: 12px 14px;
  border-radius: var(--radius-input);
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
  width: 100%;
  box-sizing: border-box;
  transition: all 0.15s ease;
}

.form-item input:focus {
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.1);
}

.form-item input::placeholder {
  color: var(--text-disabled);
}

.error-msg {
  font-size: 13px;
  color: var(--color-red);
  text-align: center;
  margin: 0 0 8px;
}

.login-btn {
  width: 100%;
  padding: 14px;
  border: none;
  border-radius: var(--radius-btn);
  background: var(--color-blue);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: 8px;
}

.login-btn:active {
  transform: scale(0.98);
  background: #0066D6;
}

.login-btn:disabled {
  opacity: 0.6;
  pointer-events: none;
}
</style>
