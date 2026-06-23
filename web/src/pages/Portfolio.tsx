import { positions, closedPositions, equityCurve, performance, accountSummary } from '../data/mock'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'
import { TrendingUp, Target, BarChart3, Clock } from 'lucide-react'

function PerfMetric({ label, value, icon: Icon }: { label: string; value: string; icon: React.ComponentType<{className?: string}> }) {
  return (
    <div className="card text-center">
      <Icon className="w-4 h-4 text-accent-cyan mx-auto mb-2" />
      <div className="metric-value text-text-primary text-xl">{value}</div>
      <div className="text-[10px] text-text-muted mt-1 uppercase tracking-wider">{label}</div>
    </div>
  )
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-surface-overlay border border-border-dim rounded-lg p-3 shadow-xl">
      <p className="text-[11px] font-mono text-text-muted mb-1">{label}</p>
      <p className="text-sm font-bold text-text-primary">¥{payload[0].value.toLocaleString()}</p>
    </div>
  )
}

export default function Portfolio() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-text-primary">AI 账户</h1>
        <p className="text-xs text-text-muted mt-0.5 font-mono">虚拟交易 · 初始 ¥{accountSummary.initialAssets.toLocaleString()}</p>
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <PerfMetric label="胜率" value={`${performance.winRate}%`} icon={Target} />
        <PerfMetric label="盈亏比" value={`${performance.profitLossRatio}:1`} icon={BarChart3} />
        <PerfMetric label="最大回撤" value={`${performance.maxDrawdown}%`} icon={TrendingUp} />
        <PerfMetric label="平均持有" value={`${performance.avgHoldDays}天`} icon={Clock} />
      </div>

      {/* Equity Curve */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-text-primary">资产曲线</h2>
          <div className="flex items-center gap-3 text-[11px] font-mono">
            <span className="text-profit">+{accountSummary.totalReturn}%</span>
            <span className="text-text-muted">vs 沪深300 +8.2%</span>
          </div>
        </div>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={equityCurve} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={{ stroke: '#dfe4ed' }} />
              <YAxis
                domain={[98000, 122000]}
                tick={{ fontSize: 10, fill: '#94a3b8' }}
                axisLine={{ stroke: '#dfe4ed' }}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={100000} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: '基准', fill: '#94a3b8', fontSize: 10 }} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#06b6d4"
                strokeWidth={2}
                dot={{ fill: '#06b6d4', r: 3 }}
                activeDot={{ fill: '#06b6d4', r: 5, stroke: '#06b6d4', strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Current Positions */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-text-primary">当前持仓</h2>
          <span className="text-[10px] font-mono text-text-muted">{positions.length}只 · ¥{accountSummary.holdingValue.toLocaleString()}</span>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border-dim text-left">
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">标的</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">持仓</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">均价</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">现价</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">盈亏</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">方向</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(p => (
              <tr key={p.code} className="border-b border-border-dim/50 last:border-0 hover:bg-surface-overlay/50 transition-colors">
                <td className="py-3">
                  <div className="text-sm font-medium text-text-primary">{p.name}</div>
                  <div className="text-[11px] text-text-muted font-mono">{p.code} · {p.sector}</div>
                </td>
                <td className="py-3 text-right">
                  <span className="text-sm font-mono text-text-primary">{p.shares}</span>
                  <span className="text-[10px] text-text-muted ml-1">股</span>
                </td>
                <td className="py-3 text-right text-sm font-mono text-text-secondary">¥{p.avgPrice.toFixed(2)}</td>
                <td className="py-3 text-right text-sm font-mono text-text-primary">¥{p.currentPrice.toFixed(2)}</td>
                <td className="py-3 text-right">
                  <div className={`text-sm font-mono ${p.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {p.pnl >= 0 ? '+' : ''}¥{p.pnl.toFixed(0)}
                  </div>
                  <div className={`text-[11px] font-mono ${p.pnlPct >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {p.pnlPct >= 0 ? '+' : ''}{p.pnlPct}%
                  </div>
                </td>
                <td className="py-3 text-right">
                  <span className={`tag ${p.sector === 'PCB' || p.sector === '光通信' ? 'text-accent-amber bg-accent-amber/10' : 'text-accent-cyan bg-accent-cyan/10'}`}>
                    {p.sector}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Closed Positions */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-text-primary">已平仓</h2>
          <span className="text-[10px] font-mono text-text-muted">{closedPositions.length}笔</span>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border-dim text-left">
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">标的</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">买入</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">卖出</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">盈亏</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">天数</th>
              <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">日期</th>
            </tr>
          </thead>
          <tbody>
            {closedPositions.map((p, i) => (
              <tr key={i} className="border-b border-border-dim/50 last:border-0 hover:bg-surface-overlay/50 transition-colors">
                <td className="py-2.5 text-sm text-text-primary">{p.name}</td>
                <td className="py-2.5 text-right text-xs font-mono text-text-secondary">¥{p.buyPrice}</td>
                <td className="py-2.5 text-right text-xs font-mono text-text-secondary">¥{p.sellPrice}</td>
                <td className="py-2.5 text-right">
                  <span className={`text-xs font-mono ${p.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {p.pnl >= 0 ? '+' : ''}{p.pnlPct}%
                  </span>
                </td>
                <td className="py-2.5 text-right text-xs font-mono text-text-muted">{p.holdDays}天</td>
                <td className="py-2.5 text-right text-xs font-mono text-text-muted">{p.sellDate}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
