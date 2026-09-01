import type { Stages } from '../api/types'

export function sourceValue(source: unknown): string {
  if (typeof source === 'string') return source
  if (source && typeof source === 'object') {
    const { stage, output } = source as { stage?: unknown; output?: unknown }
    if (typeof stage === 'string' && typeof output === 'string' && stage && output)
      return `${stage}.${output}`
  }
  return ''
}

/** Internal manifest key for a newly-created stage. User-facing labels may be Chinese. */
export function nextStageId(stages: Stages, label: string): string {
  const ascii = label.trim().toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9_-]/g, '')
    .replace(/^[^a-z_]+/, '')
  const base = ascii || 'stage'
  if (!stages[base]) return base
  let suffix = 2
  while (stages[`${base}-${suffix}`]) suffix += 1
  return `${base}-${suffix}`
}

export function validateStageContracts(stages: Stages): string[] {
  const errors: string[] = []
  for (const [stageName, stage] of Object.entries(stages)) {
    if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(stageName)) errors.push(`${stageName}:阶段标识格式无效`)
    if (!(stage.prompt ?? '').trim()) errors.push(`${stageName}:必须指定 Prompt`)
    if (!['single', 'loop'].includes(stage.kind || 'single'))
      errors.push(`${stageName}:执行方式必须是单次或循环`)
    for (const [slot, spec] of Object.entries(stage.outputs ?? {})) {
      if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(slot)) errors.push(`${stageName}.${slot}:输出标识格式无效`)
      const kind = spec.kind ?? 'artifact'
      if (!['artifact', 'document', 'resource', 'action', 'metric'].includes(kind))
        errors.push(`${stageName}.${slot}:输出类型无效`)
      if (kind === 'document' && !(spec.doc_type ?? '').trim())
        errors.push(`${stageName}.${slot}:旧式文档输出必须填写文档类型`)
    }
    for (const [slot, spec] of Object.entries(stage.inputs ?? {})) {
      const source = sourceValue(spec.from)
      const dot = source.indexOf('.')
      const sourceStage = dot > 0 ? source.slice(0, dot) : ''
      const sourceOutput = dot > 0 ? source.slice(dot + 1) : ''
      if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(slot)) errors.push(`${stageName}.${slot}:输入标识格式无效`)
      const kind = spec.kind ?? 'artifact'
      if (kind !== 'artifact') errors.push(`${stageName}.${slot}:阶段输入只能引用阶段产物`)
      if (!sourceStage || !sourceOutput || !stages[sourceStage]?.outputs?.[sourceOutput])
        errors.push(`${stageName}.${slot}:来源 ${source || '(未选择)'} 不存在`)
      const selector = spec.selector ?? 'latest'
      if (!['latest', 'previous', 'recent', 'all'].includes(selector))
        errors.push(`${stageName}.${slot}:选择策略无效`)
      if (['previous', 'recent'].includes(selector) && Number(spec.limit ?? 1) < 1)
        errors.push(`${stageName}.${slot}:最近份数必须大于 0`)
      if (spec.max_chars != null && Number(spec.max_chars) < 1000)
        errors.push(`${stageName}.${slot}:最大字符数不能小于 1000`)
    }
  }
  return errors
}
