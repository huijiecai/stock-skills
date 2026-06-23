import { useState } from 'react'
import { indices, blockRank, limitLadder, marketTemp, dailyKline, minuteKline, minuteKline5, stockList, blockMembers, indexMinuteKline, indexIntraday, stockIntraday, tradingDays } from '../data/mock'
import StockChartPanel from '../components/StockChartPanel'
import Modal from '../components/Modal'
import CalendarPicker from '../components/CalendarPicker'
import { BarChart3, Layers, Thermometer, ChevronRight, Calendar } from 'lucide-react'

type ModalState =
  | { type: 'none' }
  | { type: 'index'; name: string }
  | { type: 'block'; name: string }
  | { type: 'stock'; code: string }

function IndexCard({ idx, onClick }: { idx: typeof indices[0]; onClick: () => void }) {
  const isUp = idx.change >= 0
  const color = isUp ? 'text-profit' : 'text-loss'
  const bg = isUp ? 'bg-profit/5' : 'bg-loss/5'
  const border = isUp ? 'border-profit/20' : 'border-loss/20'

  return (
    <div
      onClick={onClick}
      className={`card ${bg} border ${border} cursor-pointer hover:scale-[1.02] transition-transform active:scale-[0.98]`}
    >
      <div className="flex items-start justify-between mb-2">
        <span className="text-xs text-text-muted">{idx.name}</span>
        <ChevronRight className="w-3.5 h-3.5 text-text-muted/50" />
      </div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{idx.price.toFixed(2)}</div>
      <div className="flex items-center justify-between mt-2">
        <span className={`text-xs font-mono ${color}`}>{isUp ? '+' : ''}{idx.change}%</span>
        <span className="text-[10px] text-text-muted font-mono">成交 {idx.amount}</span>
      </div>
    </div>
  )
}

/** K-line modal content with StockChartPanel (雪球风格) */
function KlineModalContent({ name, isIndex }: { name: string; isIndex?: boolean }) {
  return (
    <StockChartPanel
      name={name}
      dailyData={dailyKline}
      intradayData={isIndex ? indexIntraday : stockIntraday}
      minuteData={isIndex ? indexMinuteKline : minuteKline}
      minuteData5={isIndex ? undefined : minuteKline5}
      preClose={isIndex ? 3375.0 : 137.8}
      tradingDays={tradingDays}
      height={420}
    />
  )
}

