/** 数据区(原型画面三/八 ⭐数据):自选组表格视图——组列表 + 成员明细(角色分级)。 */
import { Table, Spin, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { get } from '../api/client'

export default function DataWorkbench() {
  const { name: system = '' } = useParams()
  const [sel, setSel] = useState<string | null>(null)
  const lists = useQuery({
    queryKey: ['watchlists', system],
    queryFn: () => get(`/watchlists?system=${encodeURIComponent(system)}`),
    staleTime: 30000,
  })
  const members = useQuery({
    queryKey: ['watchlist', system, sel],
    queryFn: () => get(`/watchlists/${encodeURIComponent(sel ?? '')}?system=${encodeURIComponent(system)}`),
    enabled: !!sel,
  })

  if (lists.isLoading) return <Spin style={{ display: 'block', margin: '60px auto' }} />

  return (
    <div className="ws-panel">
      <div className="ws-phead" style={{ borderBottom: 'none' }}>
        <span style={{ fontSize: 15, fontWeight: 700 }}>⭐ 数据 · 自选组</span>
        <span className="st-badge st-neutral">{(lists.data ?? []).length} 组</span>
        <span style={{ color: 'var(--text-3)', fontSize: 12, marginLeft: 'auto' }}>
          唯一结构化原语:成员/角色分级/行情快览;scan_market 每轮读取
        </span>
      </div>
      <div className="data-workbench-grid">
        <div className="data-list-pane">
          <Table rowKey="name" size="small" pagination={false}
                 onRow={(r: any) => ({ onClick: () => setSel(r.name), style: { cursor: 'pointer' } })}
                 rowClassName={(r: any) => (r.name === sel ? 'ant-table-row-selected' : '')}
                 dataSource={lists.data ?? []}
                 columns={[
                   { title: '组名', dataIndex: 'name', ellipsis: true },
                   { title: '成员', dataIndex: 'member_count', width: 60, className: 'num' },
                   { title: '更新', dataIndex: 'updated_at', width: 90,
                     render: (v: string) => (v ?? '').slice(5, 10) },
                 ]} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {sel ? (
            members.isLoading ? <Spin /> : (
              <Table rowKey="code" size="small" pagination={false}
                     dataSource={members.data ?? []}
                     columns={[
                       { title: '代码', dataIndex: 'code', width: 90, className: 'num' },
                       { title: '名称', dataIndex: 'name' },
                       { title: '角色', width: 110,
                         render: (_: any, m: any) => m.fields?.role
                           ? <Tag color={m.fields.role === 'leader' ? 'gold' : 'default'}>{m.fields.role}</Tag>
                           : <Tag>-</Tag> },
                       { title: '备注', render: (_: any, m: any) =>
                         <span style={{ color: 'var(--text-3)', fontSize: 12 }}>{m.fields?.note ?? ''}</span> },
                     ]} />
            )
          ) : <div style={{ color: 'var(--text-3)', padding: 40, textAlign: 'center' }}>← 选择左侧的自选组查看成员</div>}
        </div>
      </div>
    </div>
  )
}
