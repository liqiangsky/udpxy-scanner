import { defineConfig, globalIgnores } from 'eslint/config'
import globals from 'globals'
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import skipFormatting from 'eslint-config-prettier/flat'

export default defineConfig([
  {
    name: 'app/files-to-lint',
    files: ['**/*.{vue,js,mjs,jsx}'],
  },

  // 全局忽略的目录
  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**']),

  {
    languageOptions: {
      globals: {
        ...globals.browser,
        // 如果你的组件中使用了 Vue 3 的 Compiler-macro（如 defineProps, defineEmits），
        // 且你的环境没有自动启用它们，可以取消下面这行的注释：
        // ...globals.vue,
      },
    },
  },

  // 1. JS 推荐规则
  js.configs.recommended,

  // 2. Vue 3 核心基础规则 (对应你的 vue 3.5+ 组件)
  ...pluginVue.configs['flat/essential'],

  // 3. 必须放在最后：禁用所有与 Prettier/格式化冲突的 ESLint 规则
  skipFormatting,
])
