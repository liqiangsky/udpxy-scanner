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
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { batchSelectActive } from '@/shared'
import { connect, disconnect } from '@/composables/useNotifications'

const route = useRoute()

onMounted(() => {
  // 全局 SSE 连接（只连接一次）
  connect()
})

onUnmounted(() => {
  disconnect()
})

const showTabbar = computed(() => {
  return (
    !route.meta?.hideNavbar &&
    !batchSelectActive.value
  )
})
</script>
