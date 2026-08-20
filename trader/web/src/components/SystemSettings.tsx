/** 系统工作台·设置 Tab:阶段增删 / 工具白名单 / 联网开关 / 归档恢复。低频操作,收在这里。 */
import { Button, Card, Input, message, Modal, Select, Space, Switch, Tag, Typography, Popconfirm } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { get, put, post, del } from '../api/client'
import { TOOL_GROUPS, stageIcon, kindLabel } from '../lib/system'

export default function SystemSettings() {
  const { name = '' } = useParams()
  const system = name
  const qc = useQueryClient()
  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}`) })

  const [stages, setStages] = useState<Record<string, any>>({})
  const [tools, setTools] = useState<string[]>([])
  const [webSearch, setWebSearch] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [dirty, setDirty] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [newStage, setNewStage] = useState({ name: '', type: 'single', interval: 5 })

  const manifest = detail.data?.manifest
  useEffect(() => {
    if (manifest) {
      setStages(manifest.stages ?? {})
      setTools(manifest.tools ?? [])
      setWebSearch(manifest.web_search ?? false)
      setDisplayName(detail.data?.display_name ?? '')
      setDirty(false)
    }
  }, [manifest])

  async function saveManifest() {
    const m = {
      system_prompt: manifest?.system_prompt ?? `${system}-system`,
      stages, tools, web_search: webSearch,
    }
    // 显示名是 systems 列(不在 manifest):单独走 upsert
    await put(`/systems/${encodeURIComponent(system)}/manifest`, { manifest: m })
    await post('/systems', { slug: system, display_name: displayName.trim() || system,
                             manifest: m, status: detail.data?.status ?? 'active' })
    message.success('配置已保存')
    setDirty(false)
    qc.invalidateQueries({ queryKey: ['systemDetail', system] })
    qc.invalidateQueries({ queryKey: ['prompts', system] })
    qc.invalidateQueries({ queryKey: ['systems'] })
  }

  function addStage() {
    const { name, type, interval } = newStage
    if (!name.trim() || stages[name]) { if (stages[name]) message.warning('阶段已存在'); return }
    const d: any = type === 'single'
      ? { kind: 'single', prompt: `${system}-${name}`, request_limit: 100, vars: ['date'] }
      : type === 'live'
      ? { kind: 'loop', prompt: `${system}-${name}`, request_limit: 50,
          window: '09:35-15:05', skip_lunch: true, log_type: `watch_${name}` }
      : { kind: 'loop', prompt: `${system}-${name}`, request_limit: 50,
          interval: interval || 5, window: '09:35-15:00', skip_lunch: true,
          log_type: `watch_${name}` }
    setStages(prev => ({ ...prev, [name]: d }))
    setDirty(true)
    setAddOpen(false)
    setNewStage({ name: '', type: 'single', interval: 5 })
  }

  function removeStage(name: string) {
    setStages(prev => { const n = { ...prev }; delete n[name]; return n })
    setDirty(true)
  }

  async function archive() {
    await del(`/systems/${encodeURIComponent(system)}`)
    message.success('已归档(数据保留,可恢复)')
    qc.invalidateQueries({ queryKey: ['systems'] })
    qc.invalidateQueries({ queryKey: ['systemDetail', system] })
  }

  async function restore() {
    await put(`/systems/${encodeURIComponent(system)}/restore`)
    message.success('已恢复')
    qc.invalidateQueries({ queryKey: ['systems'] })
    qc.invalidateQueries({ queryKey: ['systemDetail', system] })
  }

  if (detail.isLoading) return <Card>加载中…</Card>
  const status = detail.data?.status

  return (
    <div style={{ maxWidth: 860 }}>
      {/* 基本信息 */}
      <Card size="small" title="基本信息">
        <Space direction="vertical" style={{ width: '100%' }} size={6}>
          <Typography.Text strong style={{ fontSize: 13 }}>显示名(侧栏与工作台标题)</Typography.Text>
          <Space.Compact style={{ width: 360 }}>
            <Input value={displayName} placeholder={system}
                   onChange={(e) => { setDisplayName(e.target.value); setDirty(true) }} />
          </Space.Compact>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            标识(路由/prompt 前缀):<span className="mono">{system}</span> · 不可改
          </Typography.Text>
        </Space>
      </Card>

      {/* 阶段管理 */}
      <Card size="small" title="阶段" style={{ marginTop: 16 }} extra={
        <Space>
          {dirty && <Tag color="orange">未保存</Tag>}
          <Button size="small" onClick={() => setAddOpen(true)}>+ 添加阶段</Button>
        </Space>}>
        {Object.entries(stages).map(([name, d]) => (
          <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
            <span>{stageIcon(name)}</span>
            <b style={{ minWidth: 110 }}>{name}</b>
            <Tag>{kindLabel(name, d)}</Tag>
            {d.kind === 'loop' && d.interval != null && <Tag>每 {d.interval} 分钟/轮</Tag>}
            <Tag style={{ marginInlineStart: 'auto' }}>prompt: {d.prompt}</Tag>
            <Popconfirm title={`删除阶段 ${name}?`} description="prompt 版本历史保留,仅从 manifest 移除"
                        onConfirm={() => removeStage(name)} okText="删除" cancelText="取消">
              <a style={{ color: '#cf1322' }}>删除</a>
            </Popconfirm>
          </div>
        ))}
        {!Object.keys(stages).length && <Typography.Text type="secondary">还没有阶段——添加一个开始</Typography.Text>}
      </Card>

      {/* 工具与联网 */}
      <Card size="small" title="AI 能力" style={{ marginTop: 16 }}>
        <Typography.Text strong style={{ fontSize: 13 }}>🔧 工具白名单</Typography.Text>
        <Select mode="multiple" style={{ width: '100%', marginTop: 8 }} value={tools}
                onChange={(v) => { setTools(v); setDirty(true) }}
                options={TOOL_GROUPS} placeholder="勾选 AI 可调用的工具"
                dropdownStyle={{ maxHeight: 400, overflow: 'auto' }} />
        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <Typography.Text strong style={{ fontSize: 13 }}>🌐 联网搜索</Typography.Text>
          <Switch checked={webSearch} onChange={(v) => { setWebSearch(v); setDirty(true) }} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>盘中每轮最多 3 次网页搜索</Typography.Text>
        </div>
      </Card>

      {/* 保存与危险区 */}
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button type="primary" onClick={saveManifest} disabled={!dirty}>保存配置</Button>
        </Space>
        <Space>
          {status === 'archived'
            ? <Button onClick={restore} style={{ color: '#52c41a', borderColor: '#52c41a' }}>恢复此系统</Button>
            : <Popconfirm title="归档此系统?" description="数据与场次历史保留,侧栏灰显,可随时恢复"
                          onConfirm={archive} okText="归档" cancelText="取消">
                <Button danger>归档</Button>
              </Popconfirm>}
        </Space>
      </div>

      {/* 添加阶段 */}
      <Modal title="添加阶段" open={addOpen} onCancel={() => setAddOpen(false)}
             onOk={addStage} okText="添加" width={420}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input placeholder="阶段名(如 premarket / close)" value={newStage.name}
                 onChange={(e) => setNewStage({ ...newStage, name: e.target.value })} />
          <Select value={newStage.type} style={{ width: '100%' }}
                  onChange={(v) => setNewStage({ ...newStage, type: v })}
                  options={[
                    { value: 'single', label: '📄 单次分析' },
                    { value: 'live', label: '🔴 实时看盘' },
                    { value: 'replay', label: '🔄 模拟看盘' }]} />
          {newStage.type === 'replay' && (
            <Select value={newStage.interval} style={{ width: '100%' }}
                    onChange={(v) => setNewStage({ ...newStage, interval: v })}
                    options={[1, 3, 5, 10, 15, 20, 30].map(i => ({ value: i, label: `${i} 分钟/轮` }))} />)}
        </Space>
      </Modal>
    </div>
  )
}
