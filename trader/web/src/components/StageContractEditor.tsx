import { Alert, Button, Input, InputNumber, Popconfirm, Segmented, Select, Switch, Tag, Tooltip, Typography, message } from 'antd'
import { useMemo, useState } from 'react'
import { kindLabel, orderedStages, stageIcon, stageLabel } from '../lib/system'
import { sourceValue, validateStageContracts } from '../lib/stageContract'

type Stages = Record<string, any>
type Group = 'inputs' | 'outputs'

const SELECTORS = [
  { value: 'latest', label: '最新一份' },
  { value: 'previous', label: '最近几份' },
  { value: 'recent', label: '最近几份（兼容）' },
  { value: 'all', label: '全部' },
]

function nextKey(rows: Record<string, any>, prefix: string): string {
  let n = 1
  while (rows[`${prefix}_${n}`]) n += 1
  return `${prefix}_${n}`
}

function splitWindow(value: string | undefined): [string, string] {
  const [start = '', end = ''] = (value || '').split('-', 2)
  return [start, end]
}

function KeyInput({ value, onCommit }: { value: string, onCommit: (next: string) => boolean }) {
  const [draft, setDraft] = useState(value)
  function commit() {
    const next = draft.trim()
    if (!next || next === value) { setDraft(value); return }
    if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(next)) {
      message.error('标识只能使用英文、数字、下划线和连字符，且不能以数字开头')
      setDraft(value)
      return
    }
    if (!onCommit(next)) setDraft(value)
  }
  return <Input className="stage-key-input mono" value={draft} onChange={e => setDraft(e.target.value)}
                onBlur={commit} onPressEnter={commit} />
}

interface Props {
  stages: Stages
  selected: string
  onSelect: (name: string) => void
  onChange: (stages: Stages) => void
  onAdd: () => void
  onRemove: (name: string) => void
}

