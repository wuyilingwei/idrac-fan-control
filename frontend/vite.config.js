import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// Vite 配置 — build 产物输出到 ../app/static/,由 Starlette StaticFiles 托管。
// dev 模式: vite 自带 dev server 默认 :5173,前端 fetch '/api/*' 走 vite proxy 转发到核心服务 :8080。
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: resolve(__dirname, '../app/static'),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
})
