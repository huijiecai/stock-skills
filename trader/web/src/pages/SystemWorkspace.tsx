/** 工作台(原型画面八/九标记结构移植):顶栏模式切换 + 类型化左栏(履历回链/指令/数据/文档) + 主区。
 * 指令=版本化的身份文件;数据=结构化原语;文档=按类型/按日期浏览。 */
import { Spin, message } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { get, post } from '../api/client'
import { stageIcon, stageLabel, systemDisplayName, orderedStages } from '../lib/system'
import LaunchModal from '../components/LaunchModal'
import SystemSwitcher from '../components/SystemSwitcher'

/** 阶段今日状态:single 看场名前缀，loop 看今日实时时钟场。 */
function stageTodayStatus(system: string, stage: string, def: any, runs: any[], today: string): 'done' | 'running' | null {
  if (def?.kind === 'single')
    return (runs ?? []).some(r => (r.slug ?? '').startsWith(`${system}-${stage}-${today}`)) ? 'done' : null
  if (def?.kind === 'loop') {
    const live = (runs ?? []).find(r => r.clock === 'real' && r.stage === stage && r.trade_date === today)
    if (!live) return null
    return live.status === 'running' ? 'running' : 'done'
  }
  return null
}

export default function SystemWorkspace() {
  const { name = '' } = useParams()
  const nav = useNavigate()
  const loc = useLocation()
  const system = name
  const qc = useQueryClient()

  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}`) })
  const runs = useQuery({
    queryKey: ['systemRuns', system],
    queryFn: () => get(`/runs?system=${encodeURIComponent(system)}`),
    refetchInterval: (query: any) => {
      const active = (query.state.data ?? []).some((r: any) => r.status === 'running' || r.status === 'stopping')
      return active ? 5000 : 30_000
    },
  })
  const promptsList = useQuery({ queryKey: ['prompts', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}/prompts`) })
  const watchlists = useQuery({
    queryKey: ['watchlists', system],
    queryFn: () => get(`/watchlists?system=${encodeURIComponent(system)}`),
    staleTime: 60000,
  })

  const [launchOpen, setLaunchOpen] = useState(false)
  const [presetStage, setPresetStage] = useState('')

  const row: any = detail.data
  const manifest = row?.manifest
  const stages: Record<string, any> = manifest?.stages ?? {}
  const today = dayjs().format('YYYYMMDD')
  const base = `/systems/${encodeURIComponent(system)}`

  // 类型化导航状态(原型画面八:ws-tree)
  const activePrompt = loc.pathname.includes('/workbench/prompt/')
    ? decodeURIComponent(loc.pathname.split('/').pop() ?? '') : ''
  const navKey = loc.pathname.endsWith('/workbench/data') ? 'data'
    : loc.pathname.endsWith('/workbench/docs') ? 'docs' : ''
  const onSettings = loc.pathname.endsWith('/settings')
  const onCoach = loc.pathname.includes('/coach')
  const sysPromptSlug = manifest?.system_prompt ?? ''
  const promptVer: Record<string, number | null> = {}
  for (const p of (promptsList.data ?? []) as any[]) promptVer[p.prompt] = p.latest_version
  const watchCount = (watchlists.data as any[] | undefined)?.length
  const runningRun = (runs.data ?? []).find((r: any) => r.status === 'running' || r.status === 'stopping')
  const coachUrl = activePrompt
    ? `${base}/coach?prompt=${encodeURIComponent(activePrompt)}`
    : `${base}/coach`

  async function stopRunning() {
    if (!runningRun) return
    try {
      const r = await post(`/runs/${runningRun.id}/stop`)
      message.success(r.note || '已请求停止')
      qc.invalidateQueries({ queryKey: ['systemRuns', system] })
    } catch (e: any) { message.error(e.message) }
  }

  if (detail.isLoading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />
  if (detail.error) return <div>{(detail.error as any).message}</div>

  const firstStage = orderedStages(stages)[0]?.[0] ?? ''

  return (
    <div>
      {/* ── 顶栏(画面八:与资产页同构)── */}
      <div className="ws-top">
                <a onClick={() => nav('/')} title="今日工作台"
           style={{ fontSize: 16, marginRight: -2 }}>🏠</a>
        <SystemSwitcher current={system} />
        <span className="ws-sysname">{systemDisplayName(row)}</span>
        {runningRun && <span className="st-badge st-live"><span className="rd-live">●</span>运行中</span>}
        {row?.status === 'archived' && <span className="st-badge st-neutral">已归档</span>}
        <div className="ws-modes">
          <span onClick={() => nav(base)}>📈 资产</span>
          <span className="on">🔧 工作台</span>
        </div>
        <div className="ws-btnrow">
          <button className="ws-btn" onClick={() => nav(coachUrl)}>💬 教练</button>
          <button className="ws-btn" onClick={() => nav(`${base}/settings`)}>⚙ 设置</button>
          <button className="ws-btn primary" onClick={() => { setPresetStage(firstStage); setLaunchOpen(true) }}
                  disabled={!firstStage}>▶ 运行</button>
          {runningRun && <button className="ws-btn danger" onClick={stopRunning}>⏹ 停止</button>}
        </div>
      </div>

      <div className="ws-body">
        {/* ── 左栏:类型化(画面八 ws-tree)── */}
        <nav className="ws-tree">
          <div className="ws-backlink" onClick={() => nav(base)}>📈 履历 · 资产视图 ↗</div>

          <div className="ws-tg">📜 指令</div>
          <div className={`ws-f${activePrompt === sysPromptSlug ? ' sel' : ''}`}
               onClick={() => sysPromptSlug && nav(`${base}/workbench/prompt/${encodeURIComponent(sysPromptSlug)}`)}>
            <span>⚙️</span><span>系统设定</span>
            <span className="meta">{promptVer[sysPromptSlug] != null ? `v${promptVer[sysPromptSlug]} ●在用` : ''}</span>
          </div>
          {orderedStages(stages).map(([s, d]) => {
            const st = stageTodayStatus(system, s, d, runs.data ?? [], today)
            const pslug = d?.prompt
            return (
              <div key={s} className={`ws-f${activePrompt === pslug ? ' sel' : ''}`}
                   onClick={() => pslug && nav(`${base}/workbench/prompt/${encodeURIComponent(pslug)}`)}>
                <span>{stageIcon(s)}</span><span>{stageLabel(s, d)}</span>
                <span className="meta">
                  {st === 'running' ? '●' : st === 'done' ? '✓ ' : ''}
                  {promptVer[pslug] != null ? `v${promptVer[pslug]}` : ''}
                </span>
              </div>
            )
          })}

          <div className="ws-tg">⭐ 数据</div>
          <div className={`ws-f${navKey === 'data' ? ' sel' : ''}`}
               onClick={() => nav(`${base}/workbench/data`)}>
            <span>📊</span><span>自选组</span>
            <span className="meta">{watchCount != null ? `${watchCount} 组` : ''}</span>
          </div>

          <div className="ws-tg">📚 文档</div>
          <div className={`ws-f${navKey === 'docs' ? ' sel' : ''}`}
               onClick={() => nav(`${base}/workbench/docs`)}>
            <span>🗂</span><span>按类型 / 按日期</span>
            <span className="meta">↗</span>
          </div>

          {/* 设置/教练 落在树底部 */}
          <div className="ws-tg">·</div>
          <div className={`ws-f${onCoach ? ' sel' : ''}`} onClick={() => nav(coachUrl)}>
            <span>💬</span><span>教练对话</span>
          </div>
          <div className={`ws-f${onSettings ? ' sel' : ''}`} onClick={() => nav(`${base}/settings`)}>
            <span>⚙️</span><span>系统设置</span>
          </div>
        </nav>

        {/* ── 主区(指令台/数据/文档/设置/教练)── */}
        <div style={{ flex: 1, minWidth: 0, padding: 14, display: 'flex' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex' }}><Outlet /></div>
        </div>
      </div>

      <LaunchModal system={system} stages={stages} presetStage={presetStage}
                   open={launchOpen} onClose={() => setLaunchOpen(false)} />
    </div>
  )
}
