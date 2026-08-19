import { Tabs, Input, Button, message, Select, Switch, Space, Typography, Modal,
         Tag, Divider } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, put } from '../api/client'

const TOOL_GROUPS = [
  {
    label: '📊 行情数据',
    options: [
      { value: 'get_quotes', label: '股票报价' },
      { value: 'get_indices', label: '指数行情' },
      { value: 'get_kline', label: 'K线序列' },
      { value: 'get_block_rank', label: '板块排名' },
      { value: 'get_block_members', label: '板块成分股' },
      { value: 'get_candidates', label: '异动候选' },
      { value: 'get_limit_up', label: '涨停清单' },
      { value: 'get_market_summary', label: '市场概览' },
      { value: 'get_top_amount', label: '成交额排行' },
      { value: 'get_us_market', label: '全球市场快照(美股/商品)' },
    ],
  },
  {
    label: '💰 交易与账户',
    options: [
      { value: 'get_positions', label: '当前持仓' },
      { value: 'get_account', label: '账户资产' },
      { value: 'get_trades', label: '成交流水' },
      { value: 'execute', label: '下单交易 ⚠' },
    ],
  },
  {
    label: '🔍 看盘组合',
    options: [
      { value: 'scan_market', label: '快扫(指数+持仓+自选组+板块+异动)' },
    ],
  },
  {
    label: '📝 文档',
    options: [
      { value: 'save_doc', label: '保存文档' },
      { value: 'get_doc', label: '读文档' },
      { value: 'list_docs', label: '列文档' },
      { value: 'set_doc_meta', label: '改文档meta' },
    ],
  },
  {
    label: '⭐ 自选组',
    options: [
      { value: 'save_watchlist', label: '保存自选组' },
      { value: 'get_watchlist', label: '查自选组' },
      { value: 'get_watchlist_quotes', label: '自选组报价(X/Y)' },
      { value: 'remove_watchlist_member', label: '剔自选组成员' },
    ],
  },
]

function stageIcon(stage: string): string {
  if (stage === '_system') return '⚙️'
  if (stage.includes('live')) return '📊'
  if (stage.includes('premarket')) return '🌅'
  if (stage.includes('close')) return '🌙'
  if (stage.includes('research')) return '🔍'
  if (stage.includes('replay')) return '🔄'
  return '📄'
}

function stageKindLabel(def: any): string {
  if (!def) return ''
  if (def.kind === 'single') return '单次分析'
  if (def.data_mode === 'live') return '实时看盘'
  return '模拟看盘'
}

