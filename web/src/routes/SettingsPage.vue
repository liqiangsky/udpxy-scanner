<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">设置</h1>
    </div>

    <div class="header-spacer"></div>

    <div class="settings-flow">
      <!-- 修改密码 -->
      <div class="settings-card">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">lock</span>
          <h2>修改密码</h2>
        </div>

        <div class="form-group">
          <input
            v-model="passwordForm.oldPassword"
            type="password"
            class="input-base"
            placeholder="当前密码"
          />
          <input
            v-model="passwordForm.newPassword"
            type="password"
            class="input-base"
            style="margin-top: 8px"
            placeholder="新密码（至少 4 位）"
          />
          <button
            type="button"
            class="fetch-btn-mini"
            style="margin-top: 8px"
            :class="{ fetching: changingPassword }"
            @click="handleChangePassword"
          >
            <span class="material-symbols-outlined fetch-icon">key</span>
            <span>{{ changingPassword ? '修改中...' : '修改密码' }}</span>
          </button>
        </div>
      </div>

      <!-- 参数管理入口 -->
      <div class="settings-card entry-card" @click="$router.push('/settings/params')">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">tune</span>
          <h2>参数管理</h2>
          <span class="material-symbols-outlined entry-arrow">chevron_right</span>
        </div>
        <p class="field-desc">扫描引擎参数、自动化调度、推送 API Key</p>
      </div>

      <!-- 游离主机入口 -->
      <div class="settings-card entry-card" @click="$router.push('/settings/orphans')">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon" style="color: var(--color-orange)"
            >broadcast_on_personal</span
          >
          <h2>游离主机</h2>
          <span class="material-symbols-outlined entry-arrow" style="color: var(--color-orange)"
            >chevron_right</span
          >
        </div>
        <p class="field-desc">管理已不在主机池中的缓存主机</p>
      </div>

      <!-- 通知入口 -->
      <div class="settings-card entry-card" @click="$router.push('/settings/notifications')">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon" style="color: var(--color-blue)"
            >notifications</span
          >
          <h2>通知</h2>
          <span v-if="msgStore.unreadCount > 0" class="unread-badge">{{
            msgStore.unreadCount
          }}</span>
          <span class="material-symbols-outlined entry-arrow" style="color: var(--color-blue)"
            >chevron_right</span
          >
        </div>
        <p class="field-desc">扫描完成、复测结果、订阅拉取等系统通知</p>
      </div>

      <!-- 后台日志入口 -->
      <div class="settings-card entry-card" @click="$router.push('/logs')">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">receipt_long</span>
          <h2>后台日志</h2>
          <span class="material-symbols-outlined entry-arrow">chevron_right</span>
        </div>
        <p class="field-desc">查看实时运行日志</p>
      </div>

      <!-- Cron 表达式帮助 -->
      <div class="settings-card">
        <details class="cron-help-details">
          <summary class="cron-help-summary">
            <div class="card-title-group">
              <span class="material-symbols-outlined card-icon" style="color: var(--color-orange)">schedule</span>
              <h2>Cron 表达式帮助</h2>
              <span class="material-symbols-outlined expand-icon">expand_more</span>
            </div>
          </summary>
          <div class="help-content">
            <p><b>格式</b>：分 时 日 月 周（5 个字段，空格分隔）</p>
            <p><b>取值范围</b>：</p>
            <table>
              <tr><td>分</td><td>0-59</td></tr>
              <tr><td>时</td><td>0-23</td></tr>
              <tr><td>日</td><td>1-31</td></tr>
              <tr><td>月</td><td>1-12</td></tr>
              <tr><td>周</td><td>1-7（1=周一，7=周日）</td></tr>
            </table>
            <p><b>常用符号</b>：</p>
            <p><code>*</code> 任意值 &nbsp; <code>/</code> 步长如 <code>*/10</code> 每10分钟</p>
            <p><code>-</code> 范围如 <code>9-17</code> &nbsp; <code>,</code> 多个值如 <code>8,12,18</code></p>
            <p><b>常用示例</b>：</p>
            <p><code>* * * * *</code> → 每分钟</p>
            <p><code>*/30 * * * *</code> → 每 30 分钟</p>
            <p><code>0 2 * * *</code> → 每天凌晨 2:00</p>
            <p><code>0 */4 * * *</code> → 每 4 小时整点</p>
            <p><code>0 9 * * 1-5</code> → 工作日 9:00</p>
            <p><code>1 * * * *</code> → 每小时第1分钟</p>
          </div>
        </details>
      </div>

      <!-- 退出登录 -->
      <div class="settings-card logout-card" @click="handleLogout">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon" style="color: var(--color-red)"
            >logout</span
          >
          <h2 style="color: var(--color-red)">退出登录</h2>
          <span class="material-symbols-outlined entry-arrow" style="color: var(--color-red)"
            >chevron_right</span
          >
        </div>
        <p class="field-desc">退出当前账号，返回登录页面</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from '@/components/Toast'
