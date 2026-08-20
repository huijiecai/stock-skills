/** 指令台(原型画面八):打开一条指令 ≠ 打开文件——
 * 版本时间线 + 双栏(内容编辑/预览/对比 | 执行史按版本分组) + 引用关系。
 * 路由:/systems/:slug/workbench/prompt/:prompt(_system=系统设定)。 */
import { Button, Input, message, Select, Space, Spin, Tabs, Tag, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, put } from '../api/client'
import { stageIcon, stageLabel, parsePromptVersions } from '../lib/system'
import { pnlColor } from '../lib/ui'
import PromptDiff from './PromptDiff'

export default function PromptWorkbench() {
  const { name = '', prompt = '' } = useParams()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const system = name
  const promptSlug = decodeURIComponent(prompt)

  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}`) })
  const promptsList = useQuery({ queryKey: ['prompts', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}/prompts`) })

  // prompt → 所属阶段(执行史按阶段筛场次)
  const stages: Record<string, any> = detail.data?.manifest?.stages ?? {}
  const stageOf = promptSlug === detail.data?.manifest?.system_prompt
    ? '(system)'
    : Object.entries(stages).find(([, d]: any) => d?.prompt === promptSlug)?.[0] ?? ''

  const [versions, setVersions] = useState<any[]>([])
  const [version, setVersion] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [view, setView] = useState<'preview' | 'edit' | 'diff'>('preview')
  const [dirty, setDirty] = useState(false)
  const [diffA, setDiffA] = useState<number | null>(null)
  const taRef = useRef<any>(null)
  const seedFrom = params.get('from')
  const seedV = params.get('v')

  useEffect(() => {
    if (!promptSlug) return
    ;(async () => {
      const vs: any[] = await get(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}/versions`)
      setVersions(vs)
      if (!vs.length) { setVersion(null); setText(''); return }
      const preferred = seedV && vs.some(v => v.version === Number(seedV)) ? Number(seedV) : vs[0].version
      const r = await get(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}/versions/${preferred}`)
      setVersion(preferred)
      setText(r.content)
      setDirty(false)
      setDiffA(vs[vs.findIndex(v => v.version === preferred) + 1]?.version ?? null)
    })()
  }, [system, promptSlug])

  const content = useQuery({
    queryKey: ['promptContent', system, promptSlug, diffA],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}/versions/${diffA}`).then((r: any) => r.content),
    enabled: view === 'diff' && !!diffA,
  })

  async function pickVersion(v: number) {
    const r = await get(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}/versions/${v}`)
    setVersion(v)
    setText(r.content)
    setDirty(false)
    const idx = versions.findIndex(x => x.version === v)
    setDiffA(versions[idx + 1]?.version ?? null)
  }

  async function save() {
    const r = await put(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}`,
                        { content: text })
    message.success(r.changed ? `已存为新版本 v${r.version}` : '内容未变,不重复入库')
    setDirty(false)
    qc.invalidateQueries({ queryKey: ['prompts', system] })
    const vs: any[] = await get(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}/versions`)
    setVersions(vs)
    setVersion(vs[0].version)
  }

  // ── 执行史:该指令阶段的名下场次,按所用版本分组 ──
  const runs = useQuery({
    queryKey: ['systemRuns', system],
    queryFn: () => get(`/runs?system=${encodeURIComponent(system)}`),
    staleTime: 15000,
  })
  const stageRuns: any[] = (runs.data ?? [])
    .filter((r: any) => (stageOf === '(system)' ? true : r.stage === stageOf))
    .slice(0, 30)
  const byVersion: { v: number | null, rows: any[] }[] = []
  for (const r of stageRuns) {
    const v = parsePromptVersions(r.prompt_versions)[promptSlug] ?? null
    let g = byVersion.find(x => x.v === v)
    if (!g) { g = { v, rows: [] }; byVersion.push(g) }
    g.rows.push(r)
  }

  const latestV = versions[0]?.version
  const verOptions = versions.map((v: any) => ({
    value: v.version,
    label: `v${v.version}${v.version === latestV ? ' (最新·在用)' : ''}`,
  }))

  if (detail.isLoading || promptsList.isLoading) return <Spin style={{ display: 'block', margin: '60px auto' }} />

  return (
    <div className="ws-panel">
      <div className="ws-phead">
        <span style={{ fontSize: 15.5, fontWeight: 700 }}>
          {stageIcon(stageOf)} {stageOf === '(system)' ? '系统设定' : stageLabel(stageOf, stages[stageOf])}
          <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400, marginLeft: 8 }}>.{promptSlug}</Typography.Text>
        </span>
        {version === latestV && latestV != null && <span className="st-badge st-ok">v{latestV} ●在用</span>}
        {seedFrom && <span className="st-badge st-neutral">来自场次 #{seedFrom} 的 v{seedV} 快照</span>}
        <span style={{ color: 'var(--text-3)', fontSize: 11.5, marginLeft: 'auto' }}>
          📜 {promptSlug}</span>
        <Space style={{ marginLeft: 'auto' }}>
          {dirty && <Tag color="orange">未保存</Tag>}
          <Select size="small" style={{ width: 140 }} value={version} onChange={pickVersion}
                  placeholder="版本" options={verOptions} />
          <Button type="primary" size="small" onClick={save} disabled={!dirty || !version}>保存新版本</Button>
        </Space>
      </div>
      <div className="ws-pbody">

      {/* 版本时间线 */}
      <div className="vtimeline">
        {[...versions].reverse().map((v: any, i: number) => (
          <span key={v.version} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            {i > 0 && <span className="varr">──</span>}
            <span className={`vchip${v.version === version ? ' cur' : ''}${v.version === latestV ? ' on' : ''}`}
                  onClick={() => pickVersion(v.version)}>
              v{v.version}{v.version === latestV ? ' ●' : ''}
            </span>
          </span>
        ))}
        {!versions.length && <span style={{ color: 'var(--text-3)', fontSize: 12 }}>还没有版本(编辑后保存生成 v1)</span>}
      </div>

      {/* 双栏:内容 | 执行史 */}
      <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
        <div style={{ flex: 1.45, minWidth: 0 }}>
          <Tabs size="small" activeKey={view} onChange={(k) => setView(k as any)} items={[
            { key: 'preview', label: '👁 预览', forceRender: false,
              children: (
                <div className="md-body">
                  <Markdown remarkPlugins={[remarkGfm]}>{text || '(空)'}</Markdown>
                </div>
              ) },
            { key: 'edit', label: '✏️ 编辑', forceRender: true,
              children: (
                <Input.TextArea ref={taRef} value={text} onChange={(e) => { setText(e.target.value); setDirty(true) }}
                                autoSize={{ minRows: 18, maxRows: 32 }}
                                style={{ fontFamily: 'var(--font-num)', fontSize: 13 }} />
              ) },
            { key: 'diff', label: '🔀 版本对比', forceRender: true,
              children: (
                <div>
                  <Space style={{ marginBottom: 8 }}>
                    <Select size="small" style={{ width: 110 }} value={diffA} onChange={setDiffA}
                            options={versions.filter((v: any) => v.version !== version)
                              .map((v: any) => ({ value: v.version, label: `对比 v${v.version}` }))} />
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>v{diffA} → v{version}(绿增红删)</Typography.Text>
                  </Space>
                  <PromptDiff a={content.data ?? ''} b={text} />
                </div>
              ) },
          ]} />
        </div>

        {/* 执行史(右栏) */}
        <div style={{ flex: 1, minWidth: 240, position: 'sticky', top: 8 }}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
                       boxShadow: 'var(--shadow-card)', padding: '12px 14px' }}>
            <div style={{ fontWeight: 800, fontSize: 13, marginBottom: 8 }}>▎执行史 <span style={{ fontWeight: 400, color: 'var(--text-3)', fontSize: 11.5 }}>改前先看战绩</span></div>
            {byVersion.map(g => (
              <div key={g.v ?? 'none'}>
                <div className="hx-group">v{g.v ?? '-'}{g.v === latestV ? '(在用)' : ''}</div>
                {g.rows.map(r => (
                  <div className="hx-row" key={r.id} onClick={() => nav(`/runs/${r.id}`)}>
                    <span className="num">{(r.trade_date ?? '').slice(5)}</span>
                    <span>{r.status === 'sealed' ? '✓' : '●'}</span>
                    {r.metrics?.return_pct != null && (
                      <span className="num" style={{ color: pnlColor(r.metrics.return_pct) }}>
                        {r.metrics.return_pct > 0 ? '+' : ''}{r.metrics.return_pct}%
                      </span>
                    )}
                    <span className="d">{r.slug?.slice(0, 20)}</span>
                  </div>
                ))}
              </div>
            ))}
            {!stageRuns.length && <div style={{ color: 'var(--text-3)', fontSize: 12, padding: '8px 0' }}>
              还没有用这条指令跑过场次</div>}
          </div>
        </div>
      </div>
      </div>
    </div>
  )
}
