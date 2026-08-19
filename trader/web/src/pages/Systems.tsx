import { Card, Table, Tag, Button, Drawer, message, Modal, Input, Typography, Space } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { get, post, getToken } from '../api/client'
import SystemEditor from '../components/SystemEditor'

function stageKindLabel(def: any): string {
  if (!def) return ''
  if (def.kind === 'single') return '分析'
  if (def.data_mode === 'live') return '实时'
  return '模拟'
}

function stageIcon(stage: string): string {
  if (stage.includes('live')) return '📊'
  if (stage.includes('premarket')) return '🌅'
  if (stage.includes('close')) return '🌙'
  if (stage.includes('research')) return '🔍'
  if (stage.includes('replay')) return '🔄'
  return '📄'
}

export default function Systems() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get('/systems') })

  async function handleCreate() {
    if (!newName.trim()) return
    try {
      const manifest = {
        system_prompt: `${newName}-system`,
        stages: { run: { kind: 'single', prompt: `${newName}-run`, request_limit: 100, vars: ['date'] } },
        tools: ['get_quotes', 'get_indices', 'get_kline', 'get_limit_up',
          'get_top_amount', 'get_market_summary', 'get_positions', 'get_account',
          'scan_market', 'save_doc', 'get_doc', 'list_docs'],
        web_search: true,
      }
      await post('/systems', { name: newName, manifest: manifest })
      message.success(`系统 ${newName} 已建`)
      setCreating(false)
      setNewName('')
      setEditing(newName)
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch (e: any) { message.error(e.message) }
  }

  async function handleArchive(name: string) {
    try {
      await fetch(`/systems/${name}`, { method: 'DELETE', headers: { Authorization: `Bearer ${getToken()}` } })
      message.success(`已归档`)
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch { message.error('归档失败') }
  }

  async function handleRestore(name: string) {
    try {
      await fetch(`/systems/${name}/restore`, { method: 'PUT', headers: { Authorization: `Bearer ${getToken()}` } })
      message.success(`已恢复`)
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch { message.error('恢复失败') }
  }

  return (
    <div>
      <Card title="我的交易系统" extra={
        <Button type="primary" onClick={() => setCreating(true)}>新建系统</Button>
      }>
        <Table rowKey="id" size="small" dataSource={systems.data ?? []}
               onRow={(r: any) => ({ onClick: () => setEditing(r.name), style: { cursor: 'pointer' } })}
               columns={[
                 { title: '系统', dataIndex: 'name', render: (n: string) => <b>{n}</b> },
                 { title: '阶段', width: 300,
                   render: (_: any, r: any) => {
                     const st = r.manifest?.stages ?? {}
                     return Object.entries(st).map(([k, v]: [string, any]) => (
                       <Tag key={k}>{stageIcon(k)} {k}({stageKindLabel(v)})</Tag>
                     ))
                   }},
                 { title: '状态', dataIndex: 'status', width: 80,
                   render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
                 { title: '', width: 80, render: (_: any, r: any) => (
                   <Space onClick={(e) => e.stopPropagation()}>
                     {r.status === 'archived' ? (
                       <a style={{ color: '#52c41a' }} onClick={() => handleRestore(r.name)}>恢复</a>
                     ) : (
                       <a style={{ color: '#999' }} onClick={() => handleArchive(r.name)}>归档</a>
                     )}
                   </Space>
                 )},
               ]} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          点击系统名进入编辑器 · 新建只需起名,编辑器里配置一切
        </Typography.Text>
      </Card>

      {/* 极简创建:只起名 */}
      <Modal title="新建交易系统" open={creating} onCancel={() => setCreating(false)}
             onOk={handleCreate} okText="创建并开始编辑" width={400}
             okButtonProps={{ disabled: !newName.trim() }}>
        <Input placeholder="系统名(英文,如 my-momentum)" value={newName}
               onChange={(e) => setNewName(e.target.value)}
               onPressEnter={handleCreate} />
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
          创建后自动进入编辑器——在那里写 prompt、加阶段、选工具。
        </Typography.Text>
      </Modal>

      {/* 系统编辑器 */}
      <Drawer title={`编辑系统:${editing}`} width={860} open={!!editing}
              onClose={() => { setEditing(null); qc.invalidateQueries({ queryKey: ['systems'] }) }}>
        {editing && <SystemEditor system={editing} />}
      </Drawer>
    </div>
  )
}
