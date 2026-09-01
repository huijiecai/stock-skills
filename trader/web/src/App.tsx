import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getToken, get } from './api/client'
import type { SystemRow, UserOut, Stages } from './api/types'
import { orderedStages } from './lib/system'
import { PageState } from './lib/ui'
import Layout from './components/Layout'
import Login from './pages/Login'
import Runs from './pages/Runs'
import RunDetail from './pages/RunDetail'
import Compare from './pages/Compare'
import SystemWorkspace from './pages/SystemWorkspace'
import SystemAsset from './pages/SystemAsset'
import PromptWorkbench from './pages/PromptWorkbench'
import DataWorkbench from './pages/DataWorkbench'
import DocsBrowser from './pages/DocsBrowser'
import Coach from './pages/Coach'
import SystemSettings from './pages/SystemSettings'

function Guard({ children }: { children: React.ReactNode }) {
  const hasToken = !!getToken()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => get<UserOut>('/auth/me'),
    enabled: hasToken,       // 没 token 不发请求
    retry: false,            // 401 不重试,直接走 error 分支
    staleTime: 60_000,       // 1 分钟内不重复验证
  })

  if (!hasToken) return <Navigate to="/login" replace />
  if (me.isLoading) return <PageState query={me} />
  if (me.isError) return <Navigate to="/login" replace />
  return <>{children}</>
}

/** /systems → 第一个活跃系统(无则回工作台)。 */
function SystemsRedirect() {
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get<SystemRow[]>('/systems') })
  if (systems.isLoading || systems.error) return <PageState query={systems} />
  const first = (systems.data ?? []).find(s => s.status !== 'archived')
  return <Navigate to={first ? `/systems/${encodeURIComponent(first.slug)}` : '/'} replace />
}



/** /workbench → 第一条指令(按业务序第一个阶段的 prompt)。 */
function WorkbenchRedirect() {
  const { name = '' } = useParams()
  const detail = useQuery({ queryKey: ['systemDetail', name], queryFn: () => get<SystemRow>(`/systems/${encodeURIComponent(name)}`) })
  if (detail.isLoading || detail.error) return <PageState query={detail} />
  const m = detail.data?.manifest
  // manifest 是透传 dict(ADR-0014):stages 子结构按运行时约定收窄
  const first = orderedStages((m?.stages ?? {}) as Stages)[0]?.[1]?.prompt || (m?.system_prompt as string | undefined)
  return <Navigate to={first ? `prompt/${encodeURIComponent(first)}` : '../settings'} replace />
}

/** 旧阶段 URL 只做兼容跳转；阶段页已被类型化工作台取代。 */
function LegacyStageRedirect() {
  const { name = '', stage = '' } = useParams()
  const detail = useQuery({
    queryKey: ['systemDetail', name],
    queryFn: () => get<SystemRow>(`/systems/${encodeURIComponent(name)}`),
  })
  if (detail.isLoading || detail.error) return <PageState query={detail} />
  const m = detail.data?.manifest
  const prompt = (stage === '_system'
    ? m?.system_prompt
    : (m?.stages as Stages | undefined)?.[stage]?.prompt) as string | undefined
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
