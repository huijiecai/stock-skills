import { Navigate, Route, Routes } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Spin } from 'antd'
import { getToken, get } from './api/client'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Runs from './pages/Runs'
import RunDetail from './pages/RunDetail'
import Compare from './pages/Compare'
import Systems from './pages/Systems'

function Guard({ children }: { children: React.ReactNode }) {
  const hasToken = !!getToken()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => get('/auth/me'),
    enabled: hasToken,       // 没 token 不发请求
    retry: false,            // 401 不重试,直接走 error 分支
    staleTime: 60_000,       // 1 分钟内不重复验证
  })

  if (!hasToken) return <Navigate to="/login" replace />
  if (me.isLoading) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Spin size="large" tip="验证登录…" />
    </div>
  )
  if (me.isError) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Guard><Layout /></Guard>}>
        <Route index element={<Dashboard />} />
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:id" element={<RunDetail />} />
        <Route path="compare" element={<Compare />} />
        <Route path="systems" element={<Systems />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
