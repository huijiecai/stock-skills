import { Card, Table, Tag, Button, Drawer, message } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { get, post } from '../api/client'
import PromptEditor from '../components/PromptEditor'

export default function Systems() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get('/systems') })

  async function createSystem() {
    const name = prompt('系统名(英文/拼音,如 my-momentum):')
    if (!name) return
    try {
      await post('/systems', {
        name,
        manifest: {
          system_prompt: `${name}-system`,
          stages: {
            replay: { kind: 'loop', prompt: `${name}-round`, request_limit: 50,
                      data_mode: 'replay', clock: 'simulated', interval: 5,
                      window: '09:35-15:00', skip_lunch: true, log_type: `watch_${name}` },
          },
          tools: ['get_quotes', 'get_indices', 'get_kline', 'get_top_amount',
                  'get_positions', 'get_account', 'get_trades', 'execute',
                  'scan_market', 'save_doc', 'get_doc', 'list_docs', 'set_doc_meta',
                  'save_watchlist', 'get_watchlist', 'get_watchlist_quotes'],
          web_search: true,
        },
      })
      message.success(`系统 ${name} 已建,现在编辑它的 prompts`)
      setEditing(name)
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch (e: any) { message.error(e.message) }
  }

  return (
    <Card title="我的交易系统" extra={<Button type="primary" onClick={createSystem}>新建系统</Button>}>
      <Table rowKey="id" size="small" dataSource={systems.data ?? []}
             columns={[
               { title: '系统', dataIndex: 'name',
                 render: (n: string) => <a onClick={() => setEditing(n)}><b>{n}</b></a> },
               { title: '状态', dataIndex: 'status', width: 90,
                 render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
               { title: '更新', dataIndex: 'updated_at', width: 170, render: (v: string) => v?.slice(0, 19) },
               { title: '', width: 90,
                 render: (_: any, r: any) => <a onClick={() => setEditing(r.name)}>编辑 prompts</a> },
             ]} />
      <Drawer title={`Prompt 编辑:${editing}`} width={760} open={!!editing} onClose={() => setEditing(null)}>
        {editing && <PromptEditor system={editing} />}
      </Drawer>
    </Card>
  )
}
