<template>
  <div class="not-found">
    <div class="not-found-card">
      <h1 class="code">404</h1>
      <p class="msg">页面不存在</p>
      <router-link to="/" class="back-btn">返回首页</router-link>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.not-found {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-page);
}

.not-found-card {
  text-align: center;
}

.code {
  font-size: 72px;
  font-weight: 800;
  color: var(--color-blue);
  margin: 0;
  line-height: 1;
}

.msg {
  font-size: 16px;
  color: var(--text-muted);
  margin: 12px 0 24px;
}

.back-btn {
  display: inline-block;
  background: var(--color-blue);
  color: #fff;
  text-decoration: none;
  padding: 10px 28px;
  border-radius: var(--radius-btn);
  font-size: 14px;
  font-weight: 600;
  transition: all 0.2s ease;
}

.back-btn:active {
  transform: scale(0.96);
  background: #0066D6;
}
</style>
