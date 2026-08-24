import { Table, Tag, Card, Button, Badge, Typography, Tooltip } from 'antd'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import { runStalled, heartbeatAge } from '../lib/ui'

export default function Runs() {
  const nav = useNavigate()
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
  const stalled = running.filter((r: any) => runStalled(r))
  const alive = running.filter((r: any) => !runStalled(r))
  const kindTag = (k: string) => {
    if (k === 'live') return <Tag color="red">实盘</Tag>
    if (k === 'single') return <Tag color="purple">分析</Tag>
    return <Tag color="blue">模拟</Tag>
  }

  return (
    <div>
      {/* 执行中横幅 */}
      {alive.length > 0 && (
        <Card size="small" style={{ marginBottom: 12, background: '#fffbe6' }}>
          <Badge status="processing" text={
            <span>
              <b>{alive.length} 个任务执行中</b>
              {alive.map((r: any) => (
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
      {/* 疑似僵死横幅:心跳超时(机器睡眠/进程被杀/旧引擎),提示处理 */}
      {stalled.length > 0 && (
        <Card size="small" style={{ marginBottom: 12, background: '#fff7e6' }}>
          <Badge status="warning" text={
            <span>
              <b>{stalled.length} 个任务疑似僵死</b>(心跳超 5 分钟:进程可能被系统睡眠冻结或已死)
              {stalled.map((r: any) => (
                <Tag key={r.id} color="warning" style={{ marginLeft: 8 }}>
                  <Link to={`/runs/${r.id}`}>{r.system}·{r.trade_date}</Link>
                </Tag>
              ))}
              <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                进详情可停止并强制封存;实盘机建议 caffeinate 防睡眠
              </Typography.Text>
            </span>
          } />
        </Card>
      )}

      <Card title="场次列表" extra={
        <Button type="primary" disabled={sel.length !== 2}
                onClick={() => nav(`/compare?ids=${sel.join(',')}`)}>
          对比勾选的两场({sel.length}/2)
        </Button>
      }>
        <Table rowKey="id" size="small"
               rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as number[]) }}
               dataSource={runs.data ?? []}
               columns={[
                 { title: '#', dataIndex: 'id', width: 50 },
                 { title: '场次', render: (_: any, r: any) => <Link to={`/runs/${r.id}`}>{r.slug}</Link> },
                 { title: '类型', dataIndex: 'kind', width: 70, render: kindTag },
                 { title: '数据日', dataIndex: 'trade_date', width: 100 },
                 { title: '系统', dataIndex: 'system', width: 110 },
                 { title: '沙盒', width: 90,
                   render: (_: any, r: any) =>
                     r.kind === 'live' ? <Tag color="red">主账本</Tag>
                     : r.kind === 'single' ? <Tag color="purple">分析</Tag>
                     : <Tag color="cyan">沙盒 #{r.portfolio_id}</Tag> },
                 { title: '指纹', width: 90,
                   render: (_: any, r: any) => <span className="mono">{(r.fingerprint ?? '').slice(0, 8) || '-'}</span> },
                 { title: '收益', width: 90,
                   render: (_: any, r: any) => r.metrics ? <Tag color={r.metrics.return_pct >= 0 ? 'green' : 'red'}>{r.metrics.return_pct}%</Tag> : '-' },
                 { title: '回撤', width: 80,
                   render: (_: any, r: any) => r.metrics ? `${r.metrics.max_drawdown_pct}%` : '-' },
                 { title: '状态', dataIndex: 'status', width: 90,
                   render: (s: string, r: any) =>
                     s === 'running'
                       ? runStalled(r)
                         ? <Tooltip title={`心跳:${heartbeatAge(r)};进程可能被系统睡眠冻结或已死`}>
                             <Badge status="warning" text="疑似僵死" />
                           </Tooltip>
                         : <Badge status="processing" text="执行中" />
                     : <Tag color="green">{s}</Tag> },
               ]} />
      </Card>
    </div>
  )
}
