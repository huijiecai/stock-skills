import { Card, Table, Tag, Button, Drawer, message, Modal, Form, Input, Select,
         Switch, Space, DatePicker, Typography, Alert, Divider } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { get, post, put, getToken } from '../api/client'
import PromptEditor from '../components/PromptEditor'

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
    label: '📝 文档(报告/笔记/知识)',
    options: [
      { value: 'save_doc', label: '保存文档' },
      { value: 'get_doc', label: '读文档' },
      { value: 'list_docs', label: '列文档' },
      { value: 'set_doc_meta', label: '改文档meta' },
    ],
  },
  {
    label: '⭐ 自选组(股票池)',
    options: [
      { value: 'save_watchlist', label: '保存自选组' },
      { value: 'get_watchlist', label: '查自选组' },
      { value: 'get_watchlist_quotes', label: '自选组报价(X/Y统计)' },
      { value: 'remove_watchlist_member', label: '剔自选组成员' },
    ],
  },
]

const DEFAULT_TOOLS = ['get_quotes', 'get_indices', 'get_kline', 'get_limit_up',
  'get_top_amount', 'get_market_summary', 'get_positions', 'get_account',
  'scan_market', 'save_doc', 'get_doc', 'list_docs']

/** 阶段类型选项 */
const STAGE_TYPES = [
  { value: 'single', label: '📄 单次分析(跑一次出报告)', mode: '' },
  { value: 'replay', label: '🔄 模拟看盘(回放某天 9:35-15:00)', mode: 'replay' },
  { value: 'live', label: '🔴 实时看盘(当前行情,15:05 自动停)', mode: 'live' },
]

/** 模板:一键生成阶段组合 */
const TEMPLATES = [
  {
    value: 'daily',
    label: '📋 每日闭环(盘前分析 → 实时看盘 → 盘后总结)',
    stages: [
      { name: 'premarket', type: 'single', interval: 0 },
      { name: 'live', type: 'live', interval: 5 },
      { name: 'close', type: 'single', interval: 0 },
    ],
  },
  {
    value: 'analysis',
    label: '📄 单次分析(如涨停复盘/专题研究)',
    stages: [{ name: 'run', type: 'single', interval: 0 }],
  },
  {
    value: 'backtest',
    label: '🔄 模拟回测(回放某天看盘)',
    stages: [{ name: 'replay', type: 'replay', interval: 5 }],
  },
  {
    value: 'blank',
    label: '✏️ 自定义(手动添加阶段)',
    stages: [],
  },
]

/** 从阶段行构建 manifest.stages */
function buildStages(rows: any[], systemName: string): Record<string, any> {
  const out: Record<string, any> = {}
  for (const r of rows) {
    if (!r?.name) continue
    if (r.type === 'single') {
      out[r.name] = { kind: 'single', prompt: `${systemName}-${r.name}`,
                      request_limit: 100, vars: ['date'] }
    } else if (r.type === 'live') {
      out[r.name] = { kind: 'loop', prompt: `${systemName}-${r.name}`,
                      request_limit: 50, data_mode: 'live', clock: 'real',
                      window: '09:35-15:05', skip_lunch: true,
                      log_type: `watch_${r.name}` }
    } else { // replay
      out[r.name] = { kind: 'loop', prompt: `${systemName}-${r.name}`,
                      request_limit: 50, data_mode: 'replay', clock: 'simulated',
                      interval: r.interval || 5, window: '09:35-15:00',
                      skip_lunch: true, log_type: `watch_${r.name}` }
    }
  }
  return out
}

/** 阶段类型中文 */
function stageKindLabel(stage: any): string {
  if (!stage) return ''
  if (stage.kind === 'single') return '单次分析'
  if (stage.data_mode === 'live') return '实时看盘'
  return '模拟看盘'
}