/** 系统编辑器:一切都是这里改——prompt/阶段/工具/联网 */
export default function SystemEditor({ system, onRun }: {
  system: string
  onRun: (stage: string) => void
}) {
  const qc = useQueryClient()
  const detail = useQuery({
    queryKey: ['systemDetail', system],
    queryFn: () => get(`/systems/${system}`),
  })
  const prompts = useQuery({
    queryKey: ['prompts', system],
    queryFn: () => get(`/systems/${system}/prompts`),
  })

  const [activeTab, setActiveTab] = useState('_system')
  const [content, setContent] = useState('')
  const [dirty, setDirty] = useState(false)
  const [manifestDirty, setManifestDirty] = useState(false)
  const [localStages, setLocalStages] = useState<Record<string, any>>({})
  const [localTools, setLocalTools] = useState<string[]>([])
  const [localWebSearch, setLocalWebSearch] = useState(false)
  const [addStageOpen, setAddStageOpen] = useState(false)
  const [newStage, setNewStage] = useState({ name: '', type: 'single', interval: 5 })
  const [version, setVersion] = useState<number | null>(null)
  const [versions, setVersions] = useState<any[]>([])

  const manifest = detail.data?.manifest
  const stages = manifestDirty ? localStages : (manifest?.stages ?? {})
  const tools = manifestDirty ? localTools : (manifest?.tools ?? [])
  const webSearch = manifestDirty ? localWebSearch : (manifest?.web_search ?? false)

  // 同步 manifest 到本地编辑态
  useEffect(() => {
    if (manifest && !manifestDirty) {
      setLocalStages(manifest.stages ?? {})
      setLocalTools(manifest.tools ?? [])
      setLocalWebSearch(manifest.web_search ?? false)
    }
  }, [manifest])

  // 加载当前 Tab 的 prompt 内容
  useEffect(() => {
    const all = prompts.data ?? []
    const p = activeTab === '_system'
      ? all.find((x: any) => x.stage === '(system)')
      : all.find((x: any) => x.stage === activeTab)
    if (p?.prompt) loadPrompt(p.prompt)
    else { setContent(''); setVersion(null); }
  }, [activeTab, prompts.data])

  async function loadPrompt(p: string) {
    const vs = await get(`/systems/${system}/prompts/${p}/versions`)
    setVersions(vs)
    if (vs.length) {
      const r = await get(`/systems/${system}/prompts/${p}/versions/${vs[0].version}`)
      setContent(r.content)
      setVersion(vs[0].version)
      setDirty(false)
    }
  }

  async function savePrompt() {
    const all = prompts.data ?? []
    const p = activeTab === '_system'
      ? all.find((x: any) => x.stage === '(system)')?.prompt
      : all.find((x: any) => x.stage === activeTab)?.prompt
    if (!p) return
    const r = await put(`/systems/${system}/prompts/${p}`, { content })
    message.success(r.changed ? `已保存 v${r.version}` : '内容未变')
    setDirty(false)
    loadPrompt(p)
    qc.invalidateQueries({ queryKey: ['prompts', system] })
  }

  async function saveManifest() {
    const newManifest = {
      system_prompt: manifest?.system_prompt ?? `${system}-system`,
      stages: localStages,
      tools: localTools,
      web_search: localWebSearch,
    }
    await put(`/systems/${system}/manifest`, { manifest: newManifest })
    message.success('配置已保存')
    setManifestDirty(false)
    qc.invalidateQueries({ queryKey: ['systemDetail', system] })
    qc.invalidateQueries({ queryKey: ['prompts', system] })
    qc.invalidateQueries({ queryKey: ['systems'] })
  }

  function addStage() {
    const { name, type, interval } = newStage
    if (!name.trim()) return
    const stageDef: any = type === 'single'
      ? { kind: 'single', prompt: `${system}-${name}`, request_limit: 100, vars: ['date'] }
      : type === 'live'
      ? { kind: 'loop', prompt: `${system}-${name}`, request_limit: 50,
          data_mode: 'live', clock: 'real', window: '09:35-15:05', skip_lunch: true,
          log_type: `watch_${name}` }
      : { kind: 'loop', prompt: `${system}-${name}`, request_limit: 50,
          data_mode: 'replay', clock: 'simulated', interval: interval || 5,
          window: '09:35-15:00', skip_lunch: true, log_type: `watch_${name}` }
    setLocalStages((prev: any) => ({ ...prev, [name]: stageDef }))
    setManifestDirty(true)
    setAddStageOpen(false)
    setNewStage({ name: '', type: 'single', interval: 5 })
    message.info(`阶段「${name}」已添加,记得保存配置`)
  }

  function removeStage(name: string) {
    setLocalStages((prev: any) => {
      const next = { ...prev }
      delete next[name]
      return next
    })
    setManifestDirty(true)
    if (activeTab === name) setActiveTab('_system')
  }

  const all = prompts.data ?? []
  const currentVersion = all.find((x: any) => x.stage === (activeTab === '_system' ? '(system)' : activeTab))?.latest_version

  return (
    <div>
      {/* 顶部:系统名 + 运行 + 配置保存 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>{system}</Typography.Title>
        <Space>
          {manifestDirty && <Tag color="orange">配置未保存</Tag>}
          <Select size="small" style={{ width: 160 }} placeholder="▶ 运行阶段"
                  onChange={(v) => onRun(v)}
                  options={Object.keys(stages).map(s => ({
                    value: s, label: `${stageIcon(s)} ${s}(${stageKindLabel(stages[s])})`,
                  }))} />
          <Button type="primary" size="small" onClick={saveManifest} disabled={!manifestDirty}>
            保存配置
          </Button>
        </Space>
      </div>

      {/* 阶段 Tab(系统设定第一个 + 动态增删) */}
      <Tabs
        type="editable-card"
        size="small"
        activeKey={activeTab}
        onChange={setActiveTab}
        onEdit={(key, action) => {
          if (action === 'add') setAddStageOpen(true)
          if (action === 'remove' && key !== '_system') removeStage(key as string)
        }}
        items={[
          {
            key: '_system',
            label: `⚙️ 系统设定${currentVersion ? ` (v${currentVersion})` : ''}`,
            closable: false,
          },
          ...Object.keys(stages).map(s => ({
            key: s,
            label: (
              <span>
                {stageIcon(s)} {s}
                <Tag style={{ marginLeft: 4, fontSize: 10 }}>{stageKindLabel(stages[s])}</Tag>
              </span>
            ),
          })),
        ]}
      />

      {/* Prompt 编辑区 */}
      <Space style={{ marginBottom: 8, width: '100%', justifyContent: 'space-between' }}>
        <Select size="small" style={{ width: 140 }} value={version}
                onChange={async (v) => {
                  const p = activeTab === '_system'
                    ? all.find((x: any) => x.stage === '(system)')?.prompt
                    : all.find((x: any) => x.stage === activeTab)?.prompt
                  if (p) {
                    const r = await get(`/systems/${system}/prompts/${p}/versions/${v}`)
                    setContent(r.content); setVersion(v); setDirty(false)
                  }
                }}
                placeholder="版本"
                options={versions.map((v: any) => ({
                  value: v.version,
                  label: `v${v.version}${v.version === versions[0]?.version ? ' (最新)' : ''}`,
                }))} />
        <Space>
          {dirty && <Tag color="orange">未保存</Tag>}
          <Button type="primary" size="small" onClick={savePrompt} disabled={!version || !dirty}>
            保存 prompt
          </Button>
        </Space>
      </Space>

      <Tabs size="small" items={[
        { key: 'edit', label: '✏️ 编辑', forceRender: true,
          children: <Input.TextArea rows={18} value={content}
            onChange={(e) => { setContent(e.target.value); setDirty(true) }}
            style={{ fontSize: 12, fontFamily: 'ui-monospace, SF Mono, Menlo, monospace' }}
            placeholder="在此编写 prompt..." /> },
        { key: 'preview', label: '👁 预览',
          children: <div className="markdown-body" style={{
            minHeight: 350, maxHeight: 550, overflow: 'auto',
            border: '1px solid #d9d9d9', borderRadius: 6, padding: 16 }}>
            {content ? <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
                      : <Typography.Text type="secondary">编辑后此处显示预览</Typography.Text>}
          </div> },
      ]} />

      <Divider />

      {/* 工具白名单(随时改) */}
      <Typography.Text strong style={{ fontSize: 13 }}>🔧 工具白名单</Typography.Text>
      <Select mode="multiple" style={{ width: '100%', marginTop: 8 }} value={tools}
              onChange={(v) => { setLocalTools(v); setManifestDirty(true) }}
              options={TOOL_GROUPS} placeholder="勾选 AI 可调用的工具"
              dropdownStyle={{ maxHeight: 400, overflow: 'auto' }} />

      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Typography.Text strong style={{ fontSize: 13 }}>🌐 联网搜索</Typography.Text>
        <Switch checked={webSearch} onChange={(v) => { setLocalWebSearch(v); setManifestDirty(true) }} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          (AI 可以联网搜索最新消息/新闻)
        </Typography.Text>
      </div>

      {/* 添加阶段弹窗 */}
      <Modal title="添加阶段" open={addStageOpen} onCancel={() => setAddStageOpen(false)}
             onOk={addStage} okText="添加" width={420}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input placeholder="阶段名(如 premarket / close / review)"
                 value={newStage.name}
                 onChange={(e) => setNewStage({ ...newStage, name: e.target.value })} />
          <Select value={newStage.type} style={{ width: '100%' }}
                  onChange={(v) => setNewStage({ ...newStage, type: v })}
                  options={[
                    { value: 'single', label: '📄 单次分析(跑一次出报告)' },
                    { value: 'live', label: '🔴 实时看盘(当前行情,15:05 停)' },
                    { value: 'replay', label: '🔄 模拟看盘(回放某天)' },
                  ]} />
          {newStage.type === 'replay' && (
            <Select value={newStage.interval} style={{ width: '100%' }}
                    onChange={(v) => setNewStage({ ...newStage, interval: v })}
                    options={[1, 3, 5, 10, 15, 20, 30].map(i => ({ value: i, label: `${i} 分钟/轮` }))} />
          )}
        </Space>
      </Modal>
    </div>
  )
}
