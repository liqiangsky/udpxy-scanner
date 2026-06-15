<template>
  <div v-if="item" class="iptv-grid-card">

    <div class="section-host">
      <div class="host-ip font-mono">{{ item.host }}</div>
      <div class="host-actions">
        <button v-if="isAuthenticated" class="action-btn delete-btn" @click.stop="$emit('delete', item)">
          <span class="material-symbols-outlined icon-g">delete</span>
        </button>
        <button class="copy-btn" @click.stop="$emit('copy', item.host)">
          <span class="material-symbols-outlined icon-g">content_copy</span>
        </button>
      </div>
    </div>

    <div class="section-metrics-grid">
      <div class="grid-item">
        <span class="badge-lbl">地区</span>
        <span class="badge-txt color-blue">{{ item.region }}</span>
      </div>

      <div class="grid-item">
        <span class="badge-lbl">运营商</span>
        <span class="badge-txt color-blue">{{ item.operator }}</span>
      </div>

      <div class="grid-item">
        <span class="badge-lbl">延迟</span>
        <div class="delay-interactive-badge" :class="{ 'state-error': item.delay < 0 }" @click.stop="$emit('test', item)">
          <span class="material-symbols-outlined icon-g">bolt</span>
          <span class="badge-txt font-mono">{{ item.delay }} ms</span>
        </div>
      </div>

      <div class="grid-item">
        <span class="badge-lbl">来源</span>
        <span class="badge-txt">{{ item.sourceName }}</span>
      </div>

      <div class="grid-item time-column full-width">
        <span class="badge-lbl">发现</span>
        <div class="time-wrapper">
          <span class="material-symbols-outlined icon-g">history</span>
          <span class="badge-txt color-gray font-mono">{{ item.createTime }}</span>
        </div>
      </div>

      <div class="grid-item time-column full-width">
        <span class="badge-lbl">验证</span>
        <div class="time-wrapper">
          <span class="material-symbols-outlined icon-g">update</span>
          <span class="badge-txt color-gray font-mono">{{ item.lastSeen }}</span>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
defineProps({
  item: {
    type: Object,
    default: null
  },
  isAuthenticated: {
    type: Boolean,
    default: false
  }
})
defineEmits(['copy', 'test', 'delete'])
</script>

<style scoped>
.iptv-grid-card {
  background: var(--bg-card);
  border-radius: var(--radius-card);
  padding: 18px;
  box-shadow: var(--shadow-md);
  border: 1px solid rgba(0, 0, 0, 0.01);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-host {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.host-ip {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.font-mono {
  font-family: var(--font-mono);
  letter-spacing: -0.3px;
}

.copy-btn {
  background: var(--bg-neutral);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border: none;
  cursor: pointer;
}
.copy-btn:active { transform: scale(0.9); background: #E8E8ED; }

.host-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  border: none;
  cursor: pointer;
}

.delete-btn {
  background: #fdecea;
  color: #e5484d;
}
.delete-btn:active { transform: scale(0.9); background: #f5d6d3; }
.delete-btn .icon-g { color: #e5484d; }

.section-metrics-grid {
  border-top: 1px solid #F1F5F9;
  padding-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
}

.grid-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.grid-item.full-width {
  grid-column: span 2;
}

.badge-lbl {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  width: 38px;
}

.badge-txt {
  font-size: 12px;
  font-weight: 600;
}

.color-blue { color: var(--color-blue); }
.color-gray { color: var(--text-secondary); }
.color-dark { color: var(--text-primary); }

.delay-interactive-badge {
  background: var(--bg-status-good);
  color: var(--color-green);
  padding: 3px 8px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.delay-interactive-badge:active { transform: scale(0.95); }

.time-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
}

.icon-g {
  font-size: 16px !important;
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  display: inline-block;
  vertical-align: middle;
}
.copy-btn .icon-g { color: var(--text-muted); }
.delay-interactive-badge .icon-g { color: var(--color-green); }
.delay-interactive-badge.state-error {
  background: #fdecea;
  color: #e5484d;
}
.delay-interactive-badge.state-error .icon-g { color: #e5484d; }
.time-wrapper .icon-g { color: var(--text-muted); }
</style>
