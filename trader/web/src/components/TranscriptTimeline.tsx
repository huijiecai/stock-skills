import { Card, Collapse, Spin, Tag } from 'antd'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export type Step = {
  kind: 'prompt' | 'text' | 'call' | 'ret' | 'retry'
  body?: string
  tool?: string
  args?: unknown
}

const KIND_META: Record<string, { label: string; color: string }> = {
  prompt: { label: '📋 轮指令', color: 'geekblue' },
  text: { label: '💬 AI 推理/输出', color: 'green' },
  call: { label: '🔧 工具调用', color: 'orange' },
  ret: { label: '← 工具返回', color: 'default' },
  retry: { label: '⚠ 重试', color: 'red' },
}

export default function TranscriptTimeline({ loading, steps, logMd, usage }: {
  loading: boolean
  steps: Step[]
  logMd?: string | null
  usage?: Record<string, number>
}) {
  if (loading) return <Card><Spin /></Card>

  const items = []
  if (logMd) {
    items.push({
      key: 'log',
      label: '📄 轮日志(md)',
      children: <div className="markdown-body" style={{ maxHeight: 500, overflow: 'auto', padding: '0 8px' }}>
        <Markdown remarkPlugins={[remarkGfm]}>{logMd}</Markdown>
      </div>,
    })
  }
  items.push({
    key: 'ts',
    label: `🧠 思考流(${steps.length} 步${usage?.requests ? ` · ${usage.requests} 请求 · 输入${(usage.input_tokens ?? 0).toLocaleString()} / 输出${(usage.output_tokens ?? 0).toLocaleString()} tokens` : ''})`,
    children: steps.length ? (
      <div>
        {steps.map((s, i) => {
          const m = KIND_META[s.kind]
          return (
            <div key={i} style={{ marginBottom: 6 }}>
              <Tag color={m?.color}>
                {m?.label ?? s.kind}{s.tool ? <> <span className="mono">{s.tool}</span></> : ''}
              </Tag>
              <pre className="step-body">
                {s.kind === 'call'
                  ? JSON.stringify(s.args, null, 1)
                  : (s.body ?? '').slice(0, 4000)}
              </pre>
            </div>
          )
        })}
      </div>
    ) : <div style={{ color: 'var(--text-3)', padding: 12 }}>这一轮没有保存思考流或工具调用。</div>,
  })

  return (
    <Card size="small">
      <Collapse defaultActiveKey={logMd ? ['log'] : ['ts']} items={items} />
    </Card>
  )
}
