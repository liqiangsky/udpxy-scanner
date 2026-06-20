import { createApp } from 'vue'
import { createPinia } from 'pinia'

// 基础样式流水线
import './styles/main.css' // 设计系统变量 + 全局重置 + 布局

import App from './App.vue'
import router from './router/index.js'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
