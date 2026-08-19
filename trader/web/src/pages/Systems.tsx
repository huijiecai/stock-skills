import { Card, Table, Tag, Button, Drawer, message, Modal, Form, Input, Select,
         Switch, Space, DatePicker, Typography, Alert } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { get, post } from '../api/client'
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

/** 阶段类型中文描述 */
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

  // 默认选第一个阶段
  useEffect(() => {
    if (stageNames.length && !selectedStage) setSelectedStage(stageNames[0])
  }, [stageNames])

  async function handleCreate(v: any) {
    try {
      await post('/systems', {
        name: v.name,
        manifest: {
          system_prompt: `${v.name}-system`,
          stages: v.stageKind === 'single'
            ? { run: { kind: 'single', prompt: `${v.name}-prompt`, request_limit: 100, vars: ['date'] } }
            : { replay: { kind: 'loop', prompt: `${v.name}-prompt`, request_limit: 50,
                         data_mode: 'replay', clock: 'simulated', interval: v.interval ?? 5,
                         window: '09:35-15:00', skip_lunch: true, log_type: `watch_${v.name}` } },
          tools: v.tools,
          web_search: v.webSearch,
        },
      })
      message.success(`系统 ${v.name} 已建,现在编辑 prompts`)
      setCreating(false)
      setEditing(v.name)
      qc.invalidateQueries({ queryKey: ['systems'] })
    } catch (e: any) { message.error(e.message) }
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

  return (
    <div>
      <Card title="我的交易系统" extra={
        <Button type="primary" onClick={() => setCreating(true)}>新建系统</Button>
      }>
        <Table rowKey="id" size="small" dataSource={systems.data ?? []}
               columns={[
                 { title: '系统', dataIndex: 'name',
                   render: (n: string) => <a onClick={() => setEditing(n)}><b>{n}</b></a> },
                 { title: '阶段', width: 200,
                   render: (_: any, r: any) => {
                     const st = r.manifest?.stages ?? {}
                     return Object.entries(st).map(([k, v]: [string, any]) => (
                       <Tag key={k}>{k}({stageKindLabel(v)})</Tag>
                     ))
                   }},
                 { title: '状态', dataIndex: 'status', width: 70,
                   render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag> },
                 { title: '', width: 200, render: (_: any, r: any) => (
                   <Space>
                     <a onClick={() => setEditing(r.name)}>编辑 prompts</a>
                     <a onClick={() => { setRunningSystem(r.name); runForm.resetFields() }}>▶ 运行</a>
                   </Space>
                 )},
               ]} />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          新建系统 = 起名 + 选阶段类型 + 勾工具 + 写 prompt,零代码。
          单次分析跑一次出报告;模拟看盘从 9:35 循环到 15:00;实时看盘对接当前行情。
        </Typography.Text>
      </Card>

      {/* 新建系统表单 */}
      <Modal title="新建交易系统" open={creating} onCancel={() => setCreating(false)}
             onOk={() => form.submit()} width={620} okText="创建">
        <Form form={form} layout="vertical" onFinish={handleCreate}
              initialValues={{ stageKind: 'single', tools: DEFAULT_TOOLS, webSearch: true, interval: 5 }}>
          <Form.Item name="name" label="系统名(英文,如 limitup-review / momentum)"
                     rules={[{ required: true, pattern: /^[a-z0-9-]+$/, message: '小写英文/数字/横杠' }]}>
            <Input placeholder="my-system" />
          </Form.Item>
          <Form.Item name="stageKind" label="阶段类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'single', label: '📄 单次分析(跑一次出报告,如涨停复盘/盘前分析/研究)' },
              { value: 'loop', label: '🔄 模拟看盘(回放某天,从 9:35 循环到 15:00)' },
            ]} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => getFieldValue('stageKind') === 'loop' ? (
              <Form.Item name="interval" label="每轮间隔(分钟)">
                <Select options={[1, 3, 5, 10, 15, 20, 30].map(i => ({ value: i, label: `${i} 分钟` }))} />
              </Form.Item>
            ) : null}
          </Form.Item>
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
                value: n,
                label: `${n}(${stageKindLabel(stages[n])})`,
              }))}
              onChange={(v) => setSelectedStage(v)} />
            </Form.Item>

            {/* 根据阶段类型动态适配输入 */}
            {currentStageDef?.kind === 'single' && (
              <Form.Item name="date" label="交易日" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            )}
            {currentStageDef?.kind === 'loop' && (
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
              <Alert type="info" message="实时看盘:点击开始后立即对接当前行情,Ctrl+C 或 15:05 自动停止"
                     style={{ marginBottom: 12 }} />
            )}
            {currentStageDef?.kind === 'single' && (
              <Alert type="info" message="单次分析:跑一次,产出报告后自动结束"
                     style={{ marginBottom: 12 }} />
            )}
            {currentStageDef?.kind === 'loop' && (
              <Alert type="info" message={`模拟看盘:回放当天行情,9:35 开始每轮间隔分析,15:00 收盘结束。${currentStageDef?.window ? `交易窗口:${currentStageDef.window}` : ''}`}
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