/** Block modal: StockChartPanel + members list */
function BlockModalContent({ blockName }: { blockName: string }) {
  const members = blockMembers[blockName] || []

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-5 gap-5">
        {/* K-line (3/5 width) */}
        <div className="col-span-3">
          <StockChartPanel
            name={blockName}
            dailyData={dailyKline}
            intradayData={stockIntraday}
            minuteData={minuteKline}
            minuteData5={minuteKline5}
            preClose={137.8}
            tradingDays={tradingDays}
            height={380}
          />
        </div>
        {/* Members (2/5 width) */}
        <div className="col-span-2 card">
          <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">板块成员 ({members.length})</h3>
          <div className="space-y-1 max-h-[340px] overflow-y-auto">
            {members.map(m => {
              const isUp = m.change >= 0
              return (
                <div key={m.code} className="flex items-center justify-between py-2 px-2 rounded-lg hover:bg-surface-overlay/50 transition-colors">
                  <div>
                    <div className="text-sm text-text-primary flex items-center gap-1.5">
                      {m.name}
                      {m.limitUp && <span className="tag bg-loss/10 text-loss text-[10px]">涨停</span>}
                    </div>
                    <div className="text-[10px] font-mono text-text-muted">{m.code}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-mono text-text-primary">¥{m.price.toFixed(2)}</div>
                    <div className={`text-[11px] font-mono ${isUp ? 'text-profit' : 'text-loss'}`}>
                      {isUp ? '+' : ''}{m.change}%
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Market() {
  const [modal, setModal] = useState<ModalState>({ type: 'none' })
  const [selectedDate, setSelectedDate] = useState(tradingDays[tradingDays.length - 1])
  const [calendarOpen, setCalendarOpen] = useState(false)

  const tempColor = marketTemp.score >= 70 ? 'text-loss' : marketTemp.score >= 50 ? 'text-accent-amber' : 'text-profit'
  const tempBg = marketTemp.score >= 70 ? 'bg-loss' : marketTemp.score >= 50 ? 'bg-accent-amber' : 'bg-profit'

  const closeModal = () => setModal({ type: 'none' })

  return (
    <div className="p-6 space-y-6">
      {/* Header with date picker */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-xl font-semibold text-text-primary">行情数据</h1>
            <p className="text-xs text-text-muted mt-0.5 font-mono">TDX 直连 · 免费数据 · 点击指数/板块查看K线</p>
          </div>
          <button
            onClick={() => setCalendarOpen(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20 hover:bg-accent-cyan/20 transition-colors"
          >
            <Calendar className="w-4 h-4" />
            <span className="text-sm font-mono font-medium">{selectedDate}</span>
          </button>
        </div>
      </div>

      {/* Indices - clickable */}
      <div className="grid grid-cols-3 gap-4">
        {indices.map(idx => (
          <IndexCard key={idx.code} idx={idx} onClick={() => setModal({ type: 'index', name: idx.name })} />
        ))}
      </div>

      <div className="grid grid-cols-5 gap-6">
        {/* Block Rankings - clickable */}
        <div className="col-span-3">
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="w-3.5 h-3.5 text-accent-cyan" />
              <h2 className="text-sm font-semibold text-text-primary">板块涨幅 TOP10</h2>
              <span className="text-[10px] text-text-muted ml-auto">点击查看成员和K线</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-dim text-left">
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">#</th>
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">板块</th>
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">涨幅</th>
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">涨停</th>
                  <th className="pb-2 text-[10px] uppercase tracking-wider text-text-muted font-medium text-right">成交额</th>
                  <th className="pb-2 w-8"></th>
                </tr>
              </thead>
              <tbody>
                {blockRank.map((b, i) => (
                  <tr
                    key={b.name}
                    onClick={() => setModal({ type: 'block', name: b.name })}
                    className="border-b border-border-dim/50 last:border-0 hover:bg-surface-overlay/50 transition-colors cursor-pointer group"
                  >
                    <td className="py-2.5 text-xs font-mono text-text-muted">{i + 1}</td>
                    <td className="py-2.5 text-sm text-text-primary group-hover:text-accent-cyan transition-colors">{b.name}</td>
                    <td className="py-2.5 text-right">
                      <span className={`text-sm font-mono ${b.change >= 0 ? 'text-profit' : 'text-loss'}`}>
                        {b.change >= 0 ? '+' : ''}{b.change}%
                      </span>
                    </td>
                    <td className="py-2.5 text-right">
                      {b.limitUp > 0 ? <span className="tag bg-loss/10 text-loss">{b.limitUp}</span> : <span className="text-xs text-text-muted">-</span>}
                    </td>
                    <td className="py-2.5 text-right text-xs font-mono text-text-muted">{b.amount}</td>
                    <td className="py-2.5 text-right">
                      <ChevronRight className="w-3.5 h-3.5 text-text-muted/30 group-hover:text-accent-cyan transition-colors" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right Column */}
        <div className="col-span-2 space-y-6">
          {/* Limit Ladder */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="w-3.5 h-3.5 text-accent-amber" />
              <h2 className="text-sm font-semibold text-text-primary">涨停天梯</h2>
            </div>
            <div className="space-y-2">
              {limitLadder.map(ladder => (
                <div key={ladder.level} className="flex items-center gap-3">
                  <div className={`w-10 h-8 rounded-md flex items-center justify-center text-xs font-bold font-mono ${
                    ladder.level >= 4 ? 'bg-loss/20 text-loss' : ladder.level >= 3 ? 'bg-accent-amber/20 text-accent-amber' : 'bg-surface-overlay text-text-secondary'
                  }`}>{ladder.level}板</div>
                  <div className="flex-1 flex flex-wrap gap-1">
                    {ladder.stocks.map(stock => (
                      <span key={stock} onClick={() => setModal({ type: 'stock', code: stock })} className="text-[11px] px-1.5 py-0.5 rounded bg-surface-overlay text-text-primary hover:text-accent-cyan cursor-pointer transition-colors">{stock}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Market Temperature */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Thermometer className="w-3.5 h-3.5 text-loss" />
              <h2 className="text-sm font-semibold text-text-primary">市场温度</h2>
            </div>
            <div className="relative h-3 bg-surface-overlay rounded-full mb-3 overflow-hidden">
              <div className={`absolute left-0 top-0 h-full rounded-full transition-all duration-500 ${tempBg}`} style={{ width: `${marketTemp.score}%` }} />
            </div>
            <div className="flex items-center justify-between mb-4">
              <span className={`text-2xl font-bold font-mono ${tempColor}`}>{marketTemp.score}</span>
              <span className={`tag ${tempColor} bg-surface-overlay`}>{marketTemp.level}</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-surface-overlay rounded-lg p-2.5 text-center">
                <div className="text-sm font-bold text-profit font-mono">{marketTemp.upCount}</div>
                <div className="text-[10px] text-text-muted">上涨</div>
              </div>
              <div className="bg-surface-overlay rounded-lg p-2.5 text-center">
                <div className="text-sm font-bold text-loss font-mono">{marketTemp.downCount}</div>
                <div className="text-[10px] text-text-muted">下跌</div>
              </div>
              <div className="bg-surface-overlay rounded-lg p-2.5 text-center">
                <div className="text-sm font-bold text-loss font-mono">{marketTemp.limitUpCount}</div>
                <div className="text-[10px] text-text-muted">涨停</div>
              </div>
              <div className="bg-surface-overlay rounded-lg p-2.5 text-center">
                <div className="text-sm font-bold text-text-muted font-mono">{marketTemp.brokenRate}%</div>
                <div className="text-[10px] text-text-muted">炸板率</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* === MODALS === */}

      {/* Index K-line Modal */}
      <Modal open={modal.type === 'index'} onClose={closeModal} title={modal.type === 'index' ? modal.name : ''} size="lg">
        {modal.type === 'index' && <KlineModalContent name={modal.name} isIndex />}
      </Modal>

      {/* Block Detail Modal */}
      <Modal open={modal.type === 'block'} onClose={closeModal} title={modal.type === 'block' ? modal.name : ''} size="lg">
        {modal.type === 'block' && <BlockModalContent blockName={modal.name} />}
      </Modal>

      {/* Stock K-line Modal */}
      <Modal open={modal.type === 'stock'} onClose={closeModal} title={modal.type === 'stock' ? `${modal.code} K线` : ''} size="lg">
        {modal.type === 'stock' && <KlineModalContent name={modal.code} />}
      </Modal>

      {/* Calendar Modal */}
      <Modal open={calendarOpen} onClose={() => setCalendarOpen(false)} title="选择交易日" size="sm">
        <CalendarPicker
          selectedDate={selectedDate}
          onSelect={(d) => { setSelectedDate(d); setCalendarOpen(false) }}
          tradingDays={tradingDays}
        />
      </Modal>
    </div>
  )
}