export default function Systems() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [runningSystem, setRunningSystem] = useState<string | null>(null)
  const [form] = Form.useForm()
  const [runForm] = Form.useForm()
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get('/systems') })
  const runDetail = useQuery({
    queryKey: ['runSystem', runningSystem],
    queryFn: () => get(`/systems/${runningSystem}`),
    enabled: !!runningSystem,
  })

  const stages = runDetail.data?.manifest?.stages ?? {}
  const stageNames = Object.keys(stages)
  const [selectedStage, setSelectedStage] = useState<string>('')
  const currentStageDef = stages[selectedStage]

  useEffect(() => {
    if (stageNames.length && !selectedStage) setSelectedStage(stageNames[0])
  }, [stageNames])

  async function handleCreate(v: any) {
    const stageRows = (v.stages ?? []).filter((s: any) => s?.name)
    if (stageRows.length === 0) { message.error('至少添加一个阶段'); return }
    const manifestStages = buildStages(stageRows, v.name)
    try {
      await post('/systems', {
        name: v.name,
        manifest: {
          system_prompt: `${v.name}-system`,
          stages: manifestStages,
          tools: v.tools,
          web_search: v.webSearch,
        },
      })
      // 为每个阶段自动创建空 prompt 模板
      for (const r of stageRows) {
        if (r?.name) {
          await put(`/systems/${v.name}/prompts/${v.name}-${r.name}`,
                    { content: `# ${v.name} · ${r.name}\n\n(在此编写此阶段的 prompt...)\n` })
        }
      }
      await put(`/systems/${v.name}/prompts/${v.name}-system`,
                { content: `你是 ${(v.displayName || v.name)} 的 AI agent。\n(在此编写系统级角色设定...)\n` })
      message.success(`系统 ${v.name} 已建(${stageRows.length} 个阶段),现在编辑 prompts`)
      setCreating(false)
      setEditing(v.name)
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch (e: any) { message.error(e.message) }
  }

  async function handleArchive(name: string) {
    try {
      await fetch(`/systems/${name}`, { method: 'DELETE', headers: { Authorization: `Bearer ${getToken()}` } })
      message.success(`系统 ${name} 已归档`)
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch { message.error('归档失败') }
  }

  async function handleRun(v: any) {
    const date = v.date?.format('YYYYMMDD')
    try {
      const r = await post(`/systems/${runningSystem}/run`, {
        date, stage: v.stage, interval: v.interval,
      })
      message.success(r.note || '已发起')
      setRunningSystem(null)
      runForm.resetFields()
    } catch (e: any) { message.error(e.message) }
  }

  // 模板切换时填充阶段列表
  function handleTemplate(templateValue: string) {
    const tpl = TEMPLATES.find(t => t.value === templateValue)
    if (tpl) {
      form.setFieldValue('stages', tpl.stages.map(s => ({ ...s })))
    }
  }

  return (
    <div>
      <Card title="我的交易系统" extra={
        <Button type="primary" onClick={() => { form.resetFields(); setCreating(true) }}>新建系统</Button>
      }>
        <Table rowKey="id" size="small" dataSource={systems.data ?? []}
               columns={[
                 { title: '系统', dataIndex: 'name',
                   render: (n: string) => <a onClick={() => setEditing(n)}><b>{n}</b></a> },
                 { title: '阶段', width: 280,
                   render: (_: any, r: any) => {
                     const st = r.manifest?.stages ?? {}
                     return Object.entries(st).map(([k, v]: [string, any]) => (
                       <Tag key={k}>{k}({stageKindLabel(v)})</Tag>
                     ))
                   }},
                 { title: '状态', dataIndex: 'status', width: 70,
                   render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
                 { title: '', width: 220, render: (_: any, r: any) => (
                   r.status === 'archived' ? <Typography.Text type="secondary">已归档</Typography.Text> : (
                   <Space>
                     <a onClick={() => setEditing(r.name)}>编辑 prompts</a>
                     <a onClick={() => { setRunningSystem(r.name); runForm.resetFields(); setSelectedStage('') }}>▶ 运行</a>
                     <a style={{ color: '#999' }} onClick={() => handleArchive(r.name)}>归档</a>
                   </Space>
                   )
                 )},
               ]} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          新建系统 = 起名 + 选模板(或手动加阶段)+ 勾工具 + 写 prompt,零代码。
          多阶段系统如「盘前分析→实时看盘→盘后总结」一条龙。
        </Typography.Text>
      </Card>

      {/* 新建系统表单 */}
      <Modal title="新建交易系统" open={creating} onCancel={() => setCreating(false)}
             onOk={() => form.submit()} width={680} okText="创建">
        <Form form={form} layout="vertical" onFinish={handleCreate}
              initialValues={{ tools: DEFAULT_TOOLS, webSearch: true, stages: [] }}>
          <Form.Item name="name" label="系统名(英文,如 limitup-review / momentum)"
                     rules={[{ required: true, pattern: /^[a-z0-9-]+$/, message: '小写英文/数字/横杠' }]}>
            <Input placeholder="my-system" />
          </Form.Item>

          {/* 模板快速选择 */}
          <Form.Item label="快速开始(选模板自动填阶段,可再手动改)">
            <Select placeholder="选一个模板..." onChange={handleTemplate}
                    options={TEMPLATES.map(t => ({ value: t.value, label: t.label }))} />
          </Form.Item>

          {/* 动态阶段列表 */}
          <Form.Item label="阶段定义(一个系统可以有多个阶段,如盘前/盘中/盘后)">
            <Form.List name="stages">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} style={{ display: 'flex', marginBottom: 4 }} align="baseline">
                      <Form.Item {...restField} name={[name, 'name']}
                                 rules={[{ required: true, message: '阶段名' }]}>
                        <Input placeholder="阶段名(如 premarket)" style={{ width: 130 }} />
                      </Form.Item>
                      <Form.Item {...restField} name={[name, 'type']} initialValue="single"
                                 rules={[{ required: true }]}>
                        <Select style={{ width: 200 }} options={STAGE_TYPES.map(t => ({
                          value: t.value, label: t.label,
                        }))} />
                      </Form.Item>
                      <Form.Item noStyle shouldUpdate>
                        {({ getFieldValue }) => {
                          const type = getFieldValue(['stages', name, 'type'])
                          return type === 'replay' ? (
                            <Form.Item {...restField} name={[name, 'interval']} initialValue={5}>
                              <Select style={{ width: 100 }} options={[1, 3, 5, 10, 15, 20, 30].map(i => ({
                                value: i, label: `${i}分钟/轮`,
                              }))} />
                            </Form.Item>
                          ) : null
                        }}
                      </Form.Item>
                      <Button type="text" danger onClick={() => remove(name)}>删除</Button>
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add({ type: 'single', interval: 5 })}
                          style={{ width: '100%' }}>+ 添加阶段</Button>
                </>
              )}
            </Form.List>
          </Form.Item>

          <Divider />
          <Form.Item name="tools" label="工具白名单(AI 能用什么,按分类勾选)" rules={[{ required: true }]}>
            <Select mode="multiple" options={TOOL_GROUPS} placeholder="勾选 AI 可调用的工具"
                     dropdownStyle={{ maxHeight: 400, overflow: 'auto' }} />
          </Form.Item>
          <Form.Item name="webSearch" label="联网搜索" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 运行对话框 */}
      <Modal title={`运行:${runningSystem}`} open={!!runningSystem} onCancel={() => setRunningSystem(null)}
             onOk={() => runForm.submit()} okText="开始运行" width={500}>
        {stageNames.length === 0 ? (
          <Alert type="warning" message="该系统没有定义任何阶段" />
        ) : (
          <Form form={runForm} layout="vertical" onFinish={handleRun}>
            <Form.Item name="stage" label="运行哪个阶段" rules={[{ required: true }]}>
              <Select options={stageNames.map(n => ({
                value: n, label: `${n}(${stageKindLabel(stages[n])})`,
              }))}
              onChange={(v) => setSelectedStage(v)} />
            </Form.Item>
            {currentStageDef?.kind === 'single' && (
              <Form.Item name="date" label="交易日" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            )}
            {currentStageDef?.kind === 'loop' && currentStageDef?.data_mode === 'replay' && (
              <>
                <Form.Item name="date" label="回放日期(哪天的行情)" rules={[{ required: true }]}>
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item name="interval" label="每轮间隔(分钟)"
                           initialValue={currentStageDef.interval ?? 5}>
                  <Select options={[1, 3, 5, 10, 15, 20, 30].map(i => ({ value: i, label: `${i} 分钟` }))} />
                </Form.Item>
              </>
            )}
            {currentStageDef?.data_mode === 'live' && (
              <Alert type="info" message="实时看盘:点击开始后立即对接当前行情,15:05 自动停止"
                     style={{ marginBottom: 12 }} />
            )}
            {currentStageDef?.kind === 'single' && (
              <Alert type="info" message="单次分析:跑一次,产出报告后自动结束" style={{ marginBottom: 12 }} />
            )}
            {currentStageDef?.kind === 'loop' && currentStageDef?.data_mode === 'replay' && (
              <Alert type="info" message={`模拟看盘:回放当天行情,9:35 开始循环分析,15:00 收盘结束。${currentStageDef?.window ? `窗口:${currentStageDef.window}` : ''}`}
                     style={{ marginBottom: 12 }} />
            )}
          </Form>
        )}
      </Modal>

      {/* Prompt 编辑抽屉 */}
      <Drawer title={`Prompt 编辑:${editing}`} width={760} open={!!editing} onClose={() => setEditing(null)}>
        {editing && <PromptEditor system={editing} />}
      </Drawer>
    </div>
  )
}
