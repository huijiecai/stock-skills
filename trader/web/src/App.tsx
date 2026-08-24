import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Spin } from 'antd'
import { getToken, get } from './api/client'
import { orderedStages } from './lib/system'
import Layout from './components/Layout'
import Login from './pages/Login'
import Runs from './pages/Runs'
import RunDetail from './pages/RunDetail'
import Compare from './pages/Compare'
import SystemWorkspace from './pages/SystemWorkspace'
import SystemAsset from './pages/SystemAsset'
import PromptWorkbench from './components/PromptWorkbench'
import DataWorkbench from './components/DataWorkbench'
import DocsBrowser from './components/DocsBrowser'
import Coach from './pages/Coach'
import SystemSettings from './components/SystemSettings'

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
      <Spin size="large"><div style={{padding:8}}>验证登录…</div></Spin>
    </div>
  )
  if (me.isError) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** /systems → 第一个活跃系统(无则回工作台)。 */
function SystemsRedirect() {
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get('/systems') })
  if (systems.isLoading)
    return <div style={{ padding: 80, textAlign: 'center' }}><Spin size="large" /></div>
  const first = (systems.data ?? []).find((s: any) => s.status !== 'archived')
  return <Navigate to={first ? `/systems/${encodeURIComponent(first.slug)}` : '/'} replace />
}



/** /workbench → 第一条指令(按业务序第一个阶段的 prompt)。 */
function WorkbenchRedirect() {
  const { name = '' } = useParams()
  const detail = useQuery({ queryKey: ['systemDetail', name], queryFn: () => get(`/systems/${encodeURIComponent(name)}`) })
  if (detail.isLoading) return <Spin style={{ display: 'block', margin: '60px auto' }} />
  const m = detail.data?.manifest
  const first = orderedStages(m?.stages ?? {})[0]?.[1]?.prompt || m?.system_prompt
  return <Navigate to={first ? `prompt/${encodeURIComponent(first)}` : '../settings'} replace />
}

/** 旧阶段 URL 只做兼容跳转；阶段页已被类型化工作台取代。 */
function LegacyStageRedirect() {
  const { name = '', stage = '' } = useParams()
  const detail = useQuery({
    queryKey: ['systemDetail', name],
    queryFn: () => get(`/systems/${encodeURIComponent(name)}`),
  })
  if (detail.isLoading) return <Spin style={{ display: 'block', margin: '60px auto' }} />
  const prompt = stage === '_system'
    ? detail.data?.manifest?.system_prompt
    : detail.data?.manifest?.stages?.[stage]?.prompt
  return <Navigate to={prompt
    ? `/systems/${encodeURIComponent(name)}/workbench/prompt/${encodeURIComponent(prompt)}`
    : `/systems/${encodeURIComponent(name)}/workbench`} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Guard><Layout /></Guard>}>
        <Route index element={<SystemsRedirect />} />   {/* 新首页=第一个系统的资产视图 */}
        <Route path="runs" element={<Runs />} />
        <Route path="runs/:id" element={<RunDetail />} />
        <Route path="compare" element={<Compare />} />
        <Route path="systems" element={<SystemsRedirect />} />
        <Route path="systems/:name">
          <Route index element={<SystemAsset />} />   {/* 资产视图:独立全宽,无侧栏 */}
          <Route element={<SystemWorkspace />}>      {/* 工作台外壳:类型化侧栏(指令/数据/文档) */}
            <Route path="workbench" element={<WorkbenchRedirect />} />
            <Route path="workbench/prompt/:prompt" element={<PromptWorkbench />} />
            <Route path="workbench/data" element={<DataWorkbench />} />
            <Route path="workbench/docs" element={<DocsBrowser />} />
            <Route path="settings" element={<SystemSettings />} />
            <Route path="coach" element={<Coach />} />
            <Route path="coach/conversations" element={<Coach />} />
            <Route path="stage/:stage/*" element={<LegacyStageRedirect />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
