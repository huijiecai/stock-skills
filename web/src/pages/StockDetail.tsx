import { useParams, useNavigate } from 'react-router-dom'
import { dailyKline, minuteKline, minuteKline5, stockIntraday, stockList, tradingDays } from '../data/mock'
import StockChartPanel from '../components/StockChartPanel'
import { ArrowLeft, Tag } from 'lucide-react'

export default function StockDetail() {
  const { code } = useParams()
  const navigate = useNavigate()

  const stock = stockList.find(s => s.code === code) || stockList[0]
  const isUp = stock.change >= 0

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/market')} className="p-1.5 rounded-lg hover:bg-surface-overlay transition-colors">
          <ArrowLeft className="w-4 h-4 text-text-muted" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-text-primary">{stock.name}</h1>
            <span className="text-xs font-mono text-text-muted">{stock.code}</span>
            <span className="tag bg-accent-cyan/10 text-accent-cyan">{stock.sector}</span>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold font-mono ${isUp ? 'text-profit' : 'text-loss'}`}>
            ¥{stock.price.toFixed(2)}
          </div>
          <div className={`text-sm font-mono ${isUp ? 'text-profit' : 'text-loss'}`}>
            {isUp ? '+' : ''}{stock.change}%
          </div>
        </div>
      </div>

      {/* K-line Chart Panel */}
      <StockChartPanel
        name={stock.name}
        dailyData={dailyKline}
        intradayData={stockIntraday}
        minuteData={minuteKline}
        minuteData5={minuteKline5}
        preClose={137.8}
        tradingDays={tradingDays}
        height={480}
      />

      {/* Stock Info */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card">
          <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">基本信息</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span className="text-xs text-text-muted">代码</span><span className="text-xs font-mono text-text-primary">{stock.code}</span></div>
            <div className="flex justify-between"><span className="text-xs text-text-muted">名称</span><span className="text-xs text-text-primary">{stock.name}</span></div>
            <div className="flex justify-between"><span className="text-xs text-text-muted">板块</span><span className="text-xs text-text-primary">{stock.sector}</span></div>
          </div>
        </div>
        <div className="card">
          <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">今日行情</h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span className="text-xs text-text-muted">现价</span><span className={`text-xs font-mono ${isUp ? 'text-profit' : 'text-loss'}`}>¥{stock.price.toFixed(2)}</span></div>
            <div className="flex justify-between"><span className="text-xs text-text-muted">涨跌幅</span><span className={`text-xs font-mono ${isUp ? 'text-profit' : 'text-loss'}`}>{isUp ? '+' : ''}{stock.change}%</span></div>
            <div className="flex justify-between"><span className="text-xs text-text-muted">成交量</span><span className="text-xs font-mono text-text-primary">{stock.volume.toLocaleString()}</span></div>
          </div>
        </div>
        <div className="card">
          <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3 flex items-center gap-1">
            <Tag className="w-3 h-3" /> AI 视角
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between"><span className="text-xs text-text-muted">预期阶段</span><span className="text-xs text-accent-amber">加速期 Day2⚠️</span></div>
            <div className="flex justify-between"><span className="text-xs text-text-muted">AI持仓</span><span className="text-xs text-profit">50股 +14.8%</span></div>
            <div className="flex justify-between"><span className="text-xs text-text-muted">置信度</span><span className="text-xs text-text-primary">高</span></div>
          </div>
        </div>
      </div>
    </div>
  )
}
