import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  AreaSeries,
  ColorType,
  CrosshairMode,
  type Time,
} from 'lightweight-charts'

interface KlineBar { open: number; high: number; low: number; close: number; volume: number; date?: string; time?: string }
interface IntradayPoint { time: string; price: number; avg: number; volume: number }

export interface StockChartPanelProps {
  name: string
  dailyData: KlineBar[]
  intradayData: IntradayPoint[]
  minuteData?: KlineBar[]
  minuteData5?: KlineBar[]
  preClose?: number
  height?: number
  tradingDays?: string[]
}

type Tab = 'fenshi' | 'daily' | '1min' | '5min'

const TABS: { key: Tab; label: string }[] = [
  { key: 'fenshi', label: '分时' },
  { key: 'daily', label: '日K' },
  { key: '1min', label: '1分' },
  { key: '5min', label: '5分' },
]

const chartTheme = {
  layout: { background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#94a3b8', fontSize: 11 },
  grid: { vertLines: { color: '#f0f2f7' }, horzLines: { color: '#f0f2f7' } },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: '#94a3b8', width: 1 as 1, style: 2, labelBackgroundColor: '#475569' },
    horzLine: { color: '#94a3b8', width: 1 as 1, style: 2, labelBackgroundColor: '#475569' },
  },
  rightPriceScale: { borderColor: '#dfe4ed', scaleMargins: { top: 0.05, bottom: 0.05 } },
  timeScale: { borderColor: '#dfe4ed', timeVisible: true },
}

function toTime(d: KlineBar | IntradayPoint): Time {
  const label = (d as KlineBar).date || (d as any).time || ''
  // Daily: "2026-06-24" or "06-24"
  if (/^\d{4}-\d{2}-\d{2}$/.test(label)) return label as Time
  if (/^\d{2}-\d{2}$/.test(label)) return `2026-${label}` as Time
  // Intraday/minute: "09:30" → Unix timestamp (seconds)
  if (/^\d{2}:\d{2}$/.test(label)) {
    const [h, m] = label.split(':').map(Number)
    const base = Math.floor(new Date('2026-06-24T00:00:00Z').getTime() / 1000)
    return (base + h * 3600 + m * 60) as Time
  }
  return label as Time
}

function useChart(containerRef: React.RefObject<HTMLDivElement | null>) {
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null)
  useEffect(() => {
    return () => {
      try { chartRef.current?.remove() } catch {}
      chartRef.current = null
    }
  }, [])
  return {
    chartRef,
    getOrCreate: (height?: number) => {
      if (!containerRef.current) return null
      try { chartRef.current?.remove() } catch {}
      chartRef.current = null
      if (height && containerRef.current) containerRef.current.style.height = `${height}px`
      const chart = createChart(containerRef.current, { ...chartTheme, height: height || 300 })
      chartRef.current = chart
      return chart
    },
  }
}

