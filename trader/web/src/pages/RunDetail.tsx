import { Card, Col, Row, Statistic, Tag, Timeline, Typography, Table, Collapse, Button } from 'antd'
import { useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import TranscriptTimeline from '../components/TranscriptTimeline'
import ChatDrawer from '../components/ChatDrawer'

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
  const trading = useQuery({
    queryKey: ['runTrading', id],
    queryFn: () => get(`/runs/${id}/trading`),
  })

  const [chatOpen, setChatOpen] = useState(false)

  if (run.isLoading) return <Card>加载中…</Card>
  if (run.error) return <Card>{(run.error as any).message}</Card>
  const r = run.data

  return (
    <div>
      <Card title={<span>{r.name} <Tag color={r.kind === 'live' ? 'red' : r.kind === 'single' ? 'purple' : 'blue'}>{r.kind === 'live' ? '实盘' : r.kind === 'single' ? '分析' : '模拟'}</Tag>
        <Tag>{r.status}</Tag><Tag color="purple">{r.system}</Tag></span>}
        extra={<span>
          <Button size="small" type="primary" ghost onClick={() => setChatOpen(true)} style={{ marginRight: 12 }}>
            💬 讨论结果
          </Button>
          <span className="mono">指纹 {(r.fingerprint ?? '').slice(0, 10) || '-'}</span>
        </span>}>
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

      {/* 沙盒账本 */}
      {trading.data && (
        <Card title={<span>沙盒账本 {r.kind === 'live'
          ? <Tag color="red">主账本</Tag>
          : r.kind === 'single'
          ? <Tag color="purple">主账本(分析)</Tag>
          : <Tag color="cyan">沙盒 #{trading.data.bag}</Tag>}</span>}
          size="small" style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={4}><Statistic title="现金" prefix="¥" precision={0}
              value={trading.data.cash ?? '-'} /></Col>
            <Col span={4}><Statistic title="初始资金" prefix="¥" precision={0}
              value={trading.data.initial ?? '-'} /></Col>
          </Row>
          {trading.data.positions?.length > 0 && (
            <Table rowKey="code" size="small" pagination={false} style={{ marginTop: 12 }}
                   dataSource={trading.data.positions}
                   columns={[
                     { title: '代码', dataIndex: 'code', width: 80 },
                     { title: '名称', dataIndex: 'name' },
                     { title: '数量', dataIndex: 'quantity', width: 70 },
                     { title: '可卖', dataIndex: 'sellable', width: 60 },
                     { title: '成本', dataIndex: 'avg_cost', width: 80 },
                     { title: '买入日', dataIndex: 'bought_on', width: 100 },
                   ]} />
          )}
          {trading.data.fills?.length > 0 && (
            <Collapse style={{ marginTop: 12 }} items={[{
              key: 'fills',
              label: `成交明细(${trading.data.fills.length} 笔)`,
              children: (
                <Table rowKey="id" size="small" pagination={false}
                       dataSource={[...trading.data.fills].reverse()}
                       columns={[
                         { title: '时间', width: 130,
                           render: (_: any, f: any) => (f.trade_time || f.created_at || '').slice(5, 16) },
                         { title: '方向', dataIndex: 'side', width: 50,
                           render: (s: string) => <Tag color={s === 'BUY' ? 'green' : 'red'}>{s}</Tag> },
                         { title: '标的', render: (_: any, f: any) => `${f.name || f.code}(${f.code})` },
                         { title: '数量', dataIndex: 'quantity', width: 70 },
                         { title: '价格', render: (_: any, f: any) => `¥${(f.price_cents / 100).toFixed(2)}` },
                         { title: '决策留痕', dataIndex: 'reason',
                           render: (v: string) => <Typography.Text type="secondary" style={{ fontSize: 12 }}>{v}</Typography.Text> },
                       ]} />
              ),
            }]} />
          )}
        </Card>
      )}

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

      {/* 讨论抽屉 */}
      <ChatDrawer runId={r.id} systemName={r.system} open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  )
}
