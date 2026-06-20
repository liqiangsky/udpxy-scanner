<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">全局设置</h1>
      <button class="save-btn" @click="handleSave">
        <span class="material-symbols-outlined save-btn-icon">save</span>
        <span>{{ saving ? '保存中...' : '保存' }}</span>
      </button>
    </div>

    <div class="header-spacer"></div>

    <div class="settings-flow">
      <!-- 扫描引擎参数 -->
      <div class="settings-card">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">speed</span>
          <h2>扫描引擎参数</h2>
        </div>

        <div class="form-grid-2">
          <div class="form-group">
            <label>并发验证数</label>
            <div class="input-with-unit">
              <input v-model.number="settings.engine.concurrency" type="number" min="1" max="500" />
              <span class="unit-text">线程</span>
            </div>
          </div>

          <div class="form-group">
            <label>连接超时</label>
            <div class="input-with-unit">
              <input
                v-model.number="settings.engine.timeout"
                type="number"
                min="200"
                max="10000"
                step="100"
              />
              <span class="unit-text">ms</span>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>配置间延迟 (Delay)</label>
          <div class="input-with-unit">
            <input v-model.number="settings.engine.configDelay" type="number" min="0" max="300" />
            <span class="unit-text">秒</span>
          </div>
          <p class="field-desc">上一个扫描配置结束后，队列进入下一个配置前的等待缓冲时间。</p>
        </div>
      </div>

      <!-- 自动化调度 -->
      <div class="settings-card">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">schedule</span>
          <h2>自动化调度</h2>
        </div>

        <div class="form-group">
          <label>定时扫描 (Cron)</label>
          <input
            v-model="settings.scheduling.scanCron"
            type="text"
            class="input-base"
            placeholder="留空表示不执行"
          />
          <p class="field-desc">
            Cron 表达式：分 时 日 月 周。留空不执行。统一调度所有数据源扫描。
          </p>
        </div>

        <button
          type="button"
          class="fetch-btn-mini"
          :class="{ fetching: scanning }"
          @click="handleScan"
        >
          <span class="material-symbols-outlined fetch-icon" :class="{ spin: scanning }"
            >search</span
          >
          <span>{{ scanning ? '扫描中...' : '手动扫描' }}</span>
        </button>

        <div class="form-group">
          <label>定时复测 (Cron)</label>
          <input
            v-model="settings.scheduling.janitorCron"
            type="text"
            class="input-base"
            placeholder="留空表示不执行"
          />
          <p class="field-desc">Cron 表达式：分 时 日 月 周。留空不执行。</p>
        </div>

        <button
          type="button"
          class="fetch-btn-mini"
          @click="handleRecheck"
          :class="{ fetching: rechecking }"
        >
          <span class="material-symbols-outlined fetch-icon" :class="{ spin: rechecking }"
            >autorenew</span
          >
          <span>{{ rechecking ? '复测中...' : '手动复测' }}</span>
        </button>

        <div class="cron-help">
          <details>
            <summary>📖 Cron 表达式帮助</summary>
            <div class="help-content">
              <p><b>格式</b>：分 时 日 月 周（5 个字段，空格分隔）</p>
              <p><b>取值范围</b>：</p>
              <table>
                <tbody>
                  <tr>
                    <td>分</td>
                    <td>0-59</td>
                  </tr>
                  <tr>
                    <td>时</td>
                    <td>0-23</td>
                  </tr>
                  <tr>
                    <td>日</td>
                    <td>1-31</td>
                  </tr>
                  <tr>
                    <td>月</td>
                    <td>1-12</td>
                  </tr>
                  <tr>
                    <td>周</td>
                    <td>1-7（1=周一，7=周日）</td>
                  </tr>
                </tbody>
              </table>
              <p><b>常用符号</b>：</p>
              <p><code>*</code> 表示任意值</p>
              <p><code>/</code> 表示步长，如 <code>*/10</code> 表示每 10 分钟</p>
              <p><code>-</code> 表示范围，如 <code>9-17</code> 表示 9 到 17 点</p>
              <p><code>,</code> 表示多个值，如 <code>8,12,18</code> 表示 8、12、18 点</p>
              <p><b>常用示例</b>：</p>
              <p><code>0 2 * * *</code> → 每天凌晨 2:00</p>
              <p><code>*/30 * * * *</code> → 每 30 分钟</p>
              <p><code>0 */4 * * *</code> → 每 4 小时整点</p>
              <p><code>0 9 * * 1-5</code> → 工作日 9:00</p>
              <p><code>0 3 * * 1</code> → 每周一 3:00</p>
            </div>
          </details>
        </div>
      </div>

      <!-- 安全设置 -->
      <div class="settings-card">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">lock</span>
          <h2>安全设置</h2>
        </div>

        <div class="form-group">
          <label>修改密码</label>
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

        <div class="form-group">
          <label>推送 API Key</label>
          <div class="input-with-icon">
            <span class="material-symbols-outlined input-prefix">vpn_key</span>
            <input
              v-model="settings.pushApiKey"
              type="text"
              class="input-base"
              placeholder="留空则不生成"
            />
          </div>
          <p class="field-desc">
            外部服务调用 <code>/api/source/push</code> 时需携带
            <code>X-API-Key</code> 头部。留空则禁用推送接口。
          </p>
          <button type="button" class="fetch-btn-mini" @click="generateApiKey">
            <span class="material-symbols-outlined fetch-icon">refresh</span>
            <span>生成随机 Key</span>
          </button>
        </div>
      </div>

      <!-- 后台日志入口 -->
      <div class="settings-card logs-entry-card" @click="$router.push('/logs')">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">receipt_long</span>
          <h2>后台日志</h2>
          <span class="material-symbols-outlined entry-arrow">chevron_right</span>
        </div>
        <p class="field-desc">查看实时运行日志，支持按级别筛选</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { toast } from '@/components/Toast'
