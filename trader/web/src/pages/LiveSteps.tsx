/** 实时思考流:当前轮的工具调用/返回逐步出现(2 秒轮询)。
 * 进行中的轮选中时用它;轮完成后自动切回完整思考流(TranscriptTimeline)。 */
import { Card, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import type { LiveSteps as LiveStepsData } from '../api/types'
import { OP, STATUS } from '../lib/icons'
import { PageState } from '../lib/ui'

function stepTag(kind: string, tool?: string | null) {
  if (kind === 'round_start') return <Tag color="blue">● 轮开始</Tag>
  if (kind === 'round_end') return <Tag color="green"><STATUS.finish /> {tool || '本轮完成'}</Tag>
  if (kind === 'call') return <Tag color="purple"><OP.tool /> {tool}</Tag>
  return <Tag><OP.back /> 返回</Tag>
}

export default function LiveSteps({ runId }: { runId: number }) {
  const q = useQuery({
    queryKey: ['liveSteps', runId],
    queryFn: () => get<LiveStepsData>(`/runs/${runId}/live`),
    refetchInterval: 2000,   // 近实时:2 秒增量拉取
  })

  const d = q.data
  if (!d) return <Card><PageState query={q} size="panel" /></Card>
  const steps = d.steps ?? []
  const last = steps.at(-1)

  return (
    <Card title={
      <span>
        {d.in_progress ? <Tag color="processing">● 进行中</Tag> : <Tag>已结束</Tag>}
        第 {d.round} 轮实时思考流
        <span style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 8 }}>每 2 秒自动刷新</span>
      </span>
    } size="small">
      {steps.length === 0 && <PageState loading size="panel" />}
      {steps.map(s => (
        <div key={s.id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 6 }}>
          <span style={{ fontSize: 11, color: 'var(--text-3)', width: 40, flexShrink: 0 }}>
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
        <div style={{ marginTop: 8, color: 'var(--accent)', fontSize: 13 }}>
          {last?.kind === 'call' ? <><OP.tool /> 工具执行中…</> : <><OP.idea /> 思考中…</>}
        </div>
      )}
    </Card>
  )
}
