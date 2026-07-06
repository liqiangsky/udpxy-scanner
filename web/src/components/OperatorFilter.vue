<template>
  <div class="select-wrapper-inline">
    <select
      :value="modelValue"
      class="apple-select-sm"
      @change="$emit('update:modelValue', $event.target.value)"
    >
      <option value="">{{ placeholder }}</option>
      <option v-for="opt in operators" :key="opt" :value="opt">{{ opt }}</option>
    </select>
  </div>
</template>

<script setup>
import { operators } from '@/data.js'

defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '全部网络' },
})

defineEmits(['update:modelValue'])
</script>

<style scoped>
.select-wrapper-inline {
  display: inline-flex;
}
.apple-select-sm {
  appearance: none;
  -webkit-appearance: none;
  background-color: var(--bg-neutral);
  color: var(--text-primary);
  border: none;
  padding: 6px 28px 6px 10px;
  border-radius: var(--radius-input);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  outline: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='%238E8E93' d='M0 0h10L5 6z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 10px center;
}
.apple-select-sm:active,
.apple-select-sm:hover {
  background-color: #e8e8ed;
}
</style>
