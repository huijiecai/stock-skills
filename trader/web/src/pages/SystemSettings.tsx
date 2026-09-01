/** 系统工作台·设置 Tab:阶段契约 / 系统策略 / 归档恢复。 */
import { Button, Card, Input, InputNumber, message, Modal, Select, Space, Switch, Tag, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { get, put, post, del } from '../api/client'
import type { SystemRow, ManifestOut, SystemBrief, DeleteOut, RestoreOut, StageDef, Stages } from '../api/types'
import StageContractEditor from './StageContractEditor'
import { nextStageId, validateStageContracts } from '../lib/stageContract'
import { OP, STATUS } from '../lib/icons'
import { ConfirmAction } from '../lib/ui'
import './SystemSettings.css'

/** manifest 是自由 JSON(阶段结构由 stageContract 库校验),这里只声明本页消费的键;
 * 索引签名保证保存时 ...manifest 原样透传其余键。 */
interface ManifestShape {
  system_prompt?: string
  web_search?: boolean   // 旧版平铺键(现归 policy)
  stages?: Stages
  policy?: { web_search?: boolean; resource_write?: boolean
             simulation_trading?: boolean; live_trading?: boolean }
  [key: string]: unknown
}

export default function SystemSettings() {
  const { name = '' } = useParams()
  const system = name
  const qc = useQueryClient()
  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get<SystemRow>(`/systems/${encodeURIComponent(system)}`) })
  const [stages, setStages] = useState<Stages>({})
  const [webSearch, setWebSearch] = useState(false)
  const [resourceWrite, setResourceWrite] = useState(false)
  const [simulationTrading, setSimulationTrading] = useState(true)
  const [liveTrading, setLiveTrading] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [newStage, setNewStage] = useState({ label: '', type: 'single', interval: 5 })
  const [selectedStage, setSelectedStage] = useState('')

  const manifest = detail.data?.manifest as ManifestShape | undefined
  useEffect(() => {
    if (manifest) {
      setStages(manifest.stages ?? {})
      const policy = manifest.policy ?? {}
      setWebSearch(policy.web_search ?? manifest.web_search ?? false)
      setResourceWrite(policy.resource_write ?? false)
      setSimulationTrading(policy.simulation_trading ?? true)
      setLiveTrading(policy.live_trading ?? false)
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
      stages,
      policy: { web_search: webSearch, resource_write: resourceWrite,
                simulation_trading: simulationTrading, live_trading: liveTrading },
    }
    setSaving(true)
    try {
      // 显示名是 systems 列(不在 manifest):单独走 upsert
      await put<ManifestOut>(`/systems/${encodeURIComponent(system)}/manifest`, { manifest: m })
      await post<SystemBrief>('/systems', { slug: system, display_name: displayName.trim() || system,
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
    const label = newStage.label.trim()
    const { type } = newStage
    if (!label) return
    const stageId = nextStageId(stages, label)
    const d: StageDef = type === 'single'
      ? { label, kind: 'single', prompt: `${system}-${stageId}`, request_limit: 100,
          outputs: { result: { kind: 'artifact',
                               label: '阶段结果' } } }
      : { label, kind: 'loop', prompt: `${system}-${stageId}`, request_limit: 50,
          window: '09:35-15:05', skip_lunch: true, interval: newStage.interval,
          outputs: { decision: { kind: 'artifact',
                                 label: '本轮判断' } } }
    setStages(prev => ({ ...prev, [stageId]: d }))
    setSelectedStage(stageId)
    setDirty(true)
    setAddOpen(false)
    setNewStage({ label: '', type: 'single', interval: 5 })
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
    await del<DeleteOut>(`/systems/${encodeURIComponent(system)}`)
    message.success('已归档(数据保留,可恢复)')
    qc.invalidateQueries({ queryKey: ['systems'] })
    qc.invalidateQueries({ queryKey: ['systemDetail', system] })
  }

  async function restore() {
    await put<RestoreOut>(`/systems/${encodeURIComponent(system)}/restore`)
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

      {/* 系统级安全策略 */}
      <Card size="small" title="AI 能力" style={{ marginTop: 16 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
          行情、组合、研究和交易工具由 Prompt 按需调用；这里仅配置有副作用或有成本的系统级策略。
        </Typography.Text>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <Typography.Text strong style={{ fontSize: 13 }}><OP.globe /> 联网搜索</Typography.Text>
          <Switch checked={webSearch} onChange={(v) => { setWebSearch(v); setDirty(true) }} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>允许模型主动检索外部信息</Typography.Text>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <Typography.Text strong style={{ fontSize: 13 }}><OP.star /> 修改自选组</Typography.Text>
          <Switch checked={resourceWrite} onChange={(v) => { setResourceWrite(v); setDirty(true) }} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>允许保存或移除标的集合成员</Typography.Text>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <Typography.Text strong style={{ fontSize: 13 }}><OP.lab /> 模拟交易</Typography.Text>
          <Switch checked={simulationTrading} onChange={(v) => { setSimulationTrading(v); setDirty(true) }} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>允许在模拟组合中执行交易</Typography.Text>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Typography.Text strong style={{ fontSize: 13 }}><STATUS.warn /> 实盘交易</Typography.Text>
          <Switch checked={liveTrading} onChange={(v) => { setLiveTrading(v); setDirty(true) }} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>仅在明确授权后开放真实下单</Typography.Text>
        </div>
      </Card>

      {/* 保存与危险区 */}
      <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Button type="primary" loading={saving} onClick={saveManifest} disabled={!dirty}>保存配置</Button>
        </Space>
        <Space>
          {status === 'archived'
            ? <Button onClick={restore} style={{ color: 'var(--down)', borderColor: 'var(--down)' }}>恢复此系统</Button>
            : <ConfirmAction title="归档此系统?" description="数据与场次历史保留,侧栏灰显,可随时恢复"
                             danger okText="归档" onConfirm={archive}>
                <Button danger>归档</Button>
              </ConfirmAction>}
        </Space>
      </div>

      {/* 添加阶段 */}
      <Modal title="添加阶段" open={addOpen} onCancel={() => setAddOpen(false)}
             onOk={addStage} okText="添加" width={420}
             okButtonProps={{ disabled: !newStage.label.trim() }}>
        <Space orientation="vertical" style={{ width: '100%' }}>
          <label><Typography.Text strong style={{ fontSize: 13 }}>阶段名称</Typography.Text>
            <Input autoFocus placeholder="例如：盘前研究、盘中观察、盘后复盘" value={newStage.label}
                   onPressEnter={addStage}
                   onChange={(e) => setNewStage({ ...newStage, label: e.target.value })} />
          </label>
          <label><Typography.Text strong style={{ fontSize: 13 }}>执行方式</Typography.Text>
            <Select value={newStage.type} style={{ width: '100%' }}
                    onChange={(v) => setNewStage({ ...newStage, type: v })}
                    options={[
                      { value: 'single', label: '单次分析' },
                      { value: 'loop', label: '循环值守(时钟在运行时选择)' }]} />
          </label>
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
