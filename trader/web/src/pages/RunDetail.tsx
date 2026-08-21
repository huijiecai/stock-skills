import { Card, Col, Row, Statistic, Typography, Table, Collapse, Button, Breadcrumb, Select, Switch, Space, Spin, Modal, Tooltip } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import { inferRunStage, parsePromptVersions, stageLabel } from '../lib/system'
import { useSystemLabel } from '../lib/useSystems'
import { pnlColor, pnlArrow, KindBadge, runStalled, heartbeatAge } from '../lib/ui'
import TranscriptTimeline from '../components/TranscriptTimeline'
import LiveSteps from '../components/LiveSteps'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

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
  const [openedDoc, setOpenedDoc] = useState<any | null>(null)
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
  const documents = useQuery({
    queryKey: ['runDocuments', id],
    queryFn: () => get(`/runs/${id}/documents`),
    refetchInterval: () => (isRunning() ? 10_000 : false),
  })


  if (run.isLoading) return <Card>加载中…</Card>
  if (run.error) return <Card>{(run.error as any).message}</Card>
  const r = run.data
  const runStage = inferRunStage(r, r.system)
  const promptVersions = Object.entries(parsePromptVersions(r.prompt_versions))
  const inputDocs = (documents.data ?? []).filter((d: any) => d.relation === 'input')
  const inputDefs = Object.entries(r.stage_contract?.inputs ?? {}) as [string, any][]
  const outputDefs = Object.entries(r.stage_contract?.outputs ?? {}) as [string, any][]
  const allBusinessOutputs = (documents.data ?? []).filter((d: any) => d.relation === 'output'
    && !d.doc_type.startsWith('transcript_'))
  const outputDocs = outputDefs.length
    ? allBusinessOutputs.filter((d: any) => !d.slot)
    : allBusinessOutputs.filter((d: any) => !d.doc_type.startsWith('watch_'))

  return (
    <div>
      {/* 面包屑:系统 → 新工作台 → 本场,不再回跳旧阶段页。 */}
      <Breadcrumb style={{ marginBottom: 12 }} items={[
        { title: <Link to={`/systems/${encodeURIComponent(r.system)}`}>{sysLabel(r.system)}</Link> },
        { title: <Link to={`/systems/${encodeURIComponent(r.system)}/workbench`}>工作台</Link> },
        ...(runStage ? [{ title: stageLabel(runStage) }] : []),
        { title: `#${r.id}` },
      ]} />

      {/* 场次头:名称 + 类型/状态徽章 + 讨论入口 */}
      <div className="run-hero">
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            {r.slug}
            <KindBadge kind={r.kind} />
            {r.status === 'running'
              ? <Tooltip title={runStalled(r)
                  ? `心跳:${heartbeatAge(r)}——进程可能被系统睡眠冻结或已死;可停止并强制封存`
                  : `心跳:${heartbeatAge(r)}`}>
                  <span className={`st-badge ${runStalled(r) ? 'st-stall' : 'st-run'}`}>
                    <span className="rd-live" style={runStalled(r) ? { color: '#d46b08' } : undefined}>●</span>
                    {runStalled(r) ? '疑似僵死' : '执行中'}
                  </span>
                </Tooltip>
              : <span className="st-badge st-ok">{r.status === 'stopping' ? '停止中' : '已封场'}</span>}
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
        {promptVersions.map(([slug, ver]: any) => (
          <div className="run-io-row" key={slug} style={{ cursor: 'pointer' }}
               onClick={() => nav(`/systems/${encodeURIComponent(r.system)}/workbench/prompt/${encodeURIComponent(slug)}?v=${ver}&from=${r.id}`)}>
            <span className="k">📄 {slug}</span>
            <span className="d">版本 v{ver}(不可变快照)</span>
            <span className="a"><span className="lbtn">看此版本 ↗</span></span>
          </div>
        ))}
        {inputDocs.map((d: any) => (
          <div className="run-io-row" key={`input-${d.id}`} style={{ cursor: 'pointer' }}
               onClick={() => setOpenedDoc(d)}>
            <span className="k">📚 {d.slot || d.name || d.doc_type}</span>
            <span className="d">{d.source_stage && d.source_output ? `${d.source_stage}.${d.source_output} · ` : ''}
              {d.name || d.doc_type}{d.trade_date ? ` · ${d.trade_date}` : ''}{d.round ? ` · r${d.round}` : ''}</span>
            <span className="a"><span className="lbtn">打开 ↗</span></span>
          </div>
        ))}
        {inputDefs.filter(([slot]) => !inputDocs.some((d: any) => d.slot === slot)).map(([slot, spec]) => (
          <div className="run-io-row" key={`missing-${slot}`}>
            <span className="k">◇ {spec.label || slot}</span>
            <span className="d">{typeof spec.from === 'string'
              ? spec.from
              : `${spec.from?.stage ?? '?'}.${spec.from?.output ?? '?'}`} · 本场未提供</span>
            <span className="a"><span className="st-badge st-neutral">{spec.required ? '必需' : '可选'}</span></span>
          </div>
        ))}
        {documents.isLoading && <Typography.Text type="secondary">正在读取文档证据…</Typography.Text>}
        {documents.error && <Typography.Text type="danger">文档证据读取失败：{(documents.error as Error).message}</Typography.Text>}
        {!promptVersions.length && !inputDocs.length && documents.isSuccess && (
          <Typography.Text type="secondary">本场没有记录到指令快照或输入文档。</Typography.Text>
        )}
        {r.clock === 'simulated' && (
          <div className="run-io-row" style={{ borderStyle: 'dashed', background: 'transparent', boxShadow: 'none' }}>
            <span className="k">📖 开局快照</span>
            <span className="d">知识/钱包从实盘复制 · 全状态指纹 {r.fingerprint || '-'}</span>
          </div>
        )}
      </div>

      {/* ⚙️ 过程:轮次与思考流 */}
      <div className="run-section-head" style={{ marginTop: 18 }}>⚙️ 过程 · 轮次与思考流</div>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={6} xl={5}>
          <Card title={`轮次 ${lastN ? `(共 ${lastN})` : ''}`} size="small"
                styles={{ body: { padding: '6px 8px' } }}>
            {/* 追盘工具行:跟随最新 + 轮号跳转 */}
            <Space orientation="vertical" size={6} style={{ width: '100%', marginBottom: 6 }}>
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
                  <span className="rd-round-main"><b>r{x.n}</b>{x.summary && <small>{x.summary}</small>}</span>
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
        <Col xs={24} md={18} xl={19}>
          {selected > 0 ? (
            selectedRound?.in_progress
              ? <LiveSteps runId={r.id} />
              : <TranscriptTimeline
                  loading={round.isLoading}
                  steps={round.data?.steps ?? []}
                  logMd={round.data?.log_md}
                  usage={round.data?.usage} />
          ) : rounds.isLoading ? <Card><Spin size="small" /> 正在读取过程…</Card>
            : rounds.error ? <Card><Typography.Text type="danger">过程读取失败：{(rounds.error as Error).message}</Typography.Text></Card>
            : <Card><Typography.Text type="secondary">本场没有记录到轮次、工具事件或思考流。</Typography.Text></Card>}
        </Col>
      </Row>

      {/* 📤 产出:显式文档 + 账本与成交。 */}
      <div className="run-section">
        <div className="run-section-head">📤 产出 · 本场留下了什么</div>
        {outputDefs.map(([slot, spec]) => {
          const matched = allBusinessOutputs.filter((d: any) => d.slot === slot)
          const latest = matched.at(-1)
          return (
            <div className="run-io-row" key={`slot-${slot}`}
                 style={latest ? { cursor: 'pointer' } : undefined}
                 onClick={() => latest && setOpenedDoc(latest)}>
              <span className="k">📄 {spec.label || slot}</span>
              <span className="d">{spec.doc_type || '文档'} · {matched.length
                ? `${matched.length} 份实际产出${latest?.name ? ` · 最新 ${latest.name}` : ''}`
                : '尚未产出'}</span>
              <span className="a">{latest && <span className="lbtn">打开最新 ↗</span>}</span>
            </div>
          )
        })}
        {outputDocs.map((d: any) => (
          <div className="run-io-row" key={`output-${d.id}`} style={{ cursor: 'pointer' }}
               onClick={() => setOpenedDoc(d)}>
            <span className="k">📄 {d.name || d.doc_type}</span>
            <span className="d">{d.doc_type}{d.trade_date ? ` · ${d.trade_date}` : ''}{d.round ? ` · r${d.round}` : ''}</span>
            <span className="a"><span className="lbtn">打开 ↗</span></span>
          </div>
        ))}
        {documents.isSuccess && !outputDocs.length && !outputDefs.length && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            本场尚未留下业务文档。
          </Typography.Text>
        )}
        {trading.data && (
          <Card title={<span>成交与组合状态 {r.kind === 'live'
            ? <span className="st-badge st-live">实盘组合</span>
            : r.kind === 'paper'
            ? <span className="st-badge st-run">模拟组合 #{trading.data.portfolio}</span>
            : r.kind === 'single'
            ? <span className="st-badge st-neutral">{r.clock === 'simulated' ? `实验组合 #${trading.data.portfolio}` : '主组合(分析)'}</span>
            : <span className="st-badge st-run">实验组合 #{trading.data.portfolio}</span>}</span>}
            size="small" style={{ marginTop: 12 }}>
            <Row gutter={16}>
              <Col xs={12} md={4}><Statistic title="现金" prefix="¥" precision={0}
                styles={{ content: { fontFamily: 'var(--font-num)' } }} value={trading.data.cash ?? '-'} /></Col>
              <Col xs={12} md={4}><Statistic title="初始资金" prefix="¥" precision={0}
                styles={{ content: { fontFamily: 'var(--font-num)' } }} value={trading.data.initial ?? '-'} /></Col>
            </Row>
            <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
              成交只显示本场；现金和持仓为该组合当前状态。
            </Typography.Text>
            {trading.data.positions?.length > 0 && (
              <Table rowKey="code" size="small" pagination={false} style={{ marginTop: 12 }}
                     scroll={{ x: 620 }} dataSource={trading.data.positions}
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
                key: 'fills', label: `成交明细(${trading.data.fills.length} 笔)`, children: (
                  <Table rowKey="id" size="small" pagination={false} scroll={{ x: 760 }}
                         dataSource={[...trading.data.fills].reverse()}
                         columns={[
                           { title: '时间', width: 130, render: (_: any, f: any) => (f.trade_time || f.created_at || '').slice(5, 16) },
                           { title: '方向', dataIndex: 'side', width: 60, render: (s: string) => <span className={`st-badge ${s === 'BUY' ? 'st-live' : 'st-ok'}`}>{s === 'BUY' ? '买入' : '卖出'}</span> },
                           { title: '标的', render: (_: any, f: any) => `${f.name || f.code}(${f.code})` },
                           { title: '数量', dataIndex: 'quantity', width: 70 },
                           { title: '价格', className: 'num', render: (_: any, f: any) => `¥${(f.price_cents / 100).toFixed(2)}` },
                           { title: '决策留痕', dataIndex: 'reason', render: (v: string) => <Typography.Text type="secondary" style={{ fontSize: 12 }}>{v}</Typography.Text> },
                         ]} />
                ),
              }]} />
            )}
            {!trading.data.fills?.length && (
              <div style={{ marginTop: 12, color: 'var(--text-3)', fontSize: 12 }}>本场没有成交。</div>
            )}
          </Card>
        )}
        {trading.error && <Typography.Text type="danger">成交证据读取失败：{(trading.error as Error).message}</Typography.Text>}
      </div>

      {openedDoc && <RunDocumentViewer runId={r.id} doc={openedDoc} onClose={() => setOpenedDoc(null)} />}

    </div>
  )
}

function RunDocumentViewer({ runId, doc, onClose }: { runId: number, doc: any, onClose: () => void }) {
  const content = useQuery({
    queryKey: ['runDocumentContent', runId, doc.id],
    queryFn: () => get(`/runs/${runId}/documents/${doc.id}`),
  })
  return (
    <Modal open title={doc.name || doc.doc_type} footer={null} width={780} onCancel={onClose}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <span className="st-badge st-neutral">{doc.doc_type}</span>
        <Typography.Text type="secondary">{doc.relation === 'input' ? '本场输入' : '本场产出'}{doc.round ? ` · r${doc.round}` : ''}</Typography.Text>
      </div>
      {content.isLoading ? <Spin /> : content.error ? (
        <Typography.Text type="danger">{(content.error as Error).message}</Typography.Text>
      ) : (
        <div className="markdown-body run-doc-content">
          <Markdown remarkPlugins={[remarkGfm]}>{content.data?.content ?? '(无内容)'}</Markdown>
        </div>
      )}
    </Modal>
  )
}
