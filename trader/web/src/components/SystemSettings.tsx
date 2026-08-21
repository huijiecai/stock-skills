/** 系统工作台·设置 Tab:阶段契约 / 工具白名单 / 联网开关 / 归档恢复。 */
import { Button, Card, Input, InputNumber, message, Modal, Select, Space, Switch, Tag, Typography, Popconfirm } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { get, put, post, del } from '../api/client'
import StageContractEditor from './StageContractEditor'
import { validateStageContracts } from '../lib/stageContract'

export default function SystemSettings() {
  const { name = '' } = useParams()
  const system = name
  const qc = useQueryClient()
  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}`) })
  // 工具白名单选项:实时目录(签名/写标记来自注册表自省,与指令台工具面板同源)
  const toolsCat = useQuery({ queryKey: ['toolsCatalog'], queryFn: () => get('/tools'), staleTime: 60_000 })

  const [stages, setStages] = useState<Record<string, any>>({})
  const [tools, setTools] = useState<string[]>([])
  const [webSearch, setWebSearch] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [newStage, setNewStage] = useState({ name: '', type: 'single', interval: 5 })
  const [selectedStage, setSelectedStage] = useState('')

  const manifest = detail.data?.manifest
  useEffect(() => {
    if (manifest) {
      setStages(manifest.stages ?? {})
      setTools(manifest.tools ?? [])
      setWebSearch(manifest.web_search ?? false)
      setDisplayName(detail.data?.display_name ?? '')
      const names = Object.keys(manifest.stages ?? {})
      setSelectedStage(current => names.includes(current) ? current : (names[0] ?? ''))
      setDirty(false)
    }
  }, [manifest, detail.data?.display_name])

  async function saveManifest() {
    const errors = validateStageContracts(stages)
    if (errors.length) {
      message.error(`阶段配置有 ${errors.length} 个问题，请先修正`)
      const first = errors[0].split(/[.:]/, 1)[0]
      if (stages[first]) setSelectedStage(first)
      return
    }
    const m = {
      ...manifest,
      system_prompt: manifest?.system_prompt ?? `${system}-system`,
      stages, tools, web_search: webSearch,
    }
    setSaving(true)
    try {
      // 显示名是 systems 列(不在 manifest):单独走 upsert
      await put(`/systems/${encodeURIComponent(system)}/manifest`, { manifest: m })
      await post('/systems', { slug: system, display_name: displayName.trim() || system,
                               manifest: m, status: detail.data?.status ?? 'active' })
      message.success('配置已保存；新场次将冻结这份阶段契约')
      setDirty(false)
      qc.invalidateQueries({ queryKey: ['systemDetail', system] })
      qc.invalidateQueries({ queryKey: ['prompts', system] })
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setSaving(false)
    }
  }

  function addStage() {
    const { name, type } = newStage
    if (!name.trim() || stages[name]) { if (stages[name]) message.warning('阶段已存在'); return }
    if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(name)) {
      message.error('阶段标识只能使用英文、数字、下划线和连字符，且不能以数字开头')
      return
    }
    const d: any = type === 'single'
      ? { kind: 'single', prompt: `${system}-${name}`, request_limit: 100, vars: ['date'],
          outputs: { result: { kind: 'document', doc_type: `${system}_${name}`,
                               trade_date: '{date}', label: '阶段结果' } } }
      : { kind: 'loop', prompt: `${system}-${name}`, request_limit: 50,
          window: '09:35-15:05', skip_lunch: true, interval: newStage.interval,
          outputs: { decision: { kind: 'document', doc_type: `${system}_${name}`,
                                 name: 'r{rounds}', trade_date: '{date}', label: '本轮判断' } } }
    setStages(prev => ({ ...prev, [name]: d }))
    setSelectedStage(name)
    setDirty(true)
    setAddOpen(false)
    setNewStage({ name: '', type: 'single', interval: 5 })
  }

  function removeStage(name: string) {
    setStages(prev => {
      const n = { ...prev }
      delete n[name]
      setSelectedStage(Object.keys(n)[0] ?? '')
      return n
    })
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
    <div className="system-settings">
      {/* 基本信息 */}
      <Card size="small" title="基本信息">
        <Space orientation="vertical" style={{ width: '100%' }} size={6}>
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
      <Card size="small" title={<span>阶段契约 <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
        定义每个阶段读取什么、产出什么</Typography.Text></span>} style={{ marginTop: 16 }}
        extra={dirty && <Tag color="orange">未保存</Tag>} styles={{ body: { padding: 0 } }}>
        <StageContractEditor stages={stages} selected={selectedStage}
          onSelect={setSelectedStage} onAdd={() => setAddOpen(true)}
          onRemove={removeStage}
          onChange={next => { setStages(next); setDirty(true) }} />
      </Card>

      {/* 工具与联网 */}
      <Card size="small" title="AI 能力" style={{ marginTop: 16 }}>
        <Typography.Text strong style={{ fontSize: 13 }}>🔧 工具白名单</Typography.Text>
        <Select mode="multiple" style={{ width: '100%', marginTop: 8 }} value={tools}
                onChange={(v) => { setTools(v); setDirty(true) }}
                placeholder="勾选 AI 可调用的工具"
                loading={toolsCat.isLoading}
                options={toolsCat.data?.tools?.map((t: any) => ({
                  value: t.name,
                  label: <span>{t.name}
                    {t.write && <Tag color="red" style={{ marginInlineStart: 6, marginInlineEnd: 0 }}>写</Tag>}
                    <Typography.Text type="secondary" style={{ fontSize: 11, marginInlineStart: 6 }}>{t.desc}</Typography.Text>
                  </span>,
                })) ?? []}
                optionFilterProp="value"
                dropdownStyle={{ maxHeight: 420, overflow: 'auto' }} />
        <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
          按名称搜索;完整目录与试运行见指令台右侧「🔧 工具」面板</Typography.Text>
        <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
          <Typography.Text strong style={{ fontSize: 13 }}>🌐 联网搜索</Typography.Text>
          <Switch checked={webSearch} onChange={(v) => { setWebSearch(v); setDirty(true) }} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>盘中每轮最多 3 次网页搜索</Typography.Text>
        </div>
      </Card>

      {/* 保存与危险区 */}
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button type="primary" loading={saving} onClick={saveManifest} disabled={!dirty}>保存配置</Button>
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
        <Space orientation="vertical" style={{ width: '100%' }}>
          <Input placeholder="阶段标识，如 prepare / observe" value={newStage.name}
                 onChange={(e) => setNewStage({ ...newStage, name: e.target.value })} />
          <Select value={newStage.type} style={{ width: '100%' }}
                  onChange={(v) => setNewStage({ ...newStage, type: v })}
                  options={[
                    { value: 'single', label: '📄 单次分析' },
                    { value: 'loop', label: '🔁 循环值守(时钟在运行时选择)' }]} />
          {newStage.type === 'loop' && <div>
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 5, fontSize: 12 }}>默认模拟步进（分钟）</Typography.Text>
            <InputNumber min={1} max={240} value={newStage.interval} style={{ width: '100%' }}
              onChange={interval => setNewStage({ ...newStage, interval: interval ?? 5 })} />
          </div>}
        </Space>
      </Modal>
    </div>
  )
}
