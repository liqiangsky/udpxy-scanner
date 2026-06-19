import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  // 🔌 在这里追加本地开发服务器的代理配置
  server: {
    host: '0.0.0.0', // 允许局域网其他设备（比如你的手机）通过 IP 访问前端进行测试
    port: 5173,      // 前端本地默认端口
    proxy: {
      // 当前端请求以 /api 开头时，Vite 会拦截并悄悄帮转发给后端
      '/api': {
        target: 'http://localhost:7860', // 你的 FastAPI 后端真实运行地址
        changeOrigin: true,              // 允许跨域欺骗，把请求头中的 Host 悄悄换成后端的地址
        // rewrite: (path) => path       // 注意：因为你的后端路由本身就带有 /api 前缀（如 /api/configs），所以这里【不需要】重写抹去 /api
      }
    }
  }
})
