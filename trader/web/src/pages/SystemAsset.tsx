/** 资产视图 —— 原型「画面一/七」标记结构直接移植,数据接真。
 * 全宽无侧栏;模式切换在顶栏;值守状态条/指标带/净值曲线/今日卡片/模拟实验室。 */
import { Spin } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { get, post } from '../api/client'
import LaunchModal from '../components/LaunchModal'
import SystemSwitcher from '../components/SystemSwitcher'
import { stageLabel, systemDisplayName, orderedStages } from '../lib/system'
import { pnlColor } from '../lib/ui'

function EquityCurve({ points, initial, height = 230 }: {
  points: any[], initial: number | null, height?: number }) {
  if (!initial || points.length < 2)
    return <div style={{ padding: 44, textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>
      实盘组合还没有成交——跑起来,履历从这里开始生长</div>
  const W = 860, H = height, L = 52, B = 24
  const eqs = points.map((p: any) => p.equity)
  const min = Math.min(initial, ...eqs), max = Math.max(initial, ...eqs)
  const span = (max - min) || 1
  const x = (i: number) => L + (i / (points.length - 1)) * (W - L - 14)
  const y = (v: number) => 14 + (1 - (v - min) / span) * (H - 14 - B)
  let peak = -Infinity, ddPoint = -1, ddMax = 0
  points.forEach((p: any, i: number) => {
    peak = Math.max(peak, p.equity)
    const dd = peak > 0 ? (peak - p.equity) / peak : 0
    if (dd > ddMax) { ddMax = dd; ddPoint = i }
  })
  const path = points.map((p: any, i: number) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join(' ')
  const last = eqs[eqs.length - 1]
  const color = last >= initial ? 'var(--up)' : 'var(--down)'
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
      {[0, 0.25, 0.5, 0.75, 1].map(f => (
        <g key={f}>
          <line x1={L} x2={W - 14} y1={14 + f * (H - 14 - B)} y2={14 + f * (H - 14 - B)} stroke="#eef1f5" />
          <text x={L - 8} y={18 + f * (H - 14 - B)} fontSize={10} fill="#98a2b3" textAnchor="end">
            {(((1 - f) * span + min) / 100).toFixed(0)}
          </text>
        </g>
      ))}
      <line x1={L} x2={W - 14} y1={y(initial)} y2={y(initial)} stroke="#d0d5dd" strokeDasharray="4,4" />
      <path d={`${path} L${x(points.length - 1)},${H - B} L${L},${H - B} Z`}
            fill={last >= initial ? 'rgba(217,45,32,.05)' : 'rgba(2,122,72,.05)'} />
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
      {points.map((p: any, i: number) => {
        if (i === 0) return null
        const isDD = i === ddPoint && ddMax > 0.005
        return (
          <g key={i} style={{ cursor: p.run_id ? 'pointer' : 'default' }}
             onClick={() => p.run_id && (location.href = `/runs/${p.run_id}`)}>
            <circle cx={x(i)} cy={y(p.equity)} r={isDD ? 5 : 3.5}
                    fill={isDD ? 'var(--down)' : '#fff'} stroke={isDD ? 'var(--down)' : color} strokeWidth={2} />
            <title>{(p.ts || '开局').slice(0, 16) + ' · ¥' + (p.equity / 100).toFixed(0) + (p.run_id ? ' · 场次 #' + p.run_id : '')}</title>
          </g>
        )
      })}
      <text x={W - 16} y={y(last) - 8} fontSize={11.5} fill={color} fontWeight={700} textAnchor="end">
        ¥{(last / 100).toFixed(0)}
      </text>
      {ddPoint > 0 && (
        <text x={x(ddPoint)} y={Math.min(H - 4, y(points[ddPoint].equity) + 16)} fontSize={10.5}
              fill="var(--down)" textAnchor="middle">↓ 回撤 {(ddMax * 100).toFixed(1)}%</text>
      )}
    </svg>
  )
}

export default function SystemAsset() {
  const { name = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const system = name
  const today = dayjs().format('YYYYMMDD')
  const base = `/systems/${encodeURIComponent(system)}`
  const [launchOpen, setLaunchOpen] = useState(false)
  const [presetStage, setPresetStage] = useState('')

  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}`) })
  const runs = useQuery({
    queryKey: ['systemRuns', system],
    queryFn: () => get(`/runs?system=${encodeURIComponent(system)}`),
    refetchInterval: (q: any) => (q.state.data ?? []).some((r: any) => r.status === 'running' || r.status === 'stopping') ? 5000 : 30000,
  })
  const portfolios = useQuery({ queryKey: ['portfolios'], queryFn: () => get('/portfolios'), staleTime: 30000 })
  const prompts = useQuery({ queryKey: ['prompts', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}/prompts`) })

  const row: any = detail.data
  const stages: Record<string, any> = row?.manifest?.stages ?? {}
  const allRuns: any[] = runs.data ?? []
  const liveRuns = allRuns.filter(r => r.kind === 'live')
  const running = allRuns.find(r => r.status === 'running' || r.status === 'stopping')
  const myPorts: any[] = (portfolios.data ?? []).filter((p: any) => p.system_id === row?.id)
  const mainPort = myPorts.find(p => p.type === 'main')
  const labs = myPorts.filter(p => p.type !== 'main')
  const curve = useQuery({
    queryKey: ['curve', mainPort?.id],
    queryFn: () => get(`/portfolios/${mainPort.id}/curve`),
    enabled: !!mainPort,
  })
  const todayRuns = allRuns.filter(r => r.trade_date === today)

  async function stopRunning() {
    if (!running) return
    await post(`/runs/${running.id}/stop`)
    qc.invalidateQueries({ queryKey: ['systemRuns', system] })
  }

  if (detail.isLoading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />
  if (detail.error) return <div>{(detail.error as any).message}</div>

  const initial = curve.data?.initial
  const eqs: number[] = (curve.data?.points ?? []).map((p: any) => p.equity)
  const lastEq = eqs.length ? eqs[eqs.length - 1] : null
  const totalRet = initial && lastEq != null ? ((lastEq - initial) / initial) * 100 : null
  let peak = -Infinity, ddMax = 0
  eqs.forEach(v => { peak = Math.max(peak, v); if (peak > 0) ddMax = Math.max(ddMax, (peak - v) / peak) })
  const winDays = liveRuns.filter(r => (r.metrics?.return_pct ?? 0) > 0).length
  const firstStage = orderedStages(stages)[0]?.[0] ?? ''

  return (
    <div>
      {/* ── 顶栏(画面一)── */}
      <div className="ws-top">
                <a onClick={() => nav('/')} title="今日工作台"
           style={{ fontSize: 16, marginRight: -2 }}>🏠</a>
        <SystemSwitcher current={system} />
        <span className="ws-sysname">{systemDisplayName(row)}</span>
        {running && <span className="st-badge st-live"><span className="rd-live">●</span>运行中</span>}
        {row?.status === 'archived' && <span className="st-badge st-neutral">已归档</span>}
        <div className="ws-modes">
          <span className="on">📈 资产</span>
          <span onClick={() => firstStage && nav(`${base}/workbench`)}>🔧 工作台</span>
        </div>
        <div className="ws-btnrow">
          <button className="ws-btn" onClick={() => nav(`${base}/coach`)}>💬 教练</button>
          <button className="ws-btn" onClick={() => nav(`${base}/settings`)}>⚙ 设置</button>
          <button className="ws-btn primary" onClick={() => { setPresetStage(firstStage); setLaunchOpen(true) }}
                  disabled={!firstStage}>▶ 运行</button>
          {running && <button className="ws-btn danger" onClick={stopRunning}>⏹ 停止</button>}
        </div>
      </div>

      {/* ── 值守状态条 ── */}
      <div className="ws-statusband">
        {running ? (
          <>
            <span className="live">● {running.kind === 'live' ? '实盘值守中' : running.kind === 'replay' ? '重演执行中' : '执行中'}</span>
            <span>#{running.id}{running.stage ? ` · ${stageLabel(running.stage, stages[running.stage])}` : ''}
              {running.status === 'stopping' ? ' · 停止中(本轮收尾)' : ''}</span>
            <span className="next"><a onClick={() => nav(`/runs/${running.id}`)}>看实时执行 ↗</a></span>
          </>
        ) : (
          <span style={{ color: 'var(--text-3)' }}>○ 当前无执行中场次 · 点 ▶运行 开始今日值守</span>
        )}
      </div>

      <div className="ws-main">
        {/* 指标带 */}
        <div className="ws-metricrow">
          <div className="ws-mc">
            <div className="l">累计收益{liveRuns.length ? `(${liveRuns.length} 个交易日)` : ''}</div>
            <div className="v" style={{ color: totalRet == null ? 'var(--text-3)' : pnlColor(totalRet) }}>
              {totalRet == null ? '—' : `${totalRet > 0 ? '+' : ''}${totalRet.toFixed(1)}%`}
            </div>
            <div className="s">{lastEq != null ? `净值 ¥${(lastEq / 100).toFixed(0)} / ¥${((initial ?? 0) / 100).toFixed(0)}` : '实盘组合暂无数据'}</div>
          </div>
          <div className="ws-mc">
            <div className="l">最大回撤</div>
            <div className="v" style={{ color: ddMax > 0 ? 'var(--down)' : 'var(--text-3)' }}>
              {ddMax > 0 ? `-${(ddMax * 100).toFixed(1)}%` : '—'}</div>
            <div className="s">按成交时点权益</div>
          </div>
          <div className="ws-mc">
            <div className="l">盈利天数</div>
            <div className="v">{liveRuns.length ? `${winDays} / ${liveRuns.length}` : '—'}</div>
            <div className="s">{liveRuns.length ? `${Math.round(winDays / liveRuns.length * 100)}%` : ''}</div>
          </div>
          <div className="ws-mc">
            <div className="l">指令版本</div>
            <div className="v">{(prompts.data ?? []).length}</div>
            <div className="s">{Object.keys(stages).length} 个阶段</div>
          </div>
          <div className="ws-mc">
            <div className="l">今日执行</div>
            <div className="v">{todayRuns.length}<span style={{ fontSize: 12, color: 'var(--text-3)' }}> 场</span></div>
            <div className="s">{todayRuns.map(r => stageLabel(r.stage, stages[r.stage])).join(' · ') || '还未开始'}</div>
          </div>
        </div>

        {/* 净值曲线 */}
        <div className="ws-chartcard">
          <div className="ws-charthead">
            净值曲线 · 实盘组合{mainPort ? ` #${mainPort.id}` : ''}
            <span className="r">点击曲线上的点 → 归因到场次</span>
          </div>
          {mainPort
            ? (curve.isLoading ? <Spin /> : <EquityCurve points={curve.data?.points ?? []} initial={curve.data?.initial} />)
            : <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-3)' }}>
                还没有实盘组合——先用模拟组合验证亦可</div>}
        </div>

        {/* 今日卡片 */}
        <div className="ws-todaycard">
          <span className="h">今日 · {dayjs().format('M月D日 dddd')}</span><br />
          {todayRuns.length ? todayRuns.map(r => (
            <a key={r.id} style={{ marginRight: 14 }} onClick={() => nav(`/runs/${r.id}`)}>
              {stageLabel(r.stage, stages[r.stage])}({r.status}
              {r.metrics?.return_pct != null && `, ${r.metrics.return_pct > 0 ? '+' : ''}${r.metrics.return_pct}%`}) ↗
            </a>
          )) : <span style={{ color: 'var(--text-3)' }}>今天还没有执行——▶运行 发起盘前分析或实盘值守</span>}
        </div>

        {/* 模拟实验室(画面七) */}
        <div className="ws-labhead">
          🧪 模拟实验室
          <span className="st-badge st-neutral">模拟/实验组合独立核算 · 不进实盘履历</span>
          <span className="r">重演=模拟时钟</span>
        </div>
        <div className="ws-expgrid">
          {labs.length ? labs.map(p => <LabCard key={p.id} port={p} runs={allRuns} />) : (
            <div className="ws-expcard" style={{ borderStyle: 'dashed', boxShadow: 'none', background: 'transparent',
                     color: 'var(--text-3)', textAlign: 'center', padding: 24 }}>
              还没有实验——▶运行 选「重演某日」,验证过的改动再上实盘
            </div>
          )}
        </div>
      </div>

      <LaunchModal system={system} stages={stages} presetStage={presetStage}
                   open={launchOpen} onClose={() => setLaunchOpen(false)} />
    </div>
  )
}

