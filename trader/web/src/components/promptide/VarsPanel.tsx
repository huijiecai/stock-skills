/** 指令台·变量面板:该阶段 prompt 可用的占位符(契约与引擎运行时同源)。
 * 点击 → 在编辑器光标处插入 {name}(§5.1)。 */
import { Input, Spin, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { get } from '../../api/client'

const SOURCE_LABEL: Record<string, string> = {
  auto: '自动注入', caller: '发起时传入',
}

export default function VarsPanel({ system, stage, onInsert }: {
  system: string, stage: string, onInsert: (snippet: string) => void }) {
  const [kw, setKw] = useState('')
  const ctx = useQuery({
    queryKey: ['stageContext', system, stage],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/stages/${encodeURIComponent(stage)}/context`),
    enabled: !!stage,
    staleTime: 60_000,
  })
  if (!stage) return <Typography.Text type="secondary">该指令未挂到阶段</Typography.Text>
  if (ctx.isLoading) return <Spin size="small" style={{ display: 'block', margin: '20px auto' }} />
  if (ctx.error) return <Typography.Text type="danger">{(ctx.error as Error).message}</Typography.Text>
  const d: any = ctx.data ?? {}
  const vars: any[] = (d.vars ?? []).filter((v: any) =>
    !kw || v.name.includes(kw) || (v.desc ?? '').includes(kw))
  return (
    <div>
      {d.note && <Typography.Text type="warning" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
        ⚠ {d.note}</Typography.Text>}
      <Input size="small" allowClear placeholder="过滤变量…" value={kw}
             onChange={e => setKw(e.target.value)} style={{ marginBottom: 8 }} />
      {vars.map(v => (
        <div key={v.name} className="var-row" onClick={() => onInsert(`{${v.name}}`)}
             title={`示例:${v.example || '-'}　点击插入`}>
          <span className="k mono">{'{' + v.name + '}'}</span>
          <span className="d">{v.desc}
            {v.example && <small> · 示例 {String(v.example)}</small>}</span>
          <Tag style={{ marginInlineEnd: 0 }}>{SOURCE_LABEL[v.source] ?? v.source}</Tag>
        </div>
      ))}
      {!vars.length && <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        本阶段没有可用变量({d.kind === 'system' ? '系统设定不做替换' : '按阶段类型自动判定'})</Typography.Text>}
    </div>
  )
}
