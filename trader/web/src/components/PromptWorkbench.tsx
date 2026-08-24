/** 指令台(原型画面八):打开一条指令 ≠ 打开文件——
 * 版本时间线 + 双栏(内容编辑/预览/对比 | 右栏 Tab:执行史/工具) + 引用关系。
 * IDE 化(设计:docs/Prompt编辑器IDE化设计讨论.md):占位符 lint、@/{ 触发补全、
 * 工具试运行(测试账号)、替换预览(派生变量服务端算真值)。
 * 路由:/systems/:slug/workbench/prompt/:prompt(_system=系统设定)。 */
import { Button, Input, message, Select, Space, Spin, Switch, Tabs, Tag, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, put } from '../api/client'
import { stageIcon, stageLabel, parsePromptVersions } from '../lib/system'
import { pnlColor } from '../lib/ui'
import { extractPlaceholders, substitute, unknownPlaceholders } from '../lib/promptLint'
import { detectAutocomplete, navAutocomplete } from '../lib/promptInsert'
import PromptDiff from './PromptDiff'
import ToolPanel from './promptide/ToolPanel'
import AutocompleteList, { type AcItem } from './promptide/AutocompleteList'

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
  const caretPending = useRef<number | null>(null)      // 插入后待恢复的光标
  const [subPreview, setSubPreview] = useState(false)   // 替换预览开关
  const [subDate, setSubDate] = useState('')            // 预览用的目标交易日
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
  }, [system, promptSlug, seedV])

  const content = useQuery({
    queryKey: ['promptContent', system, promptSlug, diffA],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}/versions/${diffA}`).then((r: any) => r.content),
    enabled: view === 'diff' && !!diffA,
  })

  // 占位符仅用于用户业务参数；日期/轮次等平台运行信息自动注入。
  const ctx = useQuery({
    queryKey: ['stageContext', system, stageOf, subPreview ? subDate : ''],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/stages/${encodeURIComponent(stageOf)}/context`
      + (subPreview && subDate ? `?date=${subDate}` : '')),
    enabled: !!stageOf,
    staleTime: 60_000,
  })
  const ctxVars: any[] = ctx.data?.vars ?? []
  const userVars = ctxVars.filter(v => v.source === 'caller')
  const knownVars = ctxVars.map(v => v.name)
  // lint:系统设定出现任何占位符都警告(它不做替换);阶段 prompt 查未知占位符
  const lintUnknown = stageOf === '(system)'
    ? extractPlaceholders(text)
    : unknownPlaceholders(text, knownVars)

  // ── 工具目录(工具面板与 @ 补全共用同一 react-query 缓存) ──
  const catalog = useQuery({ queryKey: ['toolsCatalog'], queryFn: () => get('/tools'), staleTime: 60_000 })

  // ── 触发式补全状态(@ 工具 / { 业务参数) ──
  const [ac, setAc] = useState<{ trigger: '@' | '{'; query: string; start: number } | null>(null)
  const [acIndex, setAcIndex] = useState(0)
  const acItems: AcItem[] = (() => {
    if (!ac) return []
    if (ac.trigger === '{')
      return userVars
        .filter(v => !ac.query || v.name.startsWith(ac.query))
        .map(v => ({ label: `{${v.name}}`, title: `{${v.name}}`, desc: v.desc,
                     tag: v.source === 'auto' ? '自动注入' : '发起时传' }))
    return ((catalog.data?.tools ?? []) as any[]).filter((t: any) => t.group !== 'docs')
      .filter((t: any) => !ac.query || t.name.startsWith(ac.query.replace(/_.*/, '')) || t.name.includes(ac.query))
      .map((t: any) => ({
        label: `- ${t.name}(${t.params.map((p: any) => p.name).join(', ')}): ${t.desc}`,
        title: t.name, desc: t.desc, tag: t.write ? '写' : t.group,
      }))
  })()

  function applyInsert(snippet: string, replaceFrom?: number) {
    const ta: HTMLTextAreaElement | null = taRef.current?.resizableTextArea?.textArea ?? null
    const caret = ta ? ta.selectionStart : text.length
    const from = replaceFrom ?? caret
    const next = text.slice(0, from) + snippet + text.slice(caret)
    setText(next)
    setDirty(true)
    setView('edit')
    caretPending.current = from + snippet.length
  }

  // 插入/替换后恢复光标(state 提交渲染完成后)
  useEffect(() => {
    if (caretPending.current == null) return
    const ta: HTMLTextAreaElement | null = taRef.current?.resizableTextArea?.textArea ?? null
    if (ta) { ta.focus(); ta.setSelectionRange(caretPending.current, caretPending.current) }
    caretPending.current = null
  }, [text])

  function onEditChange(v: string) {
    setText(v)
    setDirty(true)
    const ta: HTMLTextAreaElement | null = taRef.current?.resizableTextArea?.textArea ?? null
    const hit = ta ? detectAutocomplete(v, ta.selectionStart) : null
    setAc(hit)
    setAcIndex(0)
  }

  function onEditKeyDown(e: React.KeyboardEvent) {
    if (!ac) return
    const r = navAutocomplete(e, acIndex, acItems.length)
    if (!r) return
    if (r.action === 'move') setAcIndex(r.index)
    else if (r.action === 'close') setAc(null)
    else if (r.action === 'pick' && acItems[r.index]) {
      const item = acItems[r.index]
      const snippet = ac.trigger === '{' ? item.label : item.label   // 变量插 {name};工具插引导行
      applyInsert(snippet, ac.start)
      setAc(null)
    }
  }

  // 替换预览:值 = 服务端真值(带 date 时)或示例值;未覆盖占位符保留原样
  const subValues = Object.fromEntries(ctxVars.map(v => [v.name, v.value ?? v.example ?? '']))
  const subText = subPreview ? substitute(text, subValues) : ''
  const unresolved = subPreview ? extractPlaceholders(subText) : []

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
          <Button type="primary" size="small" onClick={save} disabled={!dirty}>保存新版本</Button>
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

      {/* 双栏:内容 | 右栏(执行史/工具) */}
      <div className="prompt-workbench-grid">
        <div style={{ flex: 1.45, minWidth: 0, position: 'relative' }}>
          {/* 占位符 lint:只警告不阻断(设计 Q3) */}
          {view !== 'diff' && lintUnknown.length > 0 && (
            <div style={{ background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 8,
                         padding: '5px 10px', marginBottom: 8, fontSize: 12 }}>
              ⚠ {stageOf === '(system)'
                ? <>系统设定不做变量替换,以下将按字面文本发给模型:
                   {lintUnknown.map(n => <Tag key={n} color="warning" style={{ marginInlineStart: 4 }}>{`{${n}}`}</Tag>)}</>
                : <>未知占位符({lintUnknown.length} 个,运行时会报错):{lintUnknown.map(n => <Tag key={n} color="warning" style={{ marginInlineStart: 4 }}>{`{${n}}`}</Tag>)}
                   <Typography.Text type="secondary"> 平台运行信息无需手工配置</Typography.Text></>}
            </div>
          )}
          <Tabs size="small" activeKey={view} onChange={(k) => setView(k as any)} items={[
            { key: 'preview', label: '👁 预览', forceRender: false,
              children: (
                <div>
                  <Space style={{ marginBottom: 8 }}>
                    <Switch size="small" checked={subPreview} onChange={setSubPreview} />
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>替换预览</Typography.Text>
                    {subPreview && userVars.some(v => v.name === 'date') && (
                      <Input size="small" style={{ width: 120 }} placeholder="date 如 20260824"
                             value={subDate} onChange={e => setSubDate(e.target.value.trim())} />
                    )}
                    {subPreview && <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      {unresolved.length ? `未覆盖:${unresolved.map(n => `{${n}}`).join(' ')}` : '变量已全部解析'}</Typography.Text>}
                  </Space>
                  {subPreview ? (
                    <pre className="md-body" style={{ whiteSpace: 'pre-wrap', fontSize: 12.5 }}>
                      {subText.split(/(\{[a-zA-Z_][a-zA-Z0-9_]*\})/g).map((seg, i) =>
                        /^\{[a-zA-Z_]/.test(seg)
                          ? <span key={i} style={{ color: 'var(--down)', fontWeight: 700 }}>{seg}</span>
                          : <span key={i}>{seg}</span>)}
                    </pre>
                  ) : (
                    <div className="md-body">
                      <Markdown remarkPlugins={[remarkGfm]}>{text || '(空)'}</Markdown>
                    </div>
                  )}
                </div>
              ) },
            { key: 'edit', label: '✏️ 编辑', forceRender: true,
              children: (
                <div style={{ position: 'relative' }}>
                  <Input.TextArea ref={taRef} value={text}
                                  onChange={(e) => onEditChange(e.target.value)}
                                  onKeyDown={onEditKeyDown}
                                  onBlur={() => setAc(null)}
                                  autoSize={{ minRows: 18, maxRows: 32 }}
                                  style={{ fontFamily: 'var(--font-num)', fontSize: 13 }} />
                  {ac && acItems.length > 0 && (
                    <div style={{ position: 'absolute', left: 8, bottom: 10, zIndex: 20 }}>
                      <AutocompleteList items={acItems} index={acIndex}
                        onPick={(item) => { applyInsert(item.label, ac.start); setAc(null) }}
                        onHover={setAcIndex} />
                    </div>
                  )}
                  <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    输入 <b>{'@'}</b> 查看领域工具；平台运行信息会自动注入</Typography.Text>
                </div>
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

        {/* 右栏:执行史 / 工具 */}
        <div className="prompt-history-pane">
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
                       boxShadow: 'var(--shadow-card)', padding: '10px 12px' }}>
            <Tabs size="small" items={[
              { key: 'tools', label: '🔧 工具',
                children: <ToolPanel onInsert={s => applyInsert(s)} /> },
              { key: 'history', label: '📖 执行史',
                children: (
                  <div>
                    <div style={{ fontWeight: 800, fontSize: 13, marginBottom: 8 }}>
                      ▎执行史 <span style={{ fontWeight: 400, color: 'var(--text-3)', fontSize: 11.5 }}>改前先看战绩</span>
                    </div>
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
                ) },
            ]} />
          </div>
        </div>
      </div>
      </div>
    </div>
  )
}
