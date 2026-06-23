import { accountSummary, signals, expectations, aiTimeline } from '../data/mock'
import { TrendingUp, TrendingDown, DollarSign, Activity, AlertTriangle, ArrowRight, Clock } from 'lucide-react'

function MetricCard({ label, value, sub, icon: Icon, trend }: {
  label: string; value: string; sub: string; icon: React.ComponentType<{className?: string}>; trend?: 'up' | 'down' | 'neutral'
}) {
  const trendColor = trend === 'up' ? 'text-profit' : trend === 'down' ? 'text-loss' : 'text-text-secondary'
  return (
    <div className="card card-hover">
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs text-text-muted uppercase tracking-wider">{label}</span>
        <Icon className={`w-4 h-4 ${trendColor}`} />
      </div>
      <div className="metric-value text-text-primary">{value}</div>
      <div className={`text-xs mt-1 font-mono ${trendColor}`}>{sub}</div>
    </div>
  )
}

function SignalItem({ signal }: { signal: typeof signals[0] }) {
  const icon = signal.type === 'sell' ? TrendingDown : AlertTriangle
  const color = signal.type === 'sell' ? 'text-loss' : 'text-accent-amber'
  const bg = signal.type === 'sell' ? 'bg-loss-dim/20' : 'bg-accent-amber/10'
  const Icon = icon

  return (
    <div className={`flex items-center gap-3 p-3 rounded-lg ${bg} border border-border-dim`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${bg}`}>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-text-primary">{signal.name}</span>
          <span className={`tag ${color} ${bg}`}>{signal.action}</span>
        </div>
        <div className="text-xs text-text-muted mt-0.5 truncate">{signal.reason}</div>
      </div>
      <div className="text-right shrink-0">
        {signal.price > 0 && <div className="text-sm font-mono text-text-primary">¥{signal.price}</div>}
        {signal.pnl && <div className="text-xs font-mono text-profit">{signal.pnl}</div>}
        <div className="text-[10px] text-text-muted font-mono">{signal.time}</div>
      </div>
    </div>
  )
}

function ExpectationRow({ exp }: { exp: typeof expectations[0] }) {
  const stageColor = exp.stage === '加速期' ? 'text-accent-amber' : exp.stage === '确认期' ? 'text-accent-cyan' : 'text-text-muted'
  const stageBg = exp.stage === '加速期' ? 'bg-accent-amber/10' : exp.stage === '确认期' ? 'bg-accent-cyan/10' : 'bg-surface-overlay'

  return (
    <tr className="border-b border-border-dim/50 last:border-0">
      <td className="py-2.5 pr-4">
        <div className="text-sm font-medium text-text-primary">{exp.name}</div>
        <div className="text-[11px] text-text-muted">{exp.stock}</div>
      </td>
      <td className="py-2.5 pr-4">
        <span className={`tag ${stageColor} ${stageBg}`}>{exp.stage}</span>
      </td>
      <td className="py-2.5 pr-4">
        <span className={`text-xs font-mono ${exp.warning ? 'text-accent-amber' : 'text-text-secondary'}`}>
          {exp.day}{exp.warning && '⚠️'}
        </span>
      </td>
      <td className="py-2.5">
        <span className="text-xs text-text-muted">{exp.confidence}</span>
      </td>
    </tr>
  )
}

export default function Dashboard() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Dashboard</h1>
          <p className="text-xs text-text-muted mt-0.5 font-mono">2026-06-24 · 盘后归档中</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="pulse-dot bg-accent-amber" style={{ color: 'var(--color-accent-amber)' }} />
          <span className="text-xs text-accent-amber font-medium">盘后归档中</span>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <MetricCard
          label="总资产"
          value={`¥${accountSummary.totalAssets.toLocaleString()}`}
          sub={`+${accountSummary.totalReturn}%`}
          icon={TrendingUp}
          trend="up"
        />
        <MetricCard
          label="今日盈亏"
          value={`¥${accountSummary.todayPnL.toLocaleString()}`}
          sub={`${accountSummary.todayReturn}%`}
          icon={TrendingDown}
          trend="down"
        />
        <MetricCard
          label="持仓市值"
          value={`¥${accountSummary.holdingValue.toLocaleString()}`}
          sub="4只持仓"
          icon={Activity}
          trend="neutral"
        />
        <MetricCard
          label="现金"
          value={`¥${accountSummary.cash.toLocaleString()}`}
          sub="59.2%"
          icon={DollarSign}
          trend="neutral"
        />
      </div>

      <div className="grid grid-cols-5 gap-6">
        {/* Left: Signals + Expectations */}
        <div className="col-span-3 space-y-6">
          {/* Signals */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <AlertTriangle className="w-3.5 h-3.5 text-accent-amber" />
                今日信号
              </h2>
              <span className="text-[10px] font-mono text-text-muted">{signals.length}条</span>
            </div>
            <div className="space-y-2">
              {signals.map((s, i) => <SignalItem key={i} signal={s} />)}
            </div>
          </div>

          {/* Expectations */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-text-primary">活跃预期</h2>
              <span className="text-[10px] font-mono text-text-muted">{expectations.length}个方向</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-dim text-left">
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">方向</th>
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">阶段</th>
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">天数</th>
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">置信度</th>
                </tr>
              </thead>
              <tbody>
                {expectations.map((e, i) => <ExpectationRow key={i} exp={e} />)}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: AI Timeline */}
        <div className="col-span-2">
          <div className="card h-full">
            <div className="flex items-center gap-2 mb-4">
              <Clock className="w-3.5 h-3.5 text-accent-cyan" />
              <h2 className="text-sm font-semibold text-text-primary">AI 活动时间线</h2>
            </div>
            <div className="space-y-0">
              {aiTimeline.map((item, i) => (
                <div key={i} className="flex gap-3 group">
                  <div className="flex flex-col items-center">
                    <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${
                      i === aiTimeline.length - 1 ? 'bg-accent-amber' : 'bg-accent-cyan/60'
                    }`} />
                    {i < aiTimeline.length - 1 && <div className="w-px flex-1 bg-border-dim my-1" />}
                  </div>
                  <div className="pb-4 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-mono text-text-muted">{item.time}</span>
                      <span className="text-sm text-text-primary">{item.event}</span>
                    </div>
                    <p className="text-xs text-text-muted mt-0.5">{item.detail}</p>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 pt-3 border-t border-border-dim">
              <a href="/report" className="text-xs text-accent-cyan flex items-center gap-1 hover:underline">
                查看完整报告 <ArrowRight className="w-3 h-3" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
