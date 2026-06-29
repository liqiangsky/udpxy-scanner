<template>
  <router-view />

  <nav class="bottom-tabbar" v-if="showTabbar">
    <router-link to="/hosts" class="tab-item" active-class="active" exact-active-class="active">
      <span class="material-symbols-outlined tab-icon">tv</span>
      <span class="tab-text">主机</span>
    </router-link>

    <router-link to="/scan" class="tab-item" active-class="active">
      <span class="material-symbols-outlined tab-icon">analytics</span>
      <span class="tab-text">扫描</span>
    </router-link>

    <router-link to="/subscriptions" class="tab-item" active-class="active">
      <span class="material-symbols-outlined tab-icon">rss_feed</span>
      <span class="tab-text">订阅</span>
    </router-link>

    <router-link to="/settings" class="tab-item" active-class="active">
      <span class="material-symbols-outlined tab-icon">settings</span>
      <span class="tab-text">设置</span>
    </router-link>
  </nav>

  <!-- 未登录时的登录按钮 -->
  <button v-if="showLoginBtn" class="floating-login" @click="$router.push('/login')">
    <span class="material-symbols-outlined">login</span>
    <span>登录</span>
  </button>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { batchSelectActive } from '@/shared'

const route = useRoute()
const authStore = useAuthStore()

const showTabbar = computed(() => {
  return authStore.isLoggedIn && !route.meta?.hideNavbar && route.path !== '/login' && !batchSelectActive.value
})

const showLoginBtn = computed(() => {
  return !authStore.isLoggedIn && route.path !== '/login'
})
</script>

<style scoped>
.floating-login {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-blue);
  color: #fff;
  border: none;
  border-radius: 28px;
  padding: 14px 32px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 8px 32px rgba(0, 122, 255, 0.3);
  transition: all 0.2s ease;
  z-index: 99;
}

.floating-login:active {
  transform: translateX(-50%) scale(0.96);
}

.floating-login .material-symbols-outlined {
  font-size: 20px !important;
}
</style>
