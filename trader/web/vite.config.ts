import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// dev 代理:前端 5173 → 平台 API 8501(服务化设计 §1)
// bypass:浏览器页面导航(Accept: text/html)不代理,走 SPA 路由;
//         只有 fetch/XHR 调用(Accept: application/json)才转发到 API。
const PROXY_TARGET = 'http://127.0.0.1:8501'
const bypassForPageNav = (req: any) => {
  if (req.headers.accept?.includes('text/html')) return '/index.html'
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/systems': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/ledgers': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/runs': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/trading': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/docs': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/watchlists': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/healthz': { target: PROXY_TARGET, bypass: bypassForPageNav },
    },
  },
})
