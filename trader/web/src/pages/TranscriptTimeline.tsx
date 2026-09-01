import { Card, Collapse, Tag } from 'antd'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Step } from '../api/types'
import { createElement } from 'react'
import { OP, STATUS } from '../lib/icons'
import { PageState } from '../lib/ui'

const KIND_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  prompt: { icon: createElement(OP.profile), label: '轮指令', color: 'geekblue' },
  text: { icon: createElement(OP.chat), label: 'AI 推理/输出', color: 'green' },
  call: { icon: createElement(OP.tool), label: '工具调用', color: 'orange' },
  ret: { icon: createElement(OP.back), label: '工具返回', color: 'default' },
  retry: { icon: createElement(STATUS.warn), label: '重试', color: 'red' },
}

export default function TranscriptTimeline({ loading, steps, logMd, usage }: {
  loading: boolean
  steps: Step[]   // API Step:kind 声明,body/tool/args 按 kind 出现(透传 unknown,渲染前收窄)
  logMd?: string | null
  usage?: Record<string, unknown>
}) {
  if (loading) return <Card><PageState loading size="panel" /></Card>

  const nRequests = typeof usage?.requests === 'number' ? usage.requests : 0
  const nIn = typeof usage?.input_tokens === 'number' ? usage.input_tokens : 0
  const nOut = typeof usage?.output_tokens === 'number' ? usage.output_tokens : 0

  const items = []
  if (logMd) {
    items.push({
      key: 'log',
      label: <><OP.doc /> 轮日志(md)</>,
      children: <div className="markdown-body" style={{ maxHeight: 500, overflow: 'auto', padding: '0 8px' }}>
        <Markdown remarkPlugins={[remarkGfm]}>{logMd}</Markdown>
      </div>,
    })
  }
  items.push({
    key: 'ts',
    label: <><OP.idea /> 思考流({steps.length} 步{nRequests ? ` · ${nRequests} 请求 · 输入${nIn.toLocaleString()} / 输出${nOut.toLocaleString()} tokens` : ''})</>,
    children: steps.length ? (
      <div>
        {steps.map((s, i) => {
          const m = KIND_META[s.kind]
          const tool = typeof s.tool === 'string' ? s.tool : ''
          const body = typeof s.body === 'string' ? s.body : ''
          return (
            <div key={i} style={{ marginBottom: 6 }}>
              <Tag color={m?.color}>
                {m ? <>{m.icon} {tool ? <span className="mono">{m.label} {tool}</span> : m.label}</> : s.kind}
              </Tag>
              <pre className="step-body">
                {s.kind === 'call'
                  ? JSON.stringify(s.args, null, 1)
                  : body.slice(0, 4000)}
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
