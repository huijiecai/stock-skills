/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// dev 代理:前端 5173 → 平台 API 8501(服务化设计 §1)
// bypass:浏览器页面导航(Accept: text/html)不代理,走 SPA 路由;
//         只有 fetch/XHR 调用(Accept: application/json)才转发到 API。
const PROXY_TARGET = process.env.TRADER_API_TARGET ?? 'http://127.0.0.1:8501'
const bypassForPageNav = (req: any) => {
  if (req.headers.accept?.includes('text/html')) return '/index.html'
}

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/auth': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/systems': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/tools': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/portfolios': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/runs': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/trading': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/docs': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/watchlists': { target: PROXY_TARGET, bypass: bypassForPageNav },
      '/healthz': { target: PROXY_TARGET, bypass: bypassForPageNav },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,               // RTL 依赖全局 afterEach 做自动 cleanup
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