export default function StockChartPanel({
  name, dailyData, intradayData, minuteData, minuteData5, preClose, height = 420, tradingDays = [],
}: StockChartPanelProps) {
  const [tab, setTab] = useState<Tab>('fenshi')
  const [drillDate, setDrillDate] = useState<string | null>(null)
  const chartBoxRef = useRef<HTMLDivElement>(null)
  const { chartRef, getOrCreate } = useChart(chartBoxRef)

  const handleDrill = (date: string) => { setDrillDate(date); setTab('1min') }
  const exitDrill = () => setDrillDate(null)

  const minuteSrc = tab === '5min' ? minuteData5 : minuteData
  const currentMinuteDate = drillDate || tradingDays[tradingDays.length - 1] || ''
  const curIdx = tradingDays.indexOf(currentMinuteDate)
  const canPrev = curIdx > 0
  const canNext = curIdx >= 0 && curIdx < tradingDays.length - 1

  // ---- 分时 ----
  useEffect(() => {
    if (tab !== 'fenshi' || !chartBoxRef.current) return
    const chart = getOrCreate(height)
    if (!chart) return

    const areaSeries = chart.addSeries(AreaSeries, {
      lineColor: '#0891b2',
      topColor: 'rgba(8,145,178,0.18)',
      bottomColor: 'rgba(8,145,178,0.02)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    areaSeries.setData(intradayData.map(d => ({ time: toTime(d), value: d.price })))

    const avgSeries = chart.addSeries(LineSeries, {
      color: '#d97706',
      lineWidth: 1,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    avgSeries.setData(intradayData.map(d => ({ time: toTime(d), value: d.avg })))

    // PreClose reference line
    if (preClose) {
      areaSeries.createPriceLine({ price: preClose, color: '#94a3b8', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '昨收' })
    }

    chart.timeScale().fitContent()
    return () => { try { if (chartRef.current === chart) chart.remove() } catch {} }
  }, [tab, intradayData])

  // ---- 日K ----
  useEffect(() => {
    if (tab !== 'daily' || !chartBoxRef.current) return
    const chart = getOrCreate(height * 0.72)
    if (!chart) return

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#059669', downColor: '#dc2626',
      borderUpColor: '#059669', borderDownColor: '#dc2626',
      wickUpColor: '#059669', wickDownColor: '#dc2626',
    })
    candleSeries.setData(dailyData.map(d => ({ time: toTime(d), open: d.open, high: d.high, low: d.low, close: d.close })))

    chart.subscribeDblClick(param => {
      if (param.time) {
        const bar = dailyData.find(d => toTime(d) === param.time)
        if (bar) handleDrill(bar.date || bar.time || '')
      }
    })
    chart.timeScale().fitContent()
    return () => { try { if (chartRef.current === chart) chart.remove() } catch {} }
  }, [tab, dailyData])

  // ---- 1分 / 5分 ----
  useEffect(() => {
    if ((tab !== '1min' && tab !== '5min') || !chartBoxRef.current || !minuteSrc?.length) return
    const chart = getOrCreate(height * 0.72)
    if (!chart) return

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#059669', downColor: '#dc2626',
      borderUpColor: '#059669', borderDownColor: '#dc2626',
      wickUpColor: '#059669', wickDownColor: '#dc2626',
    })
    candleSeries.setData(minuteSrc.map(d => ({ time: toTime(d), open: d.open, high: d.high, low: d.low, close: d.close })))
    chart.timeScale().fitContent()
    return () => { try { if (chartRef.current === chart) chart.remove() } catch {} }
  }, [tab, minuteSrc])

  // Volume for minute tabs
  useEffect(() => {
    if ((tab !== '1min' && tab !== '5min') || !chartBoxRef.current) return
    // Volume is already handled inside the main chart — skipping separate volume pane for simplicity
  }, [tab])

  const last = dailyData[dailyData.length - 1]
  const isDrilled = drillDate !== null

  return (
    <div className="space-y-3">
      {/* Tab bar */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 bg-surface-overlay rounded-lg p-0.5">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => { setTab(t.key); if (t.key !== '1min' && t.key !== '5min') setDrillDate(null) }}
              className={`px-3.5 py-1.5 rounded-md text-xs font-medium transition-all ${
                tab === t.key
                  ? 'bg-surface-raised text-text-primary shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          {tab === 'daily' && (
            <span className="text-[10px] text-text-muted font-mono">💡 双击K线查看分钟线</span>
          )}
          {(tab === '1min' || tab === '5min') && (
            <div className="flex items-center gap-2">
              {isDrilled && (
                <button onClick={exitDrill} className="text-[10px] text-accent-cyan hover:underline font-mono">
                  ← 返回今日
                </button>
              )}
              <button
                disabled={!canPrev}
                onClick={() => canPrev && setDrillDate(tradingDays[curIdx - 1])}
                className="px-1.5 py-0.5 rounded text-xs text-text-muted hover:text-text-primary hover:bg-surface-overlay disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >‹</button>
              <span className="text-xs font-mono text-text-secondary min-w-[72px] text-center">{currentMinuteDate}</span>
              <button
                disabled={!canNext}
                onClick={() => canNext && setDrillDate(tradingDays[curIdx + 1])}
                className="px-1.5 py-0.5 rounded text-xs text-text-muted hover:text-text-primary hover:bg-surface-overlay disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >›</button>
            </div>
          )}
        </div>
      </div>

      {/* Chart container */}
      <div ref={chartBoxRef} className="rounded-xl border border-border-dim bg-white overflow-hidden" style={{ height }} />
    </div>
  )
}