export default function StageContractEditor({ stages, selected, onSelect, onChange, onAdd, onRemove }: Props) {
  const stage = stages[selected]
  const errors = validateStageContracts(stages)
  const selectedErrors = errors.filter(e => e.startsWith(`${selected}:`) || e.startsWith(`${selected}.`))
  const sourceOptions = useMemo(() => orderedStages(stages).flatMap(([stageName, d]: [string, any]) =>
    Object.entries(d.outputs ?? {}).map(([outputName, output]: [string, any]) => ({
      value: `${stageName}.${outputName}`,
      label: `${stageLabel(stageName, d)} / ${(output as any).label || outputName}`,
    }))), [stages])

  function patchStage(patch: Record<string, any>) {
    onChange({ ...stages, [selected]: { ...stage, ...patch } })
  }

  function patchEntry(group: Group, key: string, patch: Record<string, any>) {
    patchStage({ [group]: { ...(stage[group] ?? {}), [key]: { ...(stage[group]?.[key] ?? {}), ...patch } } })
  }

  function renameEntry(group: Group, oldKey: string, newKey: string): boolean {
    if (stage[group]?.[newKey]) { message.error(`标识 ${newKey} 已存在`); return false }
    const rows: Record<string, any> = {}
    for (const [key, value] of Object.entries(stage[group] ?? {})) rows[key === oldKey ? newKey : key] = value
    const nextStages = { ...stages, [selected]: { ...stage, [group]: rows } }
    if (group === 'outputs') {
      const oldRef = `${selected}.${oldKey}`
      const newRef = `${selected}.${newKey}`
      for (const [name, d] of Object.entries(nextStages) as [string, any][]) {
        const inputs = Object.fromEntries(Object.entries(d.inputs ?? {}).map(([slot, spec]: [string, any]) =>
          [slot, sourceValue(spec.from) === oldRef ? { ...spec, from: newRef } : spec]))
        nextStages[name] = { ...d, inputs }
      }
    }
    onChange(nextStages)
    return true
  }

  function removeEntry(group: Group, key: string) {
    const rows = { ...(stage[group] ?? {}) }
    delete rows[key]
    patchStage({ [group]: rows })
  }

  function addInput() {
    const inputs = stage.inputs ?? {}
    const key = nextKey(inputs, 'input')
    patchStage({ inputs: { ...inputs, [key]: {
      kind: 'artifact', from: sourceOptions[0]?.value ?? '', selector: 'latest', required: false, label: '阶段输入',
    } } })
  }

  function addOutput() {
    const outputs = stage.outputs ?? {}
    const key = nextKey(outputs, 'output')
    patchStage({ outputs: { ...outputs, [key]: {
      kind: 'artifact', capture: 'final',
      trade_date: '{date}', label: '阶段结果',
    } } })
  }

  if (!stage) return (
    <div className="stage-config-empty">
      <Typography.Text type="secondary">还没有阶段。</Typography.Text>
      <Button type="primary" onClick={onAdd}>添加阶段</Button>
    </div>
  )

  const [windowStart, windowEnd] = splitWindow(stage.window)
  return (
    <div className="stage-config-shell">
      <aside className="stage-config-nav">
        <div className="stage-config-nav-head">
          <span>执行阶段</span>
          <Tooltip title="添加阶段"><Button size="small" type="text" onClick={onAdd}>＋</Button></Tooltip>
        </div>
        {orderedStages(stages).map(([name, d]: [string, any]) => (
          <button key={name} className={`stage-config-nav-item${selected === name ? ' active' : ''}`}
                  onClick={() => onSelect(name)}>
            <span className="stage-config-icon">{stageIcon(name)}</span>
            <span className="stage-config-nav-copy">
              <b>{stageLabel(name, d)}</b>
              <small><span className="mono">{name}</span> · {kindLabel(name, d)}</small>
            </span>
            <span className="stage-config-count">{Object.keys(d.inputs ?? {}).length}→{Object.keys(d.outputs ?? {}).length}</span>
          </button>
        ))}
      </aside>

      <section className="stage-config-editor">
        <div className="stage-config-title">
          <div>
            <span className="stage-config-eyebrow">阶段定义</span>
            <h3>{stageIcon(selected)} {stageLabel(selected, stage)} <code>{selected}</code></h3>
          </div>
          <Popconfirm title={`删除阶段 ${selected}?`} description="其 Prompt 版本和历史场次不会删除"
                      onConfirm={() => onRemove(selected)} okText="删除" cancelText="取消">
            <Button danger size="small">删除阶段</Button>
          </Popconfirm>
        </div>

        {selectedErrors.length > 0 && <Alert type="error" showIcon style={{ marginBottom: 14 }}
          message="当前阶段还不能保存" description={selectedErrors.join('；')} />}

        <div className="stage-config-block">
          <div className="stage-config-block-head">
            <div><b>基本信息</b><span>决定如何执行以及使用哪条 Prompt</span></div>
          </div>
          <div className="stage-field-grid">
            <label><span>显示名称</span><Input value={stage.label ?? ''} placeholder={selected}
              onChange={e => patchStage({ label: e.target.value })} /></label>
            <label><span>执行方式</span><Segmented block value={stage.kind ?? 'single'}
              options={[{ value: 'single', label: '单次' }, { value: 'loop', label: '循环' }]}
              onChange={kind => patchStage({ kind })} /></label>
            <label className="span-2"><span>Prompt 标识</span><Input className="mono" value={stage.prompt ?? ''}
              onChange={e => patchStage({ prompt: e.target.value })} /></label>
            <label><span>最大模型请求数</span><InputNumber min={1} max={1000} style={{ width: '100%' }}
              value={stage.request_limit ?? 100} onChange={v => patchStage({ request_limit: v ?? 100 })} /></label>
            {stage.kind === 'loop' && <>
              <label><span>运行窗口</span><div className="stage-window"><Input value={windowStart} placeholder="09:35"
                onChange={e => patchStage({ window: `${e.target.value}-${windowEnd}` })} /><i>至</i>
                <Input value={windowEnd} placeholder="15:05"
                  onChange={e => patchStage({ window: `${windowStart}-${e.target.value}` })} /></div></label>
              <label><span>模拟步进（分钟）</span><InputNumber min={1} max={240} style={{ width: '100%' }}
                value={stage.interval} placeholder="运行时指定" onChange={v => patchStage({ interval: v })} /></label>
              <label className="stage-switch-field"><span>跳过午休</span><Switch checked={stage.skip_lunch ?? false}
                onChange={skip_lunch => patchStage({ skip_lunch })} /></label>
            </>}
          </div>
        </div>

        <div className="stage-config-block">
          <div className="stage-config-block-head">
            <div><b>输入</b><span>运行前由平台读取，并作为明确上下文交给模型</span></div>
            <Button size="small" onClick={addInput}>＋ 添加输入</Button>
          </div>
          {Object.entries(stage.inputs ?? {}).map(([slot, spec]: [string, any]) => (
            <div className="stage-contract-row" key={slot}>
              <div className="stage-contract-row-head">
                <Tag color="blue">输入</Tag><KeyInput value={slot} onCommit={next => renameEntry('inputs', slot, next)} />
                <Tooltip title="移除输入"><Button type="text" danger onClick={() => removeEntry('inputs', slot)}>×</Button></Tooltip>
              </div>
              <div className="stage-contract-grid input-grid">
                <label><span>显示名称</span><Input value={spec.label ?? ''}
                  onChange={e => patchEntry('inputs', slot, { label: e.target.value })} /></label>
                <label className="span-2"><span>来源阶段输出</span><Select showSearch value={sourceValue(spec.from) || undefined}
                  placeholder="选择 stage.output" options={sourceOptions}
                  onChange={from => patchEntry('inputs', slot, { kind: 'artifact', from })} /></label>
                <label><span>选择策略</span><Select value={spec.selector ?? 'latest'} options={SELECTORS}
                  onChange={selector => patchEntry('inputs', slot, { selector })} /></label>
                {['previous', 'recent'].includes(spec.selector) && <label><span>最近份数</span>
                  <InputNumber min={1} max={100} style={{ width: '100%' }} value={spec.limit ?? 3}
                    onChange={limit => patchEntry('inputs', slot, { limit: limit ?? 1 })} /></label>}
                <label><span>最大字符数</span><InputNumber min={1000} step={1000} style={{ width: '100%' }}
                  value={spec.max_chars ?? 24000}
                  onChange={max_chars => patchEntry('inputs', slot, { max_chars: max_chars ?? 24000 })} /></label>
                <label className="stage-switch-field"><span>必需输入</span><Switch checked={spec.required ?? false}
                  onChange={required => patchEntry('inputs', slot, { required })} /></label>
              </div>
            </div>
          ))}
          {!Object.keys(stage.inputs ?? {}).length && <div className="stage-contract-none">本阶段没有声明上游输入</div>}
        </div>

        <div className="stage-config-block">
          <div className="stage-config-block-head">
            <div><b>输出</b><span>模型最终回答由平台自动发布，并可供其他阶段引用</span></div>
            <Button size="small" onClick={addOutput}>＋ 添加输出</Button>
          </div>
          {Object.entries(stage.outputs ?? {}).map(([slot, spec]: [string, any]) => (
            <div className="stage-contract-row" key={slot}>
              <div className="stage-contract-row-head">
                <Tag color="green">{spec.kind === 'artifact' || !spec.kind ? '阶段产物' : spec.kind}</Tag><KeyInput value={slot} onCommit={next => renameEntry('outputs', slot, next)} />
                <span className="stage-contract-capture">最终回答</span>
                <Tooltip title="移除输出"><Button type="text" danger onClick={() => removeEntry('outputs', slot)}>×</Button></Tooltip>
              </div>
              <div className="stage-contract-grid">
                <label><span>显示名称</span><Input value={spec.label ?? ''}
                  onChange={e => patchEntry('outputs', slot, { label: e.target.value })} /></label>
                <Typography.Text type="secondary" style={{ fontSize: 12, alignSelf: 'center' }}>
                  存储类型、名称和归档由平台自动处理
                </Typography.Text>
              </div>
            </div>
          ))}
          {!Object.keys(stage.outputs ?? {}).length && <div className="stage-contract-none">本阶段不自动发布阶段产物</div>}
        </div>
      </section>
    </div>
  )
}
