/** 实时思考流:当前轮的工具调用/返回逐步出现(2 秒轮询)。
 * 进行中的轮选中时用它;轮完成后自动切回完整思考流(TranscriptTimeline)。 */
import { Card, Spin, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'

function stepTag(kind: string, tool: string) {
  if (kind === 'round_start') return <Tag color="blue">▶ 轮开始</Tag>
  if (kind === 'round_end') return <Tag color="green">🏁 {tool || '本轮完成'}</Tag>
  if (kind === 'call') return <Tag color="purple">🔧 {tool}</Tag>
  return <Tag>← 返回</Tag>
}

export default function LiveSteps({ runId }: { runId: number }) {
  const q = useQuery({
    queryKey: ['liveSteps', runId],
    queryFn: () => get(`/runs/${runId}/live`),
    refetchInterval: 2000,   // 近实时:2 秒增量拉取
  })

  const d = q.data
  if (!d) return <Card><Spin /></Card>
  const steps: any[] = d.steps ?? []
  const last = steps.at(-1)

  return (
    <Card title={
      <span>
        {d.in_progress ? <Tag color="processing">● 进行中</Tag> : <Tag>已结束</Tag>}
        第 {d.round} 轮实时思考流
        <span style={{ fontSize: 12, color: '#999', marginLeft: 8 }}>每 2 秒自动刷新</span>
      </span>
    } size="small">
      {steps.length === 0 && <Spin size="small" style={{ margin: 20, display: 'block' }} />}
      {steps.map((s: any) => (
        <div key={s.id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 6 }}>
          <span style={{ fontSize: 11, color: '#bbb', width: 40, flexShrink: 0 }}>
            {(s.created_at || '').slice(11, 16)}
          </span>
          <span style={{ flexShrink: 0 }}>{stepTag(s.kind, s.tool)}</span>
          {s.body && (
            <pre className="step-body" style={{ flex: 1, marginBottom: 0 }}>{s.body}</pre>
          )}
        </div>
      ))}
      {/* 当前状态推断:call 无 ret=工具执行中;ret 后=LLM 推理中 */}
      {d.in_progress && (
        <div style={{ marginTop: 8, color: '#1677ff', fontSize: 13 }}>
          {last?.kind === 'call' ? '⚙️ 工具执行中…' : '💭 思考中…'}
        </div>
      )}
    </Card>
  )
}
