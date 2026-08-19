import { Card, Col, Row, Statistic, Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'

export default function Dashboard() {
  const account = useQuery({ queryKey: ['account'], queryFn: () => get('/trading/account') })
  const runs = useQuery({ queryKey: ['runs'], queryFn: () => get('/runs') })

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="现金" precision={2} prefix="¥" value={account.data?.cash ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="持仓市值" precision={2} prefix="¥" value={account.data?.market_value ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="总资产" precision={2} prefix="¥" value={account.data?.asset ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="场次" value={runs.data?.length ?? 0} suffix="场" /></Card></Col>
      </Row>
      {account.data?.positions?.length > 0 && (
        <Card title="持仓" style={{ marginTop: 16 }} size="small">
          <Table rowKey="code" size="small" pagination={false}
                 dataSource={account.data.positions}
                 columns={[
                   { title: '代码', dataIndex: 'code' },
                   { title: '名称', dataIndex: 'name' },
                   { title: '数量', dataIndex: 'quantity' },
                   { title: '可卖', dataIndex: 'sellable' },
                   { title: '成本', dataIndex: 'avg_cost' },
                   { title: '买入日', dataIndex: 'bought_on' },
                 ]} />
        </Card>
      )}
      <Card title="最近场次" style={{ marginTop: 16 }} size="small">
        <Table rowKey="id" size="small" pagination={{ pageSize: 8 }}
               dataSource={(runs.data ?? []).slice(0, 20)}
               columns={[
                 { title: '#', dataIndex: 'id', width: 50 },
                 { title: '场次', render: (_: any, r: any) => <Link to={`/runs/${r.id}`}>{r.name}</Link> },
                 { title: '类型', dataIndex: 'kind', width: 70,
                   render: (k: string) => <Tag color={k === 'live' ? 'red' : k === 'single' ? 'purple' : 'blue'}>{k === 'live' ? '实盘' : k === 'single' ? '分析' : '模拟'}</Tag> },
                 { title: '数据日', dataIndex: 'trade_date', width: 100 },
                 { title: '收益', width: 90,
                   render: (_: any, r: any) => r.metrics ? <Tag color={r.metrics.return_pct >= 0 ? 'green' : 'red'}>{r.metrics.return_pct}%</Tag> : '-' },
                 { title: '状态', dataIndex: 'status', width: 80 },
               ]} />
      </Card>
    </div>
  )
}
