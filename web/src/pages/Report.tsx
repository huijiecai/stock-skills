import { useState } from 'react'
import { dailyReport, tradingDays, reportDays } from '../data/mock'
import CalendarPicker from '../components/CalendarPicker'
import Modal from '../components/Modal'
import { ChevronDown, ChevronRight, Sunrise, Activity, Moon, Eye, Target, Calendar } from 'lucide-react'

function Section({ title, icon: Icon, children, defaultOpen = true }: {
  title: string; icon: React.ComponentType<{className?: string}>; children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="card">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 text-left"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-text-muted" /> : <ChevronRight className="w-3.5 h-3.5 text-text-muted" />}
        <Icon className="w-4 h-4 text-accent-cyan" />
        <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
      </button>
      {open && <div className="mt-4 ml-6">{children}</div>}
    </div>
  )
}

export default function Report() {
  const [selectedDate, setSelectedDate] = useState('2026-06-24')
  const [calendarOpen, setCalendarOpen] = useState(false)
  const report = dailyReport

  const handleDateSelect = (date: string) => {
    setSelectedDate(date)
    setCalendarOpen(false)
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header with calendar button */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">每日报告</h1>
          <p className="text-xs text-text-muted mt-0.5 font-mono">AI 的完整决策链路</p>
        </div>
        <button
          onClick={() => setCalendarOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20 hover:bg-accent-cyan/20 transition-colors"
        >
          <Calendar className="w-4 h-4" />
          <span className="text-sm font-mono font-medium">{selectedDate}</span>
        </button>
      </div>

      {/* Report Content - full width */}
      <div className="space-y-5">
        {/* Date Badge */}
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold font-mono text-accent-cyan">{selectedDate}</span>
          <span className="tag bg-accent-cyan/10 text-accent-cyan">情景 {report.preMarket.scenario}</span>
        </div>

        {/* Pre-Market */}
        <Section title="盘前分析摘要" icon={Sunrise}>
          <div className="space-y-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Eye className="w-3.5 h-3.5 text-accent-amber" />
                <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">市场情景判断</span>
              </div>
              <div className="bg-surface-overlay rounded-lg p-4 border border-border-dim">
                <div className="text-lg font-semibold text-accent-amber mb-1">情景 {report.preMarket.scenario}</div>
                <p className="text-sm text-text-muted">{report.preMarket.scenarioReason}</p>
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-2">
                <Target className="w-3.5 h-3.5 text-accent-amber" />
                <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">持仓预案</span>
              </div>
              <div className="space-y-1.5">
                {report.preMarket.holdingPlan.map((h, i) => (
                  <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg bg-surface-overlay/50 border border-border-dim/50">
                    <span className="text-sm font-medium text-text-primary shrink-0 w-20">{h.stock}</span>
                    <span className="text-sm text-text-muted">{h.plan}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-2">
                <Eye className="w-3.5 h-3.5 text-accent-cyan" />
                <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">关注方向</span>
              </div>
              <div className="flex gap-2 flex-wrap">
                {report.preMarket.focus.map((f, i) => (
                  <span key={i} className="tag bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20">{f}</span>
                ))}
              </div>
            </div>
          </div>
        </Section>

        {/* Intraday */}
        <Section title="盘中记录" icon={Activity}>
          <div className="space-y-0">
            {report.intraday.map((item, i) => (
              <div key={i} className="flex gap-3 group">
                <div className="flex flex-col items-center">
                  <div className={`w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${
                    item.event === '执行减仓' ? 'bg-loss' : item.event.includes('触发') ? 'bg-accent-amber' : 'bg-accent-cyan/50'
                  }`} />
                  {i < report.intraday.length - 1 && <div className="w-px flex-1 bg-border-dim my-1" />}
                </div>
                <div className="pb-5 flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-text-muted">{item.time}</span>
                    <span className="text-sm font-medium text-text-primary">{item.event}</span>
                  </div>
                  <p className="text-xs text-text-muted mt-1">{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* Summary */}
        <Section title="收盘总结" icon={Moon}>
          <div className="space-y-4">
            <div className="bg-surface-overlay rounded-lg p-4 border border-border-dim">
              <div className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">今日操作</div>
              <p className="text-sm text-text-primary leading-relaxed">{report.summary.operations}</p>
            </div>
            <div className="bg-surface-overlay rounded-lg p-4 border border-border-dim">
              <div className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-2">持仓状态</div>
              <p className="text-sm text-text-primary">{report.summary.holdingStatus}</p>
            </div>
            <div className="bg-surface-overlay rounded-lg p-4 border border-accent-cyan/20">
              <div className="text-xs font-medium text-accent-cyan uppercase tracking-wider mb-2">明日展望</div>
              <p className="text-sm text-text-primary">{report.summary.outlook}</p>
            </div>
          </div>
        </Section>
      </div>

      {/* Calendar Modal */}
      <Modal open={calendarOpen} onClose={() => setCalendarOpen(false)} title="选择日期" size="sm">
        <CalendarPicker
          selectedDate={selectedDate}
          onSelect={handleDateSelect}
          tradingDays={tradingDays}
          reportDays={reportDays}
          selectableDays={reportDays}
        />
      </Modal>
    </div>
  )
}
