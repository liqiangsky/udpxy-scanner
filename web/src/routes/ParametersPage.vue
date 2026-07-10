<template>
  <div class="page-container">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">
        <span class="material-symbols-outlined">arrow_back</span>
      </button>
      <h1 class="page-title">参数管理</h1>
      <button class="header-icon-btn" @click="handleSave" :class="{ fetching: saving }">
        <span class="material-symbols-outlined">save</span>
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
            Cron 表达式：分 时 日 月 周。留空不执行。统一调度所有订阅源扫描。
          </p>
        </div>

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
      </div>

      <!-- 推送 API Key -->
      <div class="settings-card">
        <div class="card-title-group">
          <span class="material-symbols-outlined card-icon">vpn_key</span>
          <h2>推送 API Key</h2>
        </div>

        <div class="form-group">
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
          <button
            type="button"
            class="fetch-btn-mini"
            style="margin-top: 8px"
            @click="generateApiKey"
          >
            <span class="material-symbols-outlined fetch-icon">refresh</span>
            <span>生成随机 Key</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { toast } from '@/components/Toast'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()

const settings = reactive({
  engine: { concurrency: 64, timeout: 2000, configDelay: 3 },
  scheduling: { scanCron: '', janitorCron: '' },
  pushApiKey: '',
})

const saving = ref(false)
const loadSettings = async () => {
  const res = await settingsStore.fetch()
  if (res.engine) Object.assign(settings.engine, res.engine)
  if (res.scheduling) Object.assign(settings.scheduling, res.scheduling)
  if (res.pushApiKey !== undefined) settings.pushApiKey = res.pushApiKey
}

const handleSave = async () => {
  saving.value = true
  try {
    const payload = {
      concurrency: settings.engine.concurrency,
      timeout: settings.engine.timeout,
      configDelay: settings.engine.configDelay,
      scanCron: (settings.scheduling.scanCron || '').trim(),
      janitorCron: (settings.scheduling.janitorCron || '').trim(),
      pushApiKey: (settings.pushApiKey || '').trim(),
    }
    await settingsStore.update(payload)
    toast.success('已保存')
  } catch (e) {
    console.error('保存失败:', e)
  } finally {
    saving.value = false
  }
}

const generateApiKey = () => {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  const array = new Uint8Array(32)
  crypto.getRandomValues(array)
  const key = Array.from(array, (b) => chars[b % chars.length]).join('')
  settings.pushApiKey = key
  toast.success('已生成新 Key，请保存')
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
  align-items: center;
  gap: 8px;
  max-width: 100vw;
}
@media (min-width: 768px) {
  .page-header {
    max-width: 720px;
    margin-left: auto;
    margin-right: auto;
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

.page-title {
  flex: 1;
  text-align: left;
  font-size: 18px;
  font-weight: 700;
  margin: 0;
}

.settings-flow {
  width: 100%;
  max-width: var(--max-content);
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
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

.header-icon-btn {
  background: var(--color-blue);
  border: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.header-icon-btn .material-symbols-outlined {
  font-size: 18px !important;
  color: #fff;
}
.header-icon-btn:active {
  transform: scale(0.9);
  background: #0066d6;
}
.header-icon-btn.fetching {
  opacity: 0.5;
  pointer-events: none;
}

.form-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.input-with-unit {
  display: flex;
  align-items: center;
  gap: 4px;
}

.input-with-unit input {
  flex: 1;
}

.unit-text {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.input-with-icon {
  display: flex;
  align-items: center;
  gap: 8px;
}

.input-with-icon .input-base {
  flex: 1;
}

.input-prefix {
  font-size: 20px !important;
  color: var(--text-muted);
}
</style>
