import { Card, Col, Row, Statistic, Typography, Table, Collapse, Button, Breadcrumb, Select, Switch, Space } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import { inferRunStage, parsePromptVersions, stageLabel } from '../lib/system'
import { useSystemLabel } from '../lib/useSystems'
import { pnlColor, pnlArrow, KindBadge } from '../lib/ui'
import TranscriptTimeline from '../components/TranscriptTimeline'
import LiveSteps from '../components/LiveSteps'

const PAGE = 30   // 轮次列表渐进加载步长

export default function RunDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const sysLabel = useSystemLabel()
  const run = useQuery({
    queryKey: ['run', id],
    queryFn: () => get(`/runs/${id}`),
    refetchInterval: (q) => q.state.data?.status === 'running' ? 10_000 : false,
  })
  const [selected, setSelected] = useState<number>(0)
  const [follow, setFollow] = useState(true)      // 追盘:新轮自动跟随
  const [shown, setShown] = useState(PAGE)        // 列表显示最近 N 轮
  const [jumpVal, setJumpVal] = useState<number | undefined>(undefined)
  const isRunning = () => run.data?.status === 'running'
  const rounds = useQuery({
    queryKey: ['rounds', id],
    queryFn: () => get(`/runs/${id}/rounds`),
    refetchInterval: () => (isRunning() ? 10_000 : false),
  })
  const lastN = rounds.data?.rounds?.at(-1)?.n ?? 0
  const selectedRound = (rounds.data?.rounds ?? []).find((x: any) => x.n === selected)
  useEffect(() => {
    if (lastN && follow) setSelected(lastN)   // 跟随开:始终锚定最新轮
  }, [lastN, follow])
  /** 选轮:点非最新轮自动关跟随(翻历史不被新轮拽走) */
  function pickRound(n: number) {
    setSelected(n)
    setFollow(n === lastN)
    // 该轮不在当前窗口 → 扩窗到包含它
    const desc = [...(rounds.data?.rounds ?? [])].reverse()
    const idx = desc.findIndex(x => x.n === n)
    if (idx >= shown) setShown(idx + 1)
  }
  const round = useQuery({
    queryKey: ['round', id, selected],
    queryFn: () => get(`/runs/${id}/rounds/${selected}`),
    enabled: selected > 0,
  })
  const trading = useQuery({
    queryKey: ['runTrading', id],
    queryFn: () => get(`/runs/${id}/trading`),
    refetchInterval: () => (isRunning() ? 10_000 : false),
  })


  if (run.isLoading) return <Card>加载中…</Card>
  if (run.error) return <Card>{(run.error as any).message}</Card>
  const r = run.data
  const runStage = inferRunStage(r, r.system)

  return (
    <div>
      {/* 面包屑:系统 → 阶段 → 本场,不迷路 */}
      <Breadcrumb style={{ marginBottom: 12 }} items={[
        { title: <Link to={`/systems/${encodeURIComponent(r.system)}`}>{sysLabel(r.system)}</Link> },
        ...(runStage ? [{ title: <Link to={`/systems/${encodeURIComponent(r.system)}/stage/${encodeURIComponent(runStage)}/runs`}>{stageLabel(runStage)}</Link> }] : []),
        { title: `#${r.id}` },
      ]} />

      {/* 场次头:名称 + 类型/状态徽章 + 讨论入口 */}
      <div className="run-hero">
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            {r.slug}
            <KindBadge kind={r.kind} />
            <span className={`st-badge ${r.status === 'running' ? 'st-run' : 'st-ok'}`}>
              {r.status === 'running' && <span className="rd-live">●</span>}
              {r.status === 'running' ? '执行中' : r.status === 'stopping' ? '停止中' : '已封场'}
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }} className="num">
            {r.trade_date} · {runStage ? stageLabel(runStage) : ''} · #{r.id}
          </div>
        </div>
        <Button type="primary" ghost onClick={() =>
          nav(`/systems/${encodeURIComponent(r.system)}/coach?new=1&runs=${r.id}`)}>💬 讨论结果</Button>
      </div>

      {/* 指标带:收益/资产是主角(大号),其余次级;红涨绿跌 */}
      {r.metrics ? (
        <div className="metric-row">
          <div className="metric-card grow">
            <div className="metric-label">收益</div>
            <div className="metric-value primary num" style={{ color: pnlColor(r.metrics.return_pct) }}>
              {pnlArrow(r.metrics.return_pct)} {Math.abs(r.metrics.return_pct)}%
            </div>
          </div>
          <div className="metric-card grow">
            <div className="metric-label">期末资产</div>
            <div className="metric-value primary num">¥{Number(r.metrics.asset ?? 0).toLocaleString()}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">最大回撤</div>
            <div className="metric-value num">{r.metrics.max_drawdown_pct}%</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">胜率</div>
            <div className="metric-value num">{r.metrics.win_rate ?? '-'}%</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">交易</div>
            <div className="metric-value num">{r.metrics.n_fills}<span className="metric-label"> 笔</span></div>
          </div>
          <div className="metric-card">
            <div className="metric-label">平仓回合</div>
            <div className="metric-value num">{r.metrics.realized_trades}</div>
          </div>
        </div>
      ) : (
        <div className="metric-row" style={{ gridTemplateColumns: '1fr' }}><div className="metric-card grow">
          <Typography.Text type="secondary">本场无封场指标(进行中或老场)</Typography.Text>
        </div></div>
      )}

      {/* ▼ 场次三段(输入/过程/产出)▼ */}

      {/* 📥 输入:本场执行用了什么(prompt 版本快照=指纹,可精确重放) */}
      <div className="run-section">
        <div className="run-section-head">📥 输入 · 本场用了什么</div>
        {Object.entries(parsePromptVersions(r.prompt_versions)).map(([slug, ver]: any) => (
          <div className="run-io-row" key={slug} style={{ cursor: 'pointer' }}
               onClick={() => nav(`/systems/${encodeURIComponent(r.system)}/workbench/prompt/${encodeURIComponent(slug)}?v=${ver}&from=${r.id}`)}>
            <span className="k">📄 {slug}</span>
            <span className="d">版本 v{ver}(不可变快照)</span>
            <span className="a"><span className="lbtn">看此版本 ↗</span></span>
          </div>
        ))}
        {r.kind === 'replay' && (
          <div className="run-io-row" style={{ borderStyle: 'dashed', background: 'transparent', boxShadow: 'none' }}>
            <span className="k">📖 开局快照</span>
            <span className="d">知识/钱包从实盘复制 · 全状态指纹 {r.fingerprint || '-'}</span>
          </div>
        )}
      </div>

      {/* ⚙️ 过程:轮次与思考流 */}
      <div className="run-section-head" style={{ marginTop: 18 }}>⚙️ 过程 · 轮次与思考流</div>

      {/* 📤 产出:本场留下了什么(账本与成交,决策留痕在每笔 reason) */}
      {trading.data && (
        <div className="run-section">
        <div className="run-section-head">📤 产出 · 账本与成交</div>
        <Card title={<span>组合账本 {r.kind === 'live'
          ? <span className="st-badge st-live">实盘组合</span>
          : r.kind === 'single'
          ? <span className="st-badge st-neutral">实盘组合(分析)</span>
          : <span className="st-badge st-run">实验组合 #{trading.data.portfolio}</span>}</span>}
          size="small" style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={4}><Statistic title="现金" prefix="¥" precision={0}
              valueStyle={{ fontFamily: 'var(--font-num)' }}
              value={trading.data.cash ?? '-'} /></Col>
            <Col span={4}><Statistic title="初始资金" prefix="¥" precision={0}
              valueStyle={{ fontFamily: 'var(--font-num)' }}
              value={trading.data.initial ?? '-'} /></Col>
          </Row>
          {trading.data.positions?.length > 0 && (
            <Table rowKey="code" size="small" pagination={false} style={{ marginTop: 12 }}
                   dataSource={trading.data.positions}
                   columns={[
                     { title: '代码', dataIndex: 'code', width: 80 },
                     { title: '名称', dataIndex: 'name' },
                     { title: '数量', dataIndex: 'quantity', width: 70 },
                     { title: '可卖', dataIndex: 'sellable', width: 60 },
                     { title: '成本', dataIndex: 'avg_cost', width: 80 },
                     { title: '买入日', dataIndex: 'bought_on', width: 100 },
                   ]} />
          )}
          {trading.data.fills?.length > 0 && (
            <Collapse style={{ marginTop: 12 }} items={[{
              key: 'fills',
              label: `成交明细(${trading.data.fills.length} 笔)`,
              children: (
                <Table rowKey="id" size="small" pagination={false}
                       dataSource={[...trading.data.fills].reverse()}
                       columns={[
                         { title: '时间', width: 130,
                           render: (_: any, f: any) => (f.trade_time || f.created_at || '').slice(5, 16) },
                         { title: '方向', dataIndex: 'side', width: 50,
                           render: (s: string) => (
                             <span className={`st-badge ${s === 'BUY' ? 'st-live' : 'st-ok'}`}>{s === 'BUY' ? '买入' : '卖出'}</span>
                           ) },
                         { title: '标的', render: (_: any, f: any) => `${f.name || f.code}(${f.code})` },
                         { title: '数量', dataIndex: 'quantity', width: 70 },
                         { title: '价格', className: 'num', render: (_: any, f: any) => `¥${(f.price_cents / 100).toFixed(2)}` },
                         { title: '决策留痕', dataIndex: 'reason',
                           render: (v: string) => <Typography.Text type="secondary" style={{ fontSize: 12 }}>{v}</Typography.Text> },
                       ]} />
              ),
            }]} />
          )}
        </Card>
        </div>
      )}

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={5}>
          <Card title={`轮次 ${lastN ? `(共 ${lastN})` : ''}`} size="small"
                styles={{ body: { padding: '6px 8px' } }}>
            {/* 追盘工具行:跟随最新 + 轮号跳转 */}
            <Space direction="vertical" size={6} style={{ width: '100%', marginBottom: 6 }}>
              {isRunning() && (
                <Space size={6}>
                  <Switch size="small" checked={follow} onChange={setFollow} />
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>跟随最新</Typography.Text>
                </Space>
              )}
              <Select size="small" showSearch value={jumpVal} placeholder="跳转到轮次…"
                      style={{ width: '100%' }}
                      options={[...(rounds.data?.rounds ?? [])].reverse().map((x: any) => ({
                        value: x.n, label: `r${x.n}`,
                      }))}
                      filterOption={(input, option) =>
                        String(option?.value ?? '').includes(input.replace(/\D/g, ''))}
                      onChange={(n) => { pickRound(n); setJumpVal(undefined) }} />
            </Space>
            {/* 紧凑倒序列表:时间 + 轮号,最新在顶;进行中轮带 ● */}
            <div className="rd-rounds">
              {[...(rounds.data?.rounds ?? [])].reverse().slice(0, shown).map((x: any) => (
                <div key={x.n}
                     className={`rd-round${x.n === selected ? ' sel' : ''}${x.n === lastN ? ' latest' : ''}`}
                     onClick={() => pickRound(x.n)}>
                  <span className="rd-time">{x.time || '--:--'}</span>
                  <span>r{x.n}</span>
                  {x.in_progress && <span className="rd-live">●</span>}
                  {!x.has_transcript && !x.in_progress && <span className="rd-note">无思考流</span>}
                </div>
              ))}
            </div>
            {shown < (rounds.data?.rounds?.length ?? 0) && (
              <Button size="small" block style={{ marginTop: 6 }} onClick={() => setShown(s => s + PAGE)}>
                加载更早({(rounds.data?.rounds?.length ?? 0) - shown} 轮)
              </Button>
            )}
          </Card>
        </Col>
        <Col span={19}>
          {selected > 0 ? (
            selectedRound?.in_progress
              ? <LiveSteps runId={r.id} />
              : <TranscriptTimeline
                  loading={round.isLoading}
                  steps={round.data?.steps ?? []}
                  logMd={round.data?.log_md}
                  usage={round.data?.usage} />
          ) : <Card>选择左侧轮次查看详情</Card>}
        </Col>
      </Row>

    </div>
  )
}
