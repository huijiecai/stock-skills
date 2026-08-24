/** 涨跌语义(A 股:红涨绿跌)的统一出口——全站只用这两个,不散落写色值。 */
import { Tag } from 'antd'

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
                  borderColor: up ? '#fecdca' : '#a6f4c5',
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

// ── 场次心跳:区分"真在跑"与"进程僵死"(机器睡眠/被杀/旧引擎)──

export const STALL_AFTER_MS = 5 * 60 * 1000   // 心跳超时阈值:5 分钟

/** running 但心跳超时(或无心跳)→ 疑似僵死。engine 每轮/每 10s 分片刷一次心跳。 */
export function runStalled(r: any, now = Date.now()): boolean {
  if (r?.status !== 'running') return false
  const hb = r.heartbeat_at ? Date.parse(r.heartbeat_at) : NaN
  if (Number.isNaN(hb)) return true
  return now - hb > STALL_AFTER_MS
}

/** 距上次心跳多久(人类可读),僵死徽章的悬停提示用。 */
export function heartbeatAge(r: any, now = Date.now()): string {
  const hb = r?.heartbeat_at ? Date.parse(r.heartbeat_at) : NaN
  if (Number.isNaN(hb)) return '无心跳'
  const mins = Math.floor((now - hb) / 60000)
  return mins < 1 ? '刚刚' : mins < 60 ? `${mins} 分钟前` : `${Math.floor(mins / 60)} 小时前`
}
