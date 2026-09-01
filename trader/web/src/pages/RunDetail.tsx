import { Card, Col, Row, Statistic, Typography, Table, Collapse, Button, Breadcrumb, Select, Switch, Space, Modal } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import type { RunRow, RoundsOverview, RoundDetail as RoundDetailData,
             RunTrading, RunDocumentRow, RunDocumentContent, FillRow } from '../api/types'
import { inferRunStage, parsePromptVersions, stageLabel } from '../lib/system'
import { OP, STATUS } from '../lib/icons'
import { useSystemLabel } from '../lib/useSystems'
import { pnlColor, pnlArrow, KindBadge, RunStatusBadge, StatusBadge, PageState, metric } from '../lib/ui'

/** 阶段契约的输入/产出声明(动态内层结构,ADR-0014 透传;消费面按需声明)。 */
interface IOSpec {
  label?: string
  from?: string | { stage?: string; output?: string }
  required?: boolean
  doc_type?: string
}
import TranscriptTimeline from './TranscriptTimeline'
import LiveSteps from './LiveSteps'
import RunDiscussion from './RunDiscussion'
import './RunDetail.css'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const PAGE = 30   // 轮次列表渐进加载步长

export default function RunDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const sysLabel = useSystemLabel()
  const run = useQuery({
    queryKey: ['run', id],
    queryFn: () => get<RunRow>(`/runs/${id}`),
    refetchInterval: (q) => q.state.data?.status === 'running' ? 10_000 : false,
  })
  const [selected, setSelected] = useState<number>(0)
  const [follow, setFollow] = useState(true)      // 追盘:新轮自动跟随
  const [shown, setShown] = useState(PAGE)        // 列表显示最近 N 轮
  const [jumpVal, setJumpVal] = useState<number | undefined>(undefined)
  const [openedDoc, setOpenedDoc] = useState<RunDocumentRow | null>(null)
  const [discussionOpen, setDiscussionOpen] = useState(false)
  const isRunning = () => run.data?.status === 'running'
  const rounds = useQuery({
    queryKey: ['rounds', id],
    queryFn: () => get<RoundsOverview>(`/runs/${id}/rounds`),
    refetchInterval: () => (isRunning() ? 10_000 : false),
  })
  const lastN = rounds.data?.rounds?.at(-1)?.n ?? 0
  const selectedRound = (rounds.data?.rounds ?? []).find((x) => x.n === selected)
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
    queryFn: () => get<RoundDetailData>(`/runs/${id}/rounds/${selected}`),
    enabled: selected > 0,
  })
  const trading = useQuery({
    queryKey: ['runTrading', id],
    queryFn: () => get<RunTrading>(`/runs/${id}/trading`),
    refetchInterval: () => (isRunning() ? 10_000 : false),
  })
  const documents = useQuery({
    queryKey: ['runDocuments', id],
    queryFn: () => get<RunDocumentRow[]>(`/runs/${id}/documents`),
    refetchInterval: () => (isRunning() ? 10_000 : false),
  })


  if (run.isLoading || run.error) return <PageState query={run} />
  const r = run.data!
  const systemSlug = r.system ?? ''   // system 是 LEFT JOIN 列,场次上实际恒有
  const runStage = inferRunStage(r, systemSlug)
  const promptVersions = Object.entries(parsePromptVersions(r.prompt_versions))
  const instruction = String(r.run_inputs?.instruction ?? '').trim()
  const inputDocs = (documents.data ?? []).filter((d) => d.relation === 'input')
  const inputDefs = Object.entries((r.stage_contract?.inputs ?? {}) as Record<string, IOSpec>)
  const outputDefs = Object.entries((r.stage_contract?.outputs ?? {}) as Record<string, IOSpec>)
  const allBusinessOutputs = (documents.data ?? []).filter((d) => d.relation === 'output'
    && !d.doc_type.startsWith('transcript_'))
  const outputDocs = outputDefs.length
    ? allBusinessOutputs.filter((d) => !d.slot)
    : allBusinessOutputs.filter((d) => !d.doc_type.startsWith('watch_'))
  /** 有 slot 的输入按 slot 分组:loop 场每轮回看上一轮产物(recent_decisions),
   *  264 轮就是 264 行平铺淹没输入区 → 同 slot >3 份折叠一行(与产出区聚合对称)。 */
  const inputSlots = new Map<string, RunDocumentRow[]>()
  for (const d of inputDocs) {
    if (d.slot) inputSlots.set(d.slot, [...(inputSlots.get(d.slot) ?? []), d])
  }
  const looseInputs = inputDocs.filter((d) => !d.slot)

  return (
    <div>
      {/* 面包屑:系统 → 新工作台 → 本场,不再回跳旧阶段页。 */}
      <Breadcrumb style={{ marginBottom: 12 }} items={[
        { title: <Link to={`/systems/${encodeURIComponent(systemSlug)}`}>{sysLabel(systemSlug)}</Link> },
        { title: <Link to={`/systems/${encodeURIComponent(systemSlug)}/workbench`}>工作台</Link> },
        ...(runStage ? [{ title: stageLabel(runStage) }] : []),
        { title: `#${r.id}` },
      ]} />

      {/* 场次头:名称 + 类型/状态徽章 + 讨论入口 */}
      <div className="run-hero">
        <div>
          <div style={{ fontSize: 20, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            {r.slug}
            <KindBadge kind={r.kind} />
            <RunStatusBadge r={r} runningText="执行中" />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }} className="num">
            {r.trade_date} · {runStage ? stageLabel(runStage) : ''} · #{r.id}
          </div>
        </div>
        <Space size={8} wrap>
          <Button type="primary" onClick={() => setDiscussionOpen(true)}><OP.chat /> 继续讨论</Button>
          <Button onClick={() =>
            nav(`/systems/${encodeURIComponent(systemSlug)}/coach?new=1&runs=${r.id}`)}>教练复盘</Button>
        </Space>
      </div>

      {/* 失败红条:单次阶段失败不再伪装成完成(引擎会把错误写进 metrics) */}
      {typeof r.metrics?.error === 'string' && r.metrics.error && (
        <div style={{ background: 'var(--danger-bg)', border: '1px solid var(--danger-border)', borderRadius: 10,
                      padding: '10px 14px', marginBottom: 12, color: 'var(--danger)', fontSize: 13 }}>
          <STATUS.fail /> 本场执行失败:{String(r.metrics.error)}
        </div>
      )}

      {/* 指标带:收益/资产是主角(大号),其余次级;红涨绿跌 */}
      {r.metrics && !r.metrics.error ? (
        <div className="metric-row">
          <div className="metric-card grow">
            <div className="metric-label">收益</div>
            <div className="metric-value primary num" style={{ color: pnlColor(metric(r, 'return_pct')) }}>
              {pnlArrow(metric(r, 'return_pct'))} {Math.abs(metric(r, 'return_pct') ?? 0)}%
            </div>
          </div>
          <div className="metric-card grow">
            <div className="metric-label">期末资产</div>
            <div className="metric-value primary num">¥{(metric(r, 'asset') ?? 0).toLocaleString()}</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">最大回撤</div>
            <div className="metric-value num">{metric(r, 'max_drawdown_pct') ?? '-'}%</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">胜率</div>
            <div className="metric-value num">{metric(r, 'win_rate') ?? '-'}%</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">交易</div>
            <div className="metric-value num">{metric(r, 'n_fills') ?? 0}<span className="metric-label"> 笔</span></div>
          </div>
          <div className="metric-card">
            <div className="metric-label">平仓回合</div>
            <div className="metric-value num">{metric(r, 'realized_trades') ?? '-'}</div>
          </div>
        </div>
      ) : (
        <div className="metric-row" style={{ gridTemplateColumns: '1fr' }}><div className="metric-card grow">
          <Typography.Text type="secondary">本场无封场指标(进行中或老场)</Typography.Text>
        </div></div>
      )}

      {/* ▼ 场次三段(输入/过程/产出)▼ */}

      {/* 输入:本场执行用了什么(prompt 版本快照=指纹,可精确重放) */}
      <div className="run-section">
        <div className="run-section-head"><OP.input /> 输入 · 本场用了什么</div>
        {instruction && (
          <div className="run-io-row">
            <span className="k"><OP.task /> 本次任务</span>
            <span className="d">{instruction}</span>
            <span className="a"><StatusBadge>运行输入</StatusBadge></span>
          </div>
        )}
        {promptVersions.map(([slug, ver]) => (
          <div className="run-io-row" key={slug} style={{ cursor: 'pointer' }}
               onClick={() => nav(`/systems/${encodeURIComponent(systemSlug)}/workbench/prompt/${encodeURIComponent(slug)}?v=${ver}&from=${r.id}`)}>
            <span className="k"><OP.doc /> {slug}</span>
            <span className="d">版本 v{ver}(不可变快照)</span>
            <span className="a"><span className="lbtn">看此版本 ↗</span></span>
          </div>
        ))}
        {[...inputSlots].flatMap(([slot, docs]) => {
          const spec = inputDefs.find(([s]) => s === slot)?.[1]
          if (docs.length <= 3) return docs.map((d) => (
            <div className="run-io-row" key={`input-${d.id}`} style={{ cursor: 'pointer' }}
                 onClick={() => setOpenedDoc(d)}>
              <span className="k"><OP.lib /> {spec?.label || d.slot || d.name || d.doc_type}</span>
              <span className="d">{d.source_stage && d.source_output ? `${d.source_stage}.${d.source_output} · ` : ''}
                {d.name || d.doc_type}{d.trade_date ? ` · ${d.trade_date}` : ''}{d.round ? ` · r${d.round}` : ''}</span>
              <span className="a"><span className="lbtn">打开 ↗</span></span>
            </div>))
          // 循环引用聚合行:label 用契约里的显示名,点击打开最新引用的那份
          const latest = docs.at(-1)!
          const rs = docs.map((d) => d.round).filter((x) => x > 0)
          const span = rs.length ? ` · 覆盖 r${Math.min(...rs)}–r${Math.max(...rs)}` : ''
          return [(
            <div className="run-io-row" key={`agg-${slot}`} style={{ cursor: 'pointer' }}
                 onClick={() => setOpenedDoc(latest)}
                 title={`每轮回看引用,共 ${docs.length} 份;点击打开最新一份${latest.round ? `(r${latest.round - 1} 的产出)` : ''}`}>
              <span className="k"><OP.lib /> {spec?.label || slot}</span>
              <span className="d">{latest.source_stage && latest.source_output ? `${latest.source_stage}.${latest.source_output} · ` : ''}
                循环引用 {docs.length} 份{span}</span>
              <span className="a"><span className="lbtn">打开最新 ↗</span></span>
            </div>)]
        })}
        {looseInputs.map((d) => (
          <div className="run-io-row" key={`loose-${d.id}`} style={{ cursor: 'pointer' }}
               onClick={() => setOpenedDoc(d)}>
            <span className="k"><OP.lib /> {d.name || d.doc_type}</span>
            <span className="d">{d.source_stage && d.source_output ? `${d.source_stage}.${d.source_output} · ` : ''}
              {d.name || d.doc_type}{d.trade_date ? ` · ${d.trade_date}` : ''}{d.round ? ` · r${d.round}` : ''}</span>
            <span className="a"><span className="lbtn">打开 ↗</span></span>
          </div>
        ))}
        {inputDefs.filter(([slot]) => !inputDocs.some((d) => d.slot === slot)).map(([slot, spec]) => (
          <div className="run-io-row" key={`missing-${slot}`}>
            <span className="k">◇ {spec.label || slot}</span>
            <span className="d">{typeof spec.from === 'string'
              ? spec.from
              : `${spec.from?.stage ?? '?'}.${spec.from?.output ?? '?'}`} · 本场未提供</span>
            <span className="a"><StatusBadge>{spec.required ? '必需' : '可选'}</StatusBadge></span>
          </div>
        ))}
        {documents.isLoading && <Typography.Text type="secondary">正在读取文档证据…</Typography.Text>}
        {documents.error && <Typography.Text type="danger">文档证据读取失败：{(documents.error as Error).message}</Typography.Text>}
        {!instruction && !promptVersions.length && !inputDocs.length && documents.isSuccess && (
          <Typography.Text type="secondary">本场没有记录到指令快照或输入文档。</Typography.Text>
        )}
        {r.clock === 'simulated' && (
          <div className="run-io-row" style={{ borderStyle: 'dashed', background: 'transparent', boxShadow: 'none' }}>
            <span className="k"><OP.read /> 开局快照</span>
            <span className="d">知识/钱包从实盘复制 · 全状态指纹 {r.fingerprint || '-'}</span>
          </div>
        )}
      </div>

      {/* 过程:轮次与思考流 */}
      <div className="run-section-head" style={{ marginTop: 18 }}><OP.settings /> 过程 · 轮次与思考流</div>

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
                      options={[...(rounds.data?.rounds ?? [])].reverse().map((x) => ({
                        value: x.n, label: `r${x.n}`,
                      }))}
                      filterOption={(input, option) =>
                        String(option?.value ?? '').includes(input.replace(/\D/g, ''))}
                      onChange={(n) => { pickRound(n); setJumpVal(undefined) }} />
            </Space>
            {/* 紧凑倒序列表:时间 + 轮号,最新在顶;进行中轮带 ●;连续失败轮红条(引擎在挣扎,不是静默死掉) */}
            <div className="rd-rounds">
              {[...(rounds.data?.rounds ?? [])].reverse().slice(0, shown).map((x) => (
                <div key={x.n}
                     className={`rd-round${x.n === selected ? ' sel' : ''}${x.n === lastN ? ' latest' : ''}${x.failed ? ' failed' : ''}`}
                     onClick={() => pickRound(x.n)}
                     title={x.failed ? x.error : undefined}>
                  <span className="rd-time">{x.time || '--:--'}</span>
                  <span className="rd-round-main">
                    <b>{x.failed ? <>r{x.n} <STATUS.warn style={{ fontSize: 12 }} /></> : `r${x.n}`}</b>
                    {x.failed
                      ? <small className="rd-fail-text">连续失败 {x.failures} 次 · {x.error?.slice(0, 60)}</small>
                      : x.summary && <small>{x.summary}</small>}
                  </span>
                  {x.in_progress && <span className="rd-live">●</span>}
                  {!x.has_transcript && !x.in_progress && !x.failed && <span className="rd-note">无思考流</span>}
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
          ) : <Card><PageState query={rounds} size="panel"
                empty={!(rounds.data?.rounds ?? []).length}
                emptyText="本场没有记录到轮次、工具事件或思考流。" /></Card>}
        </Col>
      </Row>

      {/* 产出:显式文档 + 账本与成交。 */}
      <div className="run-section">
        <div className="run-section-head"><OP.output /> 产出 · 本场留下了什么</div>
        {outputDefs.map(([slot, spec]) => {
          const matched = allBusinessOutputs.filter((d) => d.slot === slot)
          const latest = matched.at(-1)
          return (
            <div className="run-io-row" key={`slot-${slot}`}
                 style={latest ? { cursor: 'pointer' } : undefined}
                 onClick={() => latest && setOpenedDoc(latest)}>
              <span className="k"><OP.doc /> {spec.label || slot}</span>
              <span className="d">{spec.doc_type || '文档'} · {matched.length
                ? `${matched.length} 份实际产出${latest?.name ? ` · 最新 ${latest.name}` : ''}`
                : '尚未产出'}</span>
              <span className="a">{latest && <span className="lbtn">打开最新 ↗</span>}</span>
            </div>
          )
        })}
        {outputDocs.map((d) => (
          <div className="run-io-row" key={`output-${d.id}`} style={{ cursor: 'pointer' }}
               onClick={() => setOpenedDoc(d)}>
            <span className="k"><OP.doc /> {d.name || d.doc_type}</span>
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
            ? <StatusBadge tone="live">实盘组合</StatusBadge>
            : r.kind === 'paper'
            ? <StatusBadge tone="run">模拟组合 #{trading.data.portfolio}</StatusBadge>
            : r.kind === 'single'
            ? <StatusBadge>{r.clock === 'simulated' ? `实验组合 #${trading.data.portfolio}` : '主组合(分析)'}</StatusBadge>
            : <StatusBadge tone="run">实验组合 #{trading.data.portfolio}</StatusBadge>}</span>}
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
                           { title: '时间', width: 130, render: (_: unknown, f: FillRow) => (f.trade_time || f.created_at || '').slice(5, 16) },
                           { title: '方向', dataIndex: 'side', width: 60, render: (s: string) => <StatusBadge tone={s === 'BUY' ? 'live' : 'ok'}>{s === 'BUY' ? '买入' : '卖出'}</StatusBadge> },
                           { title: '标的', render: (_: unknown, f: FillRow) => `${f.name || f.code}(${f.code})` },
                           { title: '数量', dataIndex: 'quantity', width: 70 },
                           { title: '价格', className: 'num', render: (_: unknown, f: FillRow) => `¥${(f.price_cents / 100).toFixed(2)}` },
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
      <RunDiscussion run={r} open={discussionOpen} onClose={() => setDiscussionOpen(false)} />

    </div>
  )
}

function RunDocumentViewer({ runId, doc, onClose }: { runId: number, doc: RunDocumentRow, onClose: () => void }) {
  const content = useQuery({
    queryKey: ['runDocumentContent', runId, doc.id],
    queryFn: () => get<RunDocumentContent>(`/runs/${runId}/documents/${doc.id}`),
  })
  return (
    <Modal open title={doc.name || doc.doc_type} footer={null} width={780} onCancel={onClose}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <StatusBadge>{doc.doc_type}</StatusBadge>
        <Typography.Text type="secondary">{doc.relation === 'input' ? '本场输入' : '本场产出'}{doc.round ? ` · r${doc.round}` : ''}</Typography.Text>
      </div>
      <PageState query={content} size="panel">
        <div className="markdown-body run-doc-content">
          <Markdown remarkPlugins={[remarkGfm]}>{content.data?.content ?? '(无内容)'}</Markdown>
        </div>
      </PageState>
    </Modal>
  )
}
