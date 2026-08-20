/** 阶段工作区·提示词 Tab:绑定当前阶段的单一 prompt。
 * 版本编辑/预览/对比 + 以旧版为底稿 + 场次快照种子(?prompt=&v=&from=)。 */
import { Input, Button, message, Select, Space, Spin, Tabs, Tag, Typography, Alert } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, put } from '../api/client'
import { parsePromptVersions } from '../lib/system'
import { pnlColor } from '../lib/ui'
import PromptDiff from './PromptDiff'

export default function SystemPrompts() {
  const { name = '', stage = '' } = useParams()
  const system = name
  const qc = useQueryClient()
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const prompts = useQuery({ queryKey: ['prompts', system], queryFn: () => get(`/systems/${system}/prompts`) })
  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}`) })

  const seedPrompt = params.get('prompt')
  const seedV = Number(params.get('v') || 0)
  const seedFrom = params.get('from')

  // 绑定当前阶段:阶段页找 stage 匹配;_system 找 (system)
  const bound = (prompts.data ?? []).find((x: any) =>
    x.stage === (stage === '_system' ? '(system)' : stage))

  const [content, setContent] = useState('')
  const [versions, setVersions] = useState<any[]>([])
  const [version, setVersion] = useState<number | null>(null)
  const [dirty, setDirty] = useState(false)
  const [view, setView] = useState('edit')
  const [diffA, setDiffA] = useState<number | null>(null)
  const [diffB, setDiffB] = useState<number | null>(null)
  const inited = useRef('')

  /** 打开:拉版本列表,定位到 preferred(缺省最新),同步 diff 默认两侧。 */
  async function openPrompt(p: string, preferred?: number) {
    const vs = await get(`/systems/${system}/prompts/${encodeURIComponent(p)}/versions`)
    setVersions(vs)
    if (!vs.length) { setContent(''); setVersion(null); setDiffA(null); setDiffB(null); return }
    const target = preferred && vs.some((v: any) => v.version === preferred) ? preferred : vs[0].version
    const r = await get(`/systems/${system}/prompts/${encodeURIComponent(p)}/versions/${target}`)
    setContent(r.content); setVersion(target); setDirty(false)
    const idx = vs.findIndex((v: any) => v.version === target)
    setDiffA(vs[idx + 1]?.version ?? null)
    setDiffB(target)
    setView('edit')
  }

  // 绑定变化 / 种子参数:定位 prompt 与版本
  useEffect(() => {
    const key = bound?.prompt ?? ''
    if (!prompts.data?.length || !key || inited.current === `${key}:${seedPrompt}:${seedV}`) return
    inited.current = `${key}:${seedPrompt}:${seedV}`
    openPrompt(key, bound?.prompt === seedPrompt ? (seedV || undefined) : undefined)
  }, [prompts.data, bound?.prompt, seedPrompt, seedV])

  async function pickVersion(v: number) {
    if (!bound) return
    const r = await get(`/systems/${system}/prompts/${encodeURIComponent(bound.prompt)}/versions/${v}`)
    setContent(r.content); setVersion(v); setDirty(false)
    const idx = versions.findIndex(x => x.version === v)
    setDiffA(versions[idx + 1]?.version ?? null)
    setDiffB(v)
    setView('edit')
  }

  async function save() {
    if (!bound) return
    const r = await put(`/systems/${system}/prompts/${encodeURIComponent(bound.prompt)}`, { content })
    message.success(r.changed ? `已保存 v${r.version}` : '内容无变化')
    qc.invalidateQueries({ queryKey: ['prompts', system] })
    if (seedFrom) setParams({})
    await openPrompt(bound.prompt, r.version)
  }

  // diff 两侧内容(按需拉取,react-query 缓存)
  const diffAContent = useQuery({
    queryKey: ['promptContent', system, bound?.prompt, diffA],
    queryFn: () => get(`/systems/${system}/prompts/${encodeURIComponent(bound?.prompt)}/versions/${diffA}`).then((r: any) => r.content),
    enabled: view === 'diff' && !!diffA,
  })
  const diffBContent = useQuery({
    queryKey: ['promptContent', system, bound?.prompt, diffB],
    queryFn: () => get(`/systems/${system}/prompts/${encodeURIComponent(bound?.prompt)}/versions/${diffB}`).then((r: any) => r.content),
    enabled: view === 'diff' && !!diffB,
  })

  // 执行史:该指令对应阶段的场次(带封面版本号)
  const runs = useQuery({
    queryKey: ['systemRuns', system],
    queryFn: () => get(`/runs?system=${encodeURIComponent(system)}`),
    staleTime: 15000,
  })
  const stages: Record<string, any> = detail.data?.manifest?.stages ?? {}
  const stageOfPrompt = Object.entries(stages)
    .find(([, d]: any) => d?.prompt === bound?.prompt)?.[0]
  const stageRuns: any[] = (runs.data ?? [])
    .filter((r: any) => r.stage === stageOfPrompt || stageOfPrompt === '(system)')
    .slice(0, 20)

  if (prompts.isLoading) return <Spin />
  if (!bound)
    return <Typography.Text type="secondary">此阶段还没有 prompt 模板(到「设置」重新添加该阶段会自动创建)</Typography.Text>

  const isOldBase = version != null && versions[0] && version !== versions[0].version
  const verOptions = versions.map((v: any) => ({
    value: v.version,
    label: `v${v.version}${v.version === versions[0]?.version ? ' (最新)' : ''}`,
  }))

  return (
    <div>
      {seedFrom && bound.prompt === seedPrompt && (
        <Alert type="info" showIcon closable onClose={() => setParams({})}
               message={<span>来自场次 #{seedFrom} 的快照 v{seedV}</span>}
               description="以该版本为底稿继续改进——修改保存后将生成新版本,原场次的封面快照不受影响。"
               style={{ marginBottom: 12 }} />
      )}

      {/* 执行史(该指令跑过哪些场次/结果) */}
      {stageRuns.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div className="hx-group">▎执行史 · {stageOfPrompt ?? bound.prompt}</div>
          {stageRuns.map(r => {
            const v = parsePromptVersions(r.prompt_versions)[bound.prompt]
            return (
              <div className="hx-row" key={r.id} onClick={() => nav(`/runs/${r.id}`)}>
                <span className="num">{(r.trade_date ?? '').slice(5)}</span>
                <span className="st-badge st-neutral">v{v ?? '-'}</span>
                <span>{r.status === 'sealed' ? '✓' : '●'} {r.status}</span>
                {r.metrics?.return_pct != null && (
                  <span className="num" style={{ color: pnlColor(r.metrics.return_pct) }}>
                    {r.metrics.return_pct > 0 ? '+' : ''}{r.metrics.return_pct}%
                  </span>
                )}
                <span className="d">{r.slug?.slice(0, 24)}</span>
              </div>
            )
          })}
        </div>
      )}

      {/* 版本工具栏 */}
      <Space style={{ marginBottom: 8, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Select size="small" style={{ width: 130 }} value={version} onChange={pickVersion}
                  placeholder="版本" options={verOptions} />
          {isOldBase && <Tag color="orange">v{version} 旧版底稿 · 保存生成新版本</Tag>}
        </Space>
        <Space>
          {dirty && <Tag color="orange">未保存</Tag>}
          <Button type="primary" size="small" onClick={save} disabled={!dirty || !version}>
            保存新版本
          </Button>
        </Space>
      </Space>

      <Tabs size="small" activeKey={view} onChange={setView} items={[
        { key: 'edit', label: '✏️ 编辑', forceRender: true,
          children: <Input.TextArea rows={20} value={content}
            onChange={(e) => { setContent(e.target.value); setDirty(true) }}
            style={{ fontSize: 12, fontFamily: 'ui-monospace, SF Mono, Menlo, monospace' }}
            placeholder="在此编写 prompt...  可用变量:{date} {prev} {weekday} {gap} 等(阶段 vars 决定)" /> },
        { key: 'preview', label: '👁 预览',
          children: <div className="markdown-body" style={{
            minHeight: 300, maxHeight: 640, overflow: 'auto',
            border: '1px solid #d9d9d9', borderRadius: 6, padding: 16 }}>
            {content ? <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
                     : <Typography.Text type="secondary">编辑后显示预览</Typography.Text>}
          </div> },
        { key: 'diff', label: '🔀 版本对比', disabled: versions.length < 2,
          children: (
            <div>
              <Space style={{ marginBottom: 8 }}>
                <Select size="small" style={{ width: 120 }} value={diffA} onChange={setDiffA}
                        options={verOptions} placeholder="旧侧" />
                <span>→</span>
                <Select size="small" style={{ width: 120 }} value={diffB} onChange={setDiffB}
                        options={verOptions} placeholder="新侧" />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  对比基于已保存版本{dirty ? '(当前编辑未保存,不在对比内)' : ''}
                </Typography.Text>
              </Space>
              {diffAContent.data != null && diffBContent.data != null
                ? <PromptDiff a={diffAContent.data} b={diffBContent.data}
                              aLabel={`v${diffA}`} bLabel={`v${diffB}`} />
                : <Spin size="small" />}
            </div>
          ) },
      ]} />
    </div>
  )
}
