<template>
  <router-view />

  <nav class="bottom-tabbar" v-if="showTabbar">
    <router-link to="/hosts" class="tab-item" active-class="active" exact-active-class="active">
      <span class="material-symbols-outlined tab-icon">tv</span>
      <span class="tab-text">主机</span>
    </router-link>

    <router-link to="/scans" class="tab-item" active-class="active">
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
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useMessagesStore } from '@/stores/messages'
import { batchSelectActive } from '@/shared'

const route = useRoute()
const authStore = useAuthStore()
const msgStore = useMessagesStore()

onMounted(() => {
  if (authStore.isLoggedIn) {
    msgStore.connectSSE()
    msgStore.fetchUnreadCount()
  }
})

watch(
  () => authStore.isLoggedIn,
  (loggedIn) => {
    if (loggedIn) {
      msgStore.connectSSE()
      msgStore.fetchUnreadCount()
    } else {
      msgStore.disconnectSSE()
    }
  },
)

const showTabbar = computed(() => {
  return (
    authStore.isLoggedIn &&
    !route.meta?.hideNavbar &&
    route.path !== '/login' &&
    !batchSelectActive.value
  )
})
</script>
