import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface CalendarPickerProps {
  selectedDate: string // YYYY-MM-DD
  onSelect: (date: string) => void
  tradingDays: string[]
  reportDays?: string[]
  selectableDays?: string[] // If provided, only these dates are clickable. If omitted, tradingDays are clickable.
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate()
}

function getFirstDayOfMonth(year: number, month: number) {
  const day = new Date(year, month, 1).getDay()
  return day === 0 ? 6 : day - 1 // Monday = 0
}

export default function CalendarPicker({ selectedDate, onSelect, tradingDays, reportDays = [], selectableDays }: CalendarPickerProps) {
  const [viewYear, setViewYear] = useState(2026)
  const [viewMonth, setViewMonth] = useState(5) // 0-indexed, 5 = June

  const daysInMonth = getDaysInMonth(viewYear, viewMonth)
  const firstDay = getFirstDayOfMonth(viewYear, viewMonth)

  const prevMonth = () => {
    if (viewMonth === 0) { setViewMonth(11); setViewYear(y => y - 1) }
    else setViewMonth(m => m - 1)
  }

  const nextMonth = () => {
    if (viewMonth === 11) { setViewMonth(0); setViewYear(y => y + 1) }
    else setViewMonth(m => m + 1)
  }

  const formatDate = (day: number) => {
    const m = String(viewMonth + 1).padStart(2, '0')
    const d = String(day).padStart(2, '0')
    return `${viewYear}-${m}-${d}`
  }

  const days: (number | null)[] = []
  for (let i = 0; i < firstDay; i++) days.push(null)
  for (let d = 1; d <= daysInMonth; d++) days.push(d)

  const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

  return (
    <div className="card w-full max-w-md mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={prevMonth} className="p-1.5 rounded hover:bg-surface-overlay">
          <ChevronLeft className="w-4 h-4 text-text-muted" />
        </button>
        <span className="text-sm font-medium text-text-primary font-mono">
          {viewYear}年 {monthNames[viewMonth]}
        </span>
        <button onClick={nextMonth} className="p-1.5 rounded hover:bg-surface-overlay">
          <ChevronRight className="w-4 h-4 text-text-muted" />
        </button>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {WEEKDAYS.map(w => (
          <div key={w} className="text-xs text-text-muted text-center py-1.5 font-medium">{w}</div>
        ))}
      </div>

      {/* Days */}
      <div className="grid grid-cols-7 gap-1">
        {days.map((day, i) => {
          if (day === null) return <div key={`empty-${i}`} />

          const dateStr = formatDate(day)
          const isTrading = tradingDays.includes(dateStr)
          const hasReport = reportDays.includes(dateStr)
          const isSelectable = selectableDays
            ? selectableDays.includes(dateStr)
            : isTrading
          const isSelected = dateStr === selectedDate
          const isWeekend = (i % 7) >= 5

          return (
            <button
              key={dateStr}
              onClick={() => isSelectable && onSelect(dateStr)}
              disabled={!isSelectable}
              className={`
                relative w-full aspect-square rounded-lg text-sm font-mono transition-all
                ${isSelected
                  ? 'bg-accent-cyan text-white font-bold'
                  : isSelectable
                    ? 'hover:bg-surface-overlay text-text-primary cursor-pointer'
                    : isTrading
                      ? 'text-text-muted cursor-not-allowed'
                      : isWeekend
                        ? 'text-text-muted/40'
                        : 'text-text-muted/60'
                }
              `}
            >
              {day}
              {/* Trading day dot */}
              {isTrading && !isSelected && (
                <div className="absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-accent-cyan/60" />
              )}
              {/* Report available indicator */}
              {hasReport && !isSelected && (
                <div className="absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-profit" />
              )}
            </button>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3 pt-2 border-t border-border-dim">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-profit" />
          <span className="text-[10px] text-text-muted">有报告</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-accent-cyan/60" />
          <span className="text-[10px] text-text-muted">交易日</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-text-muted/30" />
          <span className="text-[10px] text-text-muted">休市</span>
        </div>
      </div>
    </div>
  )
}