import { useAuthStore } from '@/stores/auth'
import { useMessagesStore } from '@/stores/messages'
import request from '@/api'

const router = useRouter()
const authStore = useAuthStore()
const msgStore = useMessagesStore()

onMounted(() => {
  msgStore.fetchUnreadCount()
})

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
})
const changingPassword = ref(false)

const handleChangePassword = async () => {
  if (!passwordForm.oldPassword || !passwordForm.newPassword) {
    toast.warning('请填写新旧密码')
    return
  }
  if (passwordForm.newPassword.length < 4) {
    toast.warning('密码至少 4 位')
    return
  }
  changingPassword.value = true
  try {
    await request.post('/change-password', {
      oldPassword: passwordForm.oldPassword.trim(),
      newPassword: passwordForm.newPassword.trim(),
    })
    toast.success('密码已修改，需重新登录')
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    authStore.clearSession()
    router.push('/login')
  } catch {
    /* 错误由拦截器统一提示 */
  } finally {
    changingPassword.value = false
  }
}

const handleLogout = async () => {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.page-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  background: rgba(245, 245, 247, 0.92);
  backdrop-filter: blur(20px);
  padding: 12px 16px;
  min-height: 58px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 100vw;
}

@media (min-width: 768px) {
  .page-header {
    max-width: 720px;
    left: 50%;
    transform: translateX(-50%);
  }
}
@media (min-width: 1024px) {
  .page-header {
    max-width: 1100px;
  }
}
@media (min-width: 1440px) {
  .page-header {
    max-width: 1400px;
  }
}

.settings-flow {
  width: 100%;
  max-width: var(--max-content);
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  padding-bottom: 70px;
}

@media (min-width: 768px) {
  .settings-flow {
    max-width: 720px;
    grid-template-columns: 1fr 1fr;
  }
}
@media (min-width: 1024px) {
  .settings-flow {
    max-width: 1100px;
    grid-template-columns: 1fr 1fr 1fr;
  }
}
@media (min-width: 1440px) {
  .settings-flow {
    max-width: 1400px;
    grid-template-columns: 1fr 1fr 1fr;
  }
}

/* 入口卡片（参数管理、后台日志） */
.entry-card {
  cursor: pointer;
  transition: all 0.2s ease;
}
.entry-card:active {
  transform: scale(0.98);
}

/* 退出登录卡片 */
.logout-card {
  cursor: pointer;
  transition: all 0.2s ease;
  border-color: rgba(255, 59, 48, 0.2) !important;
}
.logout-card:active {
  transform: scale(0.98);
}

.entry-arrow {
  margin-left: auto;
  font-size: 22px !important;
  color: var(--text-muted);
}

.unread-badge {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: var(--color-red);
  color: #fff;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 700;
  line-height: 20px;
  text-align: center;
  font-family: var(--font-sans);
}

.cron-help-details {
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.cron-help-details[open] .expand-icon {
  transform: rotate(180deg);
}
.cron-help-summary {
  list-style: none;
  display: block;
}
.cron-help-summary::-webkit-details-marker {
  display: none;
}
.cron-help-summary::marker {
  display: none;
  content: '';
}
.expand-icon {
  margin-left: auto;
  font-size: 22px !important;
  color: var(--text-muted);
  transition: transform 0.3s ease;
}

.help-content {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin-top: 8px;
  padding: 12px 14px;
  background: var(--bg-neutral);
  border-radius: var(--radius-input);
}
.help-content p {
  margin: 6px 0;
}
.help-content code {
  background: #e8e8ed;
  padding: 2px 7px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
}
.help-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 6px 0;
  font-size: 12px;
}
.help-content td {
  padding: 4px 10px;
  border-bottom: 1px solid #e8e8ed;
}
.help-content td:first-child {
  font-weight: 600;
  color: var(--text-primary);
}
</style>
