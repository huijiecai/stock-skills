/** 系统相关的共享常量与小工具(工具白名单/阶段图标/类型标签)。 */
import type { StageDef, Stages } from '../api/types'

// 阶段图标已迁 lib/icons(T3.2 图标体系),此处 re-export 保持既有 import 路径兼容
export { stageIcon } from './icons'

export const TOOL_GROUPS = [
  {
    label: '行情数据',
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
      { value: 'get_us_market', label: '全球市场快照' },
    ],
  },
  {
    label: '交易与账户',
    options: [
      { value: 'get_positions', label: '当前持仓' },
      { value: 'get_account', label: '账户资产' },
      { value: 'get_trades', label: '成交流水' },
      { value: 'execute', label: '下单交易(危险)' },
    ],
  },
  { label: '看盘组合', options: [{ value: 'scan_market', label: '快扫' }] },
  { label: '文档', options: [
    { value: 'save_doc', label: '保存文档' }, { value: 'get_doc', label: '读文档' },
    { value: 'list_docs', label: '列文档' }, { value: 'set_doc_meta', label: '改meta' }] },
  { label: '自选组', options: [
    { value: 'save_watchlist', label: '保存' }, { value: 'get_watchlist', label: '查' },
    { value: 'get_watchlist_quotes', label: '报价(X/Y)' }, { value: 'remove_watchlist_member', label: '剔成员' }] },
]


/** 阶段默认中文标签;manifest 里 stages[x].label 可覆盖。 */
export const STAGE_LABELS: Record<string, string> = {
  premarket: '盘前', live: '盘中', close: '盘后', research: '研究', replay: '回放',
}

/** 阶段业务序:盘前→盘中→盘后→研究→回放,其余按字母序兜底。
 * PG JSONB 不保插入序,导航与默认落地都依赖这个排序。 */
export function orderedStages(stages: Stages): [string, StageDef][] {
  const pri = ['premarket', 'live', 'close', 'research', 'replay']
  const keys = Object.keys(stages).sort((a, b) => {
    const ia = pri.indexOf(a), ib = pri.indexOf(b)
    if (ia !== -1 && ib !== -1) return ia - ib
    if (ia !== -1) return -1
    if (ib !== -1) return 1
    return a.localeCompare(b)
  })
  return keys.map(k => [k, stages[k]])
}

export function stageLabel(stage: string, def?: StageDef): string {
  if (stage === '_system' || stage === '(system)') return '系统设定'
  return def?.label || STAGE_LABELS[stage] || stage
}

/** 系统显示名:display_name 列(中文)优先,英文 slug 兜底。 */
export function systemDisplayName(row?: {
  display_name?: string | null; slug?: string | null; name?: string | null
} | null): string {
  return row?.display_name || row?.slug || row?.name || ''
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 场次归属阶段:新场读 run.stage;老场按命名规则推导(single 场名含阶段;live 场默认 live)。 */
export function inferRunStage(
  run: { stage?: string | null; kind?: string; slug?: string; name?: string } | null | undefined,
  system: string,
): string {
  if (run?.stage) return run.stage
  if (run?.kind === 'single') {
    const m = (run.slug || run.name || '').match(new RegExp(`^${escapeRegExp(system)}-(.+?)-\\d{8}-`))
    if (m) return m[1]
  }
  if (run?.kind === 'live') return 'live'
  return ''
}

/** 阶段只声明执行形态；实时或模拟时钟由发起器绑定。 */
export function kindLabel(_stage: string, def?: StageDef): string {
  if (!def) return ''
  if (def.kind === 'single') return '单次'
  return '循环'
}

export function runKindTag(k: string) {
  if (k === 'live') return { color: 'red', text: '实盘' }
  if (k === 'single') return { color: 'purple', text: '分析' }
  if (k === 'paper') return { color: 'blue', text: '模拟盘' }
  return { color: 'blue', text: '模拟' }
}

/** prompt 名 → 短标签(expectation-premarket → premarket;expectation-system → sys)。 */
export function shortPromptName(prompt: string, system: string): string {
  if (prompt === `${system}-system` || prompt.endsWith('-system')) return 'sys'
  return prompt.startsWith(`${system}-`) ? prompt.slice(system.length + 1) : prompt
}

/** 解析场次封面的 prompt_versions(JSON 字符串)为键值对,失败返回空对象。 */
export function parsePromptVersions(raw: unknown): Record<string, number> {
  if (!raw) return {}
  try {
    const v = typeof raw === 'string' ? JSON.parse(raw) : raw
    return typeof v === 'object' && v ? v as Record<string, number> : {}
  } catch { return {} }
}
