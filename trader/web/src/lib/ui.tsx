/** 涨跌语义(A 股:红涨绿跌)的统一出口——全站只用这两个,不散落写色值。 */
import { Empty, Popconfirm, Spin, Tag, Tooltip } from 'antd'
import type { ReactNode } from 'react'
import { STATUS } from './icons'

export const UP = 'var(--up)'
export const DOWN = 'var(--down)'

/** 语义色:>=0 红(涨),<0 绿(跌)。 */
export function pnlColor(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return 'var(--text-2)'
  return v >= 0 ? UP : DOWN
}

/** 涨跌符号:红 ▲ / 绿 ▼;零不显示。 */
export function pnlArrow(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v) || v === 0) return ''
  return v > 0 ? '▲' : '▼'
}

/** 收益百分比 Tag(红涨绿跌 + 符号)。 */
export function PnlTag({ value, suffix = '%' }: { value: number | null | undefined; suffix?: string }) {
  if (value == null || Number.isNaN(value)) return <span style={{ color: 'var(--text-3)' }}>-</span>
  const up = value >= 0
  return (
    <Tag style={{ marginInlineEnd: 0, color: up ? UP : DOWN,
                  background: up ? 'var(--up-bg)' : 'var(--down-bg)',
                  borderColor: up ? 'var(--up-border)' : 'var(--down-border)',
                  fontVariantNumeric: 'tabular-nums' }}>
      {pnlArrow(value)} {Math.abs(value)}{suffix}
    </Tag>
  )
}

/** 场次类型徽章:实盘(红)/模拟(蓝)/分析(灰紫)——用语义类,和状态徽章同体系。 */
export function KindBadge({ kind }: { kind: string }) {
  const map: Record<string, [string, string]> = {
    live: ['实盘', 'st-live'],
    paper: ['模拟盘', 'st-run'],
    replay: ['模拟', 'st-run'],
    single: ['分析', 'st-neutral'],
  }
  const [text, cls] = map[kind] ?? [kind, 'st-neutral']
  return <span className={`st-badge ${cls}`}>{text}</span>
}

// ── T3.3 页面范式组件:三态/状态徽章/确认操作,全站唯一出口 ──

/** StatusBadge:st-* 语义徽章统一入口。pulse=呼吸点(运行中)。 */
export function StatusBadge({ tone = 'neutral', pulse, children }: {
  tone?: 'live' | 'run' | 'ok' | 'neutral' | 'stall'
  pulse?: boolean
  children?: ReactNode
}) {
  return <span className={`st-badge st-${tone}`}>
    {pulse && <span className="rd-live">●</span>}{children}
  </span>
}

/** RunStatusBadge:场次状态徽章(running/stopping/sealed),僵死判定与心跳提示内置。
 *  runningTone:实盘顶栏传 live(红),列表/详情默认 run(蓝);runningText 覆盖文案。 */
export function RunStatusBadge({ r, runningText = '运行中', runningTone = 'run' }: {
  r: { status?: string; heartbeat_at?: string | null }
  runningText?: string
  runningTone?: 'live' | 'run'
}) {
  if (r.status !== 'running')
    return <StatusBadge tone="ok">{r.status === 'stopping' ? '停止中' : '已封场'}</StatusBadge>
  const stalled = runStalled(r)
  return (
    <Tooltip title={`心跳:${heartbeatAge(r)}${stalled
      ? '——进程可能被系统睡眠冻结或已死;可停止并强制封存' : ''}`}>
      <StatusBadge tone={stalled ? 'stall' : runningTone} pulse>
        {stalled ? '疑似僵死' : runningText}
      </StatusBadge>
    </Tooltip>
  )
}

/** PageState:区块三态(loading→error→empty)统一入口,正常渲染 children。
 *  query 接 useQuery 结果;也可显式传 loading/error(多 query 合并时用);
 *  empty 由调用方判(数据语义各异,组件不猜)。size:page=整页,panel=面板内。 */
export function PageState({ query, loading, error, empty, emptyText = '暂无数据',
                            size = 'page', children }: {
  query?: { isLoading?: boolean; error?: unknown }
  loading?: boolean
  error?: unknown
  empty?: boolean
  emptyText?: ReactNode
  size?: 'page' | 'panel'
  children?: ReactNode
}) {
  const isLoading = loading ?? query?.isLoading
  const err = error ?? query?.error
  if (isLoading)
    return <Spin size={size === 'page' ? 'large' : 'small'}
                 style={{ display: 'block', margin: size === 'page' ? '60px auto' : '20px auto' }} />
  if (err)
    return <div style={{ color: 'var(--danger)', textAlign: 'center',
                         padding: size === 'page' ? '40px 0' : '14px 0', fontSize: 13 }}>
      <STATUS.fail /> {(err as Error).message}
    </div>
  if (empty)
    return size === 'page'
      ? <Empty style={{ margin: '40px 0' }} description={emptyText} />
      : <div style={{ color: 'var(--text-3)', textAlign: 'center', padding: '14px 0', fontSize: 12 }}>
          {emptyText}
        </div>
  return <>{children}</>
}

/** ConfirmAction:确认后再执行(危险/不可逆操作统一入口)。
 *  声明式包裹触发元素;命令式防呆流(如未收盘提示)仍用 Modal.confirm。 */
export function ConfirmAction({ title, description, danger, okText = '确认',
                                onConfirm, children }: {
  title: ReactNode
  description?: ReactNode
  danger?: boolean
  okText?: string
  onConfirm?: () => void
  children: ReactNode
}) {
  return (
    <Popconfirm title={title} description={description} okText={okText} cancelText="取消"
                okButtonProps={danger ? { danger: true } : undefined}
                onConfirm={onConfirm}>
      {children}
    </Popconfirm>
  )
}

// ── 场次心跳:区分"真在跑"与"进程僵死"(机器睡眠/被杀/旧引擎)──

export const STALL_AFTER_MS = 5 * 60 * 1000   // 心跳超时阈值:5 分钟

/** running 但心跳超时(或无心跳)→ 疑似僵死。engine 每轮/每 10s 分片刷一次心跳。 */
export function runStalled(r: { status?: string; heartbeat_at?: string | null } | null | undefined,
                           now = Date.now()): boolean {
  if (r?.status !== 'running') return false
  const hb = r.heartbeat_at ? Date.parse(r.heartbeat_at) : NaN
  if (Number.isNaN(hb)) return true
  return now - hb > STALL_AFTER_MS
}

/** 距上次心跳多久(人类可读),僵死徽章的悬停提示用。 */
export function heartbeatAge(r: { heartbeat_at?: string | null } | null | undefined,
                             now = Date.now()): string {
  const hb = r?.heartbeat_at ? Date.parse(r.heartbeat_at) : NaN
  if (Number.isNaN(hb)) return '无心跳'
  const mins = Math.floor((now - hb) / 60000)
  return mins < 1 ? '刚刚' : mins < 60 ? `${mins} 分钟前` : `${Math.floor(mins / 60)} 小时前`
}

/** metrics 是透传 dict(ADR-0014),数值字段取数前收窄;非数值/缺失 → undefined。 */
export function metric(r: { metrics?: Record<string, unknown> | null } | null | undefined,
                       k: string): number | undefined {
  const v = r?.metrics?.[k]
  return typeof v === 'number' ? v : undefined
}
