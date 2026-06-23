import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
  type Time,
} from 'lightweight-charts'

interface KlineData {
  date?: string
  time?: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface KlineChartProps {
  data: KlineData[]
  title?: string
  height?: number
  onBarDoubleClick?: (date: string) => void
  interactive?: boolean
}

function toTime(d: KlineData): Time {
  const label = d.date || d.time || ''
  // daily: "2026-06-24"
  if (/^\d{4}-\d{2}-\d{2}$/.test(label)) return label as Time
  // short date: "06-24" → "2026-06-24"
  if (/^\d{2}-\d{2}$/.test(label)) return `2026-${label}` as Time
  // minute: "10:30"
  if (/^\d{2}:\d{2}$/.test(label)) return `2026-06-24 ${label}` as Time
  // minute with date: "2026-06-24 10:30"
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(label)) return label as Time
  return label as Time
}

function toDateStr(d: KlineData): string {
  return d.date || d.time || ''
}

export default function KlineChart({ data, title, height = 400, onBarDoubleClick, interactive }: KlineChartProps) {
  const priceRef = useRef<HTMLDivElement>(null)
  const volRef = useRef<HTMLDivElement>(null)
  const [ohlc, setOhlc] = useState<KlineData | null>(null)

  useEffect(() => {
    if (!priceRef.current || !volRef.current) return

    // ---- Price Chart ----
    const priceChart = createChart(priceRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#94a3b8',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#f0f2f7' },
        horzLines: { color: '#f0f2f7' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#94a3b8', width: 1, style: 2, labelBackgroundColor: '#475569' },
        horzLine: { color: '#94a3b8', width: 1, style: 2, labelBackgroundColor: '#475569' },
      },
      rightPriceScale: {
        borderColor: '#dfe4ed',
        scaleMargins: { top: 0.05, bottom: 0.05 },
      },
      timeScale: {
        borderColor: '#dfe4ed',
        timeVisible: false,
      },
      handleScroll: interactive ? { vertTouchDrag: false } : false,
      handleScale: interactive ? { axisPressedMouseMove: true } : false,
    })

    const candleSeries = priceChart.addSeries(CandlestickSeries, {
      upColor: '#059669',
      downColor: '#dc2626',
      borderUpColor: '#059669',
      borderDownColor: '#dc2626',
      wickUpColor: '#059669',
      wickDownColor: '#dc2626',
    })

    const candleData: CandlestickData[] = data.map(d => ({
      time: toTime(d),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }))
    candleSeries.setData(candleData)

    // ---- Volume Chart ----
    const volChart = createChart(volRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#94a3b8',
        fontSize: 10,
      },
      grid: {
        vertLines: { color: '#f0f2f7' },
        horzLines: { color: '#f0f2f7' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#94a3b8', width: 1, style: 2, labelBackgroundColor: '#475569' },
        horzLine: { color: '#94a3b8', width: 1, style: 2, labelBackgroundColor: '#475569' },
      },
      rightPriceScale: {
        borderColor: '#dfe4ed',
        scaleMargins: { top: 0.1, bottom: 0 },
      },
      timeScale: {
        borderColor: '#dfe4ed',
        timeVisible: false,
        visible: true,
      },
      handleScroll: interactive ? { vertTouchDrag: false } : false,
      handleScale: interactive ? { axisPressedMouseMove: true } : false,
    })

    const volSeries = volChart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'right',
    })

    const volData: HistogramData[] = data.map(d => ({
      time: toTime(d),
      value: d.volume,
      color: d.close >= d.open ? 'rgba(5,150,105,0.35)' : 'rgba(220,38,38,0.35)',
    }))
    volSeries.setData(volData)

    // ---- Sync time ranges ----
    const priceTS = priceChart.timeScale()
    const volTS = volChart.timeScale()
    priceTS.subscribeVisibleLogicalRangeChange(range => {
      if (range) volTS.setVisibleLogicalRange(range)
    })
    volTS.subscribeVisibleLogicalRangeChange(range => {
      if (range) priceTS.setVisibleLogicalRange(range)
    })

    // ---- Crosshair move → update OHLCV display ----
    priceChart.subscribeCrosshairMove(param => {
      if (param.time) {
        const point = data.find(d => toTime(d) === param.time)
        if (point) setOhlc(point)
      }
    })
    volChart.subscribeCrosshairMove(param => {
      if (param.time) {
        const point = data.find(d => toTime(d) === param.time)
        if (point) setOhlc(point)
      }
    })

    // ---- Double-click drill-down ----
    if (interactive && onBarDoubleClick) {
      priceChart.subscribeDblClick(param => {
        if (param.time) {
          const point = data.find(d => toTime(d) === param.time)
          if (point) onBarDoubleClick!(toDateStr(point))
        }
      })
    }

    // Auto-fit content
    priceTS.fitContent()
    volTS.fitContent()

    return () => {
      priceChart.remove()
      volChart.remove()
    }
  }, [data, interactive])

  const last = data[data.length - 1]
  const display = ohlc || last

  return (
    <div className="card p-0 overflow-hidden">
      {title && (
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          <div className="flex items-center gap-4">
            {interactive && onBarDoubleClick && (
              <span className="text-[10px] text-accent-cyan/70 font-mono">💡 双击K线查看分钟线</span>
            )}
            {display && (
              <div className="flex gap-3 text-[11px] font-mono">
                <span className="text-text-muted">O:<span className="text-text-primary ml-0.5">{display.open.toFixed(2)}</span></span>
                <span className="text-text-muted">H:<span className="text-text-primary ml-0.5">{display.high.toFixed(2)}</span></span>
                <span className="text-text-muted">L:<span className="text-text-primary ml-0.5">{display.low.toFixed(2)}</span></span>
                <span className={`ml-0.5 font-semibold ${display.close >= display.open ? 'text-profit' : 'text-loss'}`}>
                  C:{display.close.toFixed(2)}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
      {/* Price */}
      <div ref={priceRef} style={{ height: height * 0.7 }} />
      {/* Volume */}
      <div ref={volRef} style={{ height: height * 0.25 }} />
    </div>
  )
}