import { useSettingsStore } from '@/stores/settings'
import request from '@/api'

const settingsStore = useSettingsStore()

// ===== 设置 =====
const settings = reactive({
  engine: { concurrency: 64, timeout: 2000, configDelay: 3 },
  scheduling: { scanCron: '', janitorCron: '' },
  pushApiKey: '',
})

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
})
const changingPassword = ref(false)

const saving = ref(false)

const loadSettings = async () => {
  const res = await settingsStore.fetch()
  if (res.engine) Object.assign(settings.engine, res.engine)
  if (res.scheduling) Object.assign(settings.scheduling, res.scheduling)
  if (res.pushApiKey !== undefined) settings.pushApiKey = res.pushApiKey
}

const handleChangePassword = async () => {
  if (!passwordForm.oldPassword || !passwordForm.newPassword) {
    toast.warning('请填写当前密码和新密码')
    return
  }
  if (passwordForm.newPassword.length < 4) {
    toast.warning('新密码至少 4 位')
    return
  }
  changingPassword.value = true
  try {
    await request.post('/change-password', {
      oldPassword: passwordForm.oldPassword,
      newPassword: passwordForm.newPassword,
    })
    toast.success('密码已修改，请重新登录')
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    setTimeout(() => {
      window.location.href = '/login'
    }, 1500)
  } catch (e) {
    toast.error(e?.response?.data?.detail || '修改失败')
  } finally {
    changingPassword.value = false
  }
}

const generateApiKey = () => {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  const key = Array.from(
    { length: 32 },
    () => chars[Math.floor(Math.random() * chars.length)],
  ).join('')
  settings.pushApiKey = key
  toast.success('已生成新 API Key，记得保存')
}

const scanning = ref(false)

const handleScan = async () => {
  scanning.value = true
  try {
    await request.post('/configs/run-all')
    toast.success('扫描任务已触发')
  } catch (e) {
    toast.error(e?.response?.data?.detail || '扫描触发失败')
  } finally {
    scanning.value = false
  }
}

const rechecking = ref(false)

const handleRecheck = async () => {
  rechecking.value = true
  try {
    await request.post('/cron/recheck')
    toast.success('复测任务已在后台启动')
  } catch (e) {
    toast.error(e?.response?.data?.detail || '复测失败')
  } finally {
    rechecking.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    const payload = {
      concurrency: settings.engine.concurrency,
      timeout: settings.engine.timeout,
      configDelay: settings.engine.configDelay,
      scanCron: settings.scheduling.scanCron,
      janitorCron: settings.scheduling.janitorCron,
      pushApiKey: settings.pushApiKey,
    }
    await settingsStore.update(payload)
    toast.success('设置已保存')
  } catch (e) {
    console.error('保存失败:', e)
    toast.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSettings()
})
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
.header-spacer {
  height: 48px;
  flex-shrink: 0;
}
.settings-flow {
  width: 100%;
  max-width: var(--max-content);
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  padding-bottom: 90px;
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

.settings-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 20px;
  box-shadow: var(--shadow-md);
  border: 1px solid rgba(0, 0, 0, 0.01);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 1px solid var(--bg-neutral);
  padding-bottom: 10px;
}
.card-icon {
  font-size: 18px !important;
  color: var(--color-blue);
  font-variation-settings:
    'FILL' 0,
    'wght' 500;
}
.card-title-group h2 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.field-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
  padding-left: 2px;
}

.textarea-input {
  font-family: var(--font-mono);
  font-size: 12px;
  resize: vertical;
  line-height: 1.6;
  padding: 8px 12px;
}

.save-btn {
  background: var(--color-blue);
  color: #ffffff;
  border: none;
  padding: 6px 12px;
  border-radius: var(--radius-btn);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: all 0.2s ease;
  -webkit-tap-highlight-color: transparent;
}
.save-btn:active {
  transform: scale(0.96);
  background: #0066d6;
}
.save-btn-icon {
  font-size: 16px !important;
  font-variation-settings:
    'FILL' 0,
    'wght' 600,
    'GRAD' 0,
    'opsz' 24;
}

.fetch-btn-mini {
  background: var(--color-blue);
  color: #fff;
  border: none;
  padding: 8px 14px;
  border-radius: var(--radius-input);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
  transition: all 0.2s ease;
  -webkit-tap-highlight-color: transparent;
}
.fetch-btn-mini:active {
  transform: scale(0.96);
  background: #0066d6;
}
.fetch-btn-mini.fetching {
  opacity: 0.6;
  pointer-events: none;
}
.fetch-icon {
  font-size: 16px !important;
  font-variation-settings:
    'FILL' 0,
    'wght' 400,
    'GRAD' 0,
    'opsz' 20;
}
.spin {
  animation: spin 1s linear infinite;
}

.cron-help {
  margin-top: 4px;
}
.cron-help summary {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-blue);
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.help-content {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--bg-neutral);
  border-radius: var(--radius-input);
}
.help-content p {
  margin: 4px 0;
}
.help-content code {
  background: #e8e8ed;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
}
.help-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 6px 0;
}
.help-content td {
  padding: 3px 8px;
  border-bottom: 1px solid #e8e8ed;
}
.help-content td:first-child {
  font-weight: 600;
  color: var(--text-primary);
}

/* 日志入口卡片 */
.logs-entry-card {
  cursor: pointer;
  transition: all 0.2s ease;
}
.logs-entry-card:active {
  transform: scale(0.98);
}
.entry-arrow {
  margin-left: auto;
  font-size: 22px !important;
  color: var(--text-muted);
}
</style>
