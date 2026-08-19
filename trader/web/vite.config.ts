import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 代理:前端 5173 → 平台 API 8501(服务化设计 §1)
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': 'http://127.0.0.1:8501',
      '/systems': 'http://127.0.0.1:8501',
      '/ledgers': 'http://127.0.0.1:8501',
      '/runs': 'http://127.0.0.1:8501',
      '/trading': 'http://127.0.0.1:8501',
      '/docs': 'http://127.0.0.1:8501',
      '/watchlists': 'http://127.0.0.1:8501',
      '/healthz': 'http://127.0.0.1:8501',
    },
  },
})
