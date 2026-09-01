/** 指令台·工具面板:领域工具目录(签名/说明/写标记)+ 试运行(挂测试账号,§5.3)。
 * 试运行返回的 output 就是 LLM 会看到的字符串——写 prompt 的依据。 */
import { Button, Collapse, Input, message, Select, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { get, post } from '../../api/client'
import { OP } from '../../lib/icons'
import { PageState } from '../../lib/ui'
import type { ToolCallOut, ToolInfo, ToolsCatalog } from '../../api/types'

const GROUP_LABEL: Record<string, string> = {
  market: '行情', scan: '扫描', account: '账户',
  trading: '交易', docs: '文档', watchlist: '自选组', other: '其他',
}
const GROUP_ICON: Record<string, React.ComponentType> = {
  market: OP.market, scan: OP.compass, account: OP.wallet,
  trading: OP.bolt, docs: OP.lib, watchlist: OP.star,
}

type Tool = ToolInfo

/** 试运行结果:成功是 ToolCallOut;失败本地拼 error。 */
type TrialOut = { output?: string; error?: string; truncated?: boolean }

export default function ToolPanel({ enabled: _enabled, onInsert }: {
  enabled?: string[]
  onInsert: (snippet: string) => void }) {
  const [kw, setKw] = useState('')
  const cat = useQuery({ queryKey: ['toolsCatalog'], queryFn: () => get<ToolsCatalog>('/tools'), staleTime: 60_000 })
  // Storage/document helpers remain available to the backend and advanced
  // test desk, but are not part of the prompt author's business vocabulary.
  const tools: Tool[] = (cat.data?.tools ?? []).filter(t => t.group !== 'docs')
  const portfolios = cat.data?.portfolios ?? []
  const groups = useMemo(() => {
    const filtered = tools.filter(t =>
      !kw || t.name.includes(kw) || t.desc.includes(kw))
    const by: Record<string, Tool[]> = {}
    for (const t of filtered) (by[t.group] ??= []).push(t)
    return Object.entries(by)
  }, [tools, kw])

  if (cat.isLoading || cat.error) return <PageState query={cat} size="panel" />

  return (
    <div>
      <Input size="small" allowClear placeholder="搜索工具…" value={kw}
             onChange={e => setKw(e.target.value)} style={{ marginBottom: 8 }} />
      <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
        工具由 Prompt 按需调用；试运行只用于查看模型实际会收到的结果。</Typography.Text>
      <Collapse size="small" items={groups.map(([g, items]) => {
        const GI = GROUP_ICON[g]
        return {
          key: g,
          label: <span>{GI ? <GI /> : null} {GROUP_LABEL[g] ?? g} <Tag style={{ marginInlineEnd: 0 }}>{items.length}</Tag></span>,
          children: items.map(t => (
            <ToolCard key={t.name} tool={t} portfolios={portfolios}
                      onInsert={onInsert} />
          )),
        }
      })} />
    </div>
  )
}

function ToolCard({ tool, portfolios, disabled, onInsert }: {
  tool: Tool, portfolios: ToolsCatalog['portfolios'], disabled?: boolean, onInsert: (s: string) => void }) {
  const [args, setArgs] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(tool.params.map(p => [p.name, p.default ?? ''])))
  const [out, setOut] = useState<TrialOut | null>(null)
  const [running, setRunning] = useState(false)
  const defaultPort = portfolios.find(p => p.has_positions) ?? portfolios[0]
  const [pid, setPid] = useState<number | undefined>(defaultPort?.id)
  const sig = tool.params.map(p => p.name + (p.required ? '' : '?')).join(', ')

  async function run() {
    setRunning(true)
    try {
      const body: { args: Record<string, unknown>; portfolio_id?: number } = { args }
      if (pid != null) body.portfolio_id = pid
      const r = await post<ToolCallOut>(`/tools/${tool.name}/call`, body)
      setOut(r)
      if (r.write_warning) message.warning(r.write_warning)
    } catch (e: any) {
      setOut({ error: e.message })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div style={{ padding: '6px 0', opacity: disabled ? 0.45 : 1 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <b className="mono" style={{ fontSize: 12.5 }}>{tool.name}</b>
        <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)' }}>({sig})</span>
        {tool.write && <Tag color="red" style={{ marginInlineEnd: 0 }}>写</Tag>}
        {disabled && <Tag style={{ marginInlineEnd: 0 }}>未启用</Tag>}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', margin: '3px 0 6px' }}>{tool.desc}</div>
      {tool.params.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
          {tool.params.map(p => (
            <Input key={p.name} size="small" addonBefore={p.name + (p.required ? '*' : '')}
                   placeholder={p.type + (p.required ? '' : `,默认 ${String(p.default)}`)}
                   disabled={disabled}
                   value={String(args[p.name] ?? '')}
                   onChange={e => {
                     const v = e.target.value
                     setArgs(a => ({ ...a, [p.name]: p.type.includes('list') && !Array.isArray(v)
                       ? v.split(',').filter(Boolean) : v }))
                   }} />
          ))}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, marginTop: 6, alignItems: 'center' }}>
        <Button size="small" type="primary" ghost loading={running} disabled={disabled} onClick={run}>
          <OP.play /> 试运行
        </Button>
        {portfolios.length > 0 && (
          <Select size="small" style={{ minWidth: 110 }} value={pid} onChange={setPid}
                  placeholder="测试组合"
                  options={portfolios.map(p => ({
                    value: p.id,
                    label: `#${p.id} ${p.name || p.type}${p.has_positions ? ' ●' : ''}`,
                  }))} />
        )}
        <Button size="small" type="text" disabled={disabled}
                onClick={() => onInsert(`- ${tool.name}(${sig}): ${tool.desc}`)}
                title="在光标处插入工具说明行">插入说明</Button>
      </div>
      {out && (
        <pre className="tool-out" style={{
          marginTop: 6, padding: 8, borderRadius: 8, fontSize: 11.5, maxHeight: 220,
          overflow: 'auto', background: 'var(--surface-2)',
          border: '1px solid var(--border)', whiteSpace: 'pre-wrap',
          color: out.error ? 'var(--down)' : 'inherit',
        }}>{out.error ?? out.output}{out.truncated ? '\n…' : ''}</pre>
      )}
    </div>
  )
}
