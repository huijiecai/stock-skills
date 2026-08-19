import { Table, Tag, Card, Button } from 'antd'
import { Link, useSearchParams } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'

export default function Runs() {
  const [params] = useSearchParams()
  const picked = useMemo(() => (params.get('ids') ?? '').split(',').filter(Boolean).map(Number), [params])
  const [sel, setSel] = useState<number[]>(picked)
  const runs = useQuery({ queryKey: ['runs'], queryFn: () => get('/runs') })

  return (
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
               { title: '类型', dataIndex: 'kind', width: 70,
                 render: (k: string) => <Tag color={k === 'live' ? 'red' : 'blue'}>{k === 'live' ? '实盘' : '模拟'}</Tag> },
               { title: '数据日', dataIndex: 'trade_date', width: 100 },
               { title: '系统', dataIndex: 'system', width: 110 },
               { title: '沙盒', width: 90,
                 render: (_: any, r: any) =>
                   r.kind === 'live'
                     ? <Tag color="red">主账本</Tag>
                     : <Tag color="cyan">沙盒 #{r.bag_id}</Tag> },
               { title: '指纹', width: 90,
                 render: (_: any, r: any) => <span className="mono">{(r.fingerprint ?? '').slice(0, 8) || '-'}</span> },
               { title: '收益', width: 90,
                 render: (_: any, r: any) => r.metrics ? <Tag color={r.metrics.return_pct >= 0 ? 'green' : 'red'}>{r.metrics.return_pct}%</Tag> : '-' },
               { title: '回撤', width: 80,
                 render: (_: any, r: any) => r.metrics ? `${r.metrics.max_drawdown_pct}%` : '-' },
               { title: '状态', dataIndex: 'status', width: 80 },
             ]} />
    </Card>
  )
}
