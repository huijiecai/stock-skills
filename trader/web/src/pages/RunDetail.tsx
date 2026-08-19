import { Card, Col, Row, Statistic, Tag, Timeline, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import TranscriptTimeline from '../components/TranscriptTimeline'

export default function RunDetail() {
  const { id } = useParams()
  const run = useQuery({ queryKey: ['run', id], queryFn: () => get(`/runs/${id}`) })
  const [selected, setSelected] = useState<number>(0)
  const rounds = useQuery({ queryKey: ['rounds', id], queryFn: () => get(`/runs/${id}/rounds`) })
  useEffect(() => {
    const last = rounds.data?.rounds?.at(-1)?.n
    if (last && !selected) setSelected(last)
  }, [rounds.data])
  const round = useQuery({
    queryKey: ['round', id, selected],
    queryFn: () => get(`/runs/${id}/rounds/${selected}`),
    enabled: selected > 0,
  })

  if (run.isLoading) return <Card>加载中…</Card>
  if (run.error) return <Card>{(run.error as any).message}</Card>
  const r = run.data

  return (
    <div>
      <Card title={<span>{r.name} <Tag color={r.kind === 'live' ? 'red' : 'blue'}>{r.kind === 'live' ? '实盘' : '模拟'}</Tag>
        <Tag>{r.status}</Tag><Tag color="purple">{r.system}</Tag></span>}
        extra={<span className="mono">bag {r.bag_id} · 指纹 {(r.fingerprint ?? '').slice(0, 10) || '-'}</span>}>
        <Row gutter={16}>
          {r.metrics && <>
            <Col span={4}><Statistic title="收益" suffix="%" value={r.metrics.return_pct}
              valueStyle={{ color: r.metrics.return_pct >= 0 ? '#3f8600' : '#cf1322' }} /></Col>
            <Col span={4}><Statistic title="最大回撤" suffix="%" value={r.metrics.max_drawdown_pct} /></Col>
            <Col span={4}><Statistic title="胜率" suffix="%" value={r.metrics.win_rate ?? '-'} /></Col>
            <Col span={4}><Statistic title="交易" value={r.metrics.n_fills} suffix="笔" /></Col>
            <Col span={4}><Statistic title="期末资产" prefix="¥" precision={0} value={r.metrics.asset} /></Col>
            <Col span={4}><Statistic title="平仓回合" value={r.metrics.realized_trades} /></Col>
          </>}
          {!r.metrics && <Col><Typography.Text type="secondary">本场无封场指标(进行中或老场)</Typography.Text></Col>}
        </Row>
      </Card>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={5}>
          <Card title="轮次" size="small" style={{ maxHeight: '75vh', overflow: 'auto' }}>
            <Timeline items={(rounds.data?.rounds ?? []).map((x: any) => ({
              color: x.has_transcript ? 'blue' : 'gray',
              children: (
                <a onClick={() => setSelected(x.n)} style={{ fontWeight: x.n === selected ? 700 : 400 }}>
                  r{x.n}{x.has_transcript ? '' : ' (无思考流)'}
                </a>
              ),
            }))} />
          </Card>
        </Col>
        <Col span={19}>
          {selected > 0 ? (
            <TranscriptTimeline
              loading={round.isLoading}
              steps={round.data?.steps ?? []}
              logMd={round.data?.log_md}
              usage={round.data?.usage} />
          ) : <Card>选择左侧轮次查看详情</Card>}
        </Col>
      </Row>
    </div>
  )
}