function LabCard({ port, runs }: { port: any, runs: any[] }) {
  const mine = runs.filter(r => r.portfolio_id === port.id)
  const labCurve = useQuery({
    queryKey: ['labCurve', port.id],
    queryFn: () => get(`/portfolios/${port.id}/curve`),
  })
  const pts: number[] = (labCurve.data?.points ?? []).map((p: any) => p.equity)
  const init = labCurve.data?.initial
  const ret = init && pts.length ? ((pts[pts.length - 1] - init) / init) * 100 : null
  const W = 150, H = 40
  const mn = Math.min(...(pts.length ? pts : [0])), mx = Math.max(...(pts.length ? pts : [1]))
  const d = pts.map((v, i) => `${i ? 'L' : 'M'}${(i / Math.max(pts.length - 1, 1) * W).toFixed(1)},${(H - (v - mn) / ((mx - mn) || 1) * H).toFixed(1)}`).join(' ')
  return (
    <div className="ws-expcard" style={{ cursor: mine.length ? 'pointer' : 'default' }}
         onClick={() => mine[0] && (location.href = `/runs/${mine[0].id}`)}>
      <div className="eh">🔬 {port.name || `实验 #${port.id}`}
        <span className="ver">{port.type === 'paper' ? '模拟' : '实验'}</span>
        {ret != null && <b style={{ marginLeft: 'auto', color: pnlColor(ret) }}>
          {ret > 0 ? '+' : ''}{ret.toFixed(1)}%</b>}
      </div>
      <div className="em">{mine.length ? `${mine.length} 场 · 最近 ${mine[0].slug?.slice(0, 20)}` : '无场次(组合已开,待发起)'}</div>
      {pts.length > 1 && (
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 40, display: 'block' }}>
          <path d={d} fill="none" stroke={ret != null && ret >= 0 ? 'var(--up)' : 'var(--down)'} strokeWidth={1.8} />
        </svg>
      )}
    </div>
  )
}
