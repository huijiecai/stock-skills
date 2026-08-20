/** 阶段工作区·场次 Tab:该阶段的场次(版本列可追溯)+ 勾两场对比 + 运行中轮询 + 停止/强封存。 */
import { Table, Tag, Button, Empty, Popconfirm, Space, Tooltip, message } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../api/client'
import { shortPromptName, parsePromptVersions, inferRunStage } from '../lib/system'
import { PnlTag, KindBadge } from '../lib/ui'

/** 封面 prompt 版本 chips(sys v3 · pre v5),tooltip 展开全名。 */
function VersionChips({ raw, system }: { raw: unknown; system: string }) {
  const pv = parsePromptVersions(raw)
  const entries = Object.entries(pv)
  if (!entries.length) return <span style={{ color: '#bbb' }}>-</span>
  return (
    <Space size={4} wrap>
      {entries.map(([k, v]) => (
        <Tooltip key={k} title={k}>
          <Tag color="purple" style={{ marginInlineEnd: 0 }}>{shortPromptName(k, system)} v{v}</Tag>
        </Tooltip>
      ))}
    </Space>
  )
}

export default function SystemRuns() {
  const { name = '', stage = '' } = useParams()
  const system = name
  const nav = useNavigate()

  // 有 running 场 → 5 秒轮询;否则 30 秒
  const runs = useQuery({
    queryKey: ['systemRuns', system],
    queryFn: () => get(`/runs?system=${encodeURIComponent(system)}`),
    refetchInterval: (query) => {
      const active = (query.state.data ?? []).some((r: any) => r.status === 'running' || r.status === 'stopping')
      return active ? 5000 : 30000
    },
  })

  const all: any[] = runs.data ?? []
  const stageRuns = stage ? all.filter(r => inferRunStage(r, system) === stage) : all
  const [sel, setSel] = useState<number[]>([])
  const qc = useQueryClient()

  async function stopRun(id: number) {
    try {
      const r = await post(`/runs/${id}/stop`)
      message.success(r.note || '已请求停止')
      qc.invalidateQueries({ queryKey: ['systemRuns', system] })
    } catch (e: any) { message.error(e.message) }
  }

  async function sealRun(id: number) {
    try {
      await post(`/runs/${id}/seal`)
      message.success('已强制封存')
      qc.invalidateQueries({ queryKey: ['systemRuns', system] })
    } catch (e: any) { message.error(e.message) }
  }

  return (
    <>
      <Table rowKey="id" size="small" loading={runs.isLoading}
             rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as number[]) }}
             dataSource={stageRuns} pagination={stageRuns.length > 15 ? { pageSize: 15 } : false}
             locale={{ emptyText: (
               <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={<span>这个阶段还没有跑过——右上 <b>▶ 运行此阶段</b> 开始第一场</span>} />
             ) }}
             columns={[
               { title: '#', dataIndex: 'id', width: 50 },
               { title: '场次', render: (_: any, r: any) => <Link to={`/runs/${r.id}`}>{r.slug}</Link> },
               { title: '类型', dataIndex: 'kind', width: 70,
                 render: (_: any, r: any) => <KindBadge kind={r.kind} /> },
               { title: '数据日', dataIndex: 'trade_date', width: 95 },
               { title: 'prompt 版本', width: 170, render: (_: any, r: any) => <VersionChips raw={r.prompt_versions} system={system} /> },
               { title: '收益', width: 95,
                 render: (_: any, r: any) => r.metrics ? <PnlTag value={r.metrics.return_pct} /> : '-' },
               { title: '回撤', width: 70,
                 render: (_: any, r: any) => r.metrics ? `${r.metrics.max_drawdown_pct}%` : '-' },
               { title: '状态', dataIndex: 'status', width: 95,
                 render: (s: string) =>
                   s === 'running' ? <span className="st-badge st-run"><span className="rd-live">●</span>执行中</span>
                   : s === 'stopping' ? <span className="st-badge st-neutral">停止中</span>
                   : <span className="st-badge st-ok">已封场</span> },
               { title: '', width: 90, render: (_: any, r: any) => (
                 <Space size={12}>
                   {r.status === 'running' && (
                     <Popconfirm title={`停止 #${r.id}?`} description="当前轮完成后封场退出"
                                 onConfirm={() => stopRun(r.id)} okText="停止" cancelText="取消">
                       <a style={{ color: '#cf1322' }}>停止</a>
                     </Popconfirm>
                   )}
                   {r.status === 'stopping' && (
                     <Popconfirm title="强制封存?" description="进程已死无法收敛时使用,直接置为已封存"
                                 onConfirm={() => sealRun(r.id)} okText="封存" cancelText="取消">
                       <a style={{ color: '#cf1322' }}>强制封存</a>
                     </Popconfirm>
                   )}
                 </Space>
               )},
             ]}
             footer={() => sel.length === 2 ? (
               <Button type="primary" size="small"
                       onClick={() => nav(`/compare?ids=${sel.join(',')}`)}>
                 对比勾选的两场
               </Button>
             ) : (
               <span style={{ fontSize: 12, color: '#999' }}>勾选两场可对比归因(同日不同版本 = 干净对比)</span>
             )} />
    </>
  )
}
