import { Table, Tag, Card, Button, Badge, Typography } from 'antd'
import { Link, useSearchParams } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'

export default function Runs() {
  const [params] = useSearchParams()
  const picked = useMemo(() => (params.get('ids') ?? '').split(',').filter(Boolean).map(Number), [params])
  const [sel, setSel] = useState<number[]>(picked)

  // 有 running 状态的场 → 5 秒轮询刷新;否则 30 秒
  const runs = useQuery({
    queryKey: ['runs'],
    queryFn: () => get('/runs'),
    refetchInterval: (query) => {
      const hasRunning = (query.state.data ?? []).some((r: any) => r.status === 'running')
      return hasRunning ? 5000 : 30000
    },
  })

  const running = (runs.data ?? []).filter((r: any) => r.status === 'running')
  const kindTag = (k: string) => {
    if (k === 'live') return <Tag color="red">实盘</Tag>
    if (k === 'single') return <Tag color="purple">分析</Tag>
    return <Tag color="blue">模拟</Tag>
  }

  return (
    <div>
      {/* 执行中横幅 */}
      {running.length > 0 && (
        <Card size="small" style={{ marginBottom: 12, background: '#fffbe6' }}>
          <Badge status="processing" text={
            <span>
              <b>{running.length} 个任务执行中</b>
              {running.map((r: any) => (
                <Tag key={r.id} style={{ marginLeft: 8 }}>
                  {r.system}·{r.trade_date}
                </Tag>
              ))}
              <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                页面每 5 秒自动刷新 · 跑完自动变绿
              </Typography.Text>
            </span>
          } />
        </Card>
      )}

      <Card title="场次列表" extra={
        <Button type="primary" disabled={sel.length !== 2}
                onClick={() => location.href = `/compare?ids=${sel.join(',')}`}>
          对比勾选的两场({sel.length}/2)
        </Button>
      }>
        <Table rowKey="id" size="small"
               rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as number[]) }}
               dataSource={runs.data ?? []}
               columns={[
                 { title: '#', dataIndex: 'id', width: 50 },
                 { title: '场次', render: (_: any, r: any) => <Link to={`/runs/${r.id}`}>{r.name}</Link> },
                 { title: '类型', dataIndex: 'kind', width: 70, render: kindTag },
                 { title: '数据日', dataIndex: 'trade_date', width: 100 },
                 { title: '系统', dataIndex: 'system', width: 110 },
                 { title: '沙盒', width: 90,
                   render: (_: any, r: any) =>
                     r.kind === 'live' ? <Tag color="red">主账本</Tag>
                     : r.kind === 'single' ? <Tag color="purple">分析</Tag>
                     : <Tag color="cyan">沙盒 #{r.bag_id}</Tag> },
                 { title: '指纹', width: 90,
                   render: (_: any, r: any) => <span className="mono">{(r.fingerprint ?? '').slice(0, 8) || '-'}</span> },
                 { title: '收益', width: 90,
                   render: (_: any, r: any) => r.metrics ? <Tag color={r.metrics.return_pct >= 0 ? 'green' : 'red'}>{r.metrics.return_pct}%</Tag> : '-' },
                 { title: '回撤', width: 80,
                   render: (_: any, r: any) => r.metrics ? `${r.metrics.max_drawdown_pct}%` : '-' },
                 { title: '状态', dataIndex: 'status', width: 90,
                   render: (s: string) =>
                     s === 'running' ? <Badge status="processing" text="执行中" />
                     : <Tag color="green">{s}</Tag> },
               ]} />
      </Card>
    </div>
  )
}
