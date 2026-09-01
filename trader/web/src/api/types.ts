/** API 数据类型出口(T2.3):schema.d.ts(生成,勿手改)的组件友好短名。
 *
 * 用法:import type { RunRow } from '../api/types'
 *       get<RunRow[]>(`/runs`) —— 后端改字段 → npm run gen:api 刷新 →
 *       组件里用到该字段处 tsc 编译报错,即影响面。
 *
 * 注意:store 表行带 `& { [key: string]: unknown }`(ADR-0014 透传层),
 * 访问未建模的列得到 unknown,需收窄(如 String(x)/Number(x))后渲染。
 */
import type { components } from './schema'

type S = components['schemas']

// ── auth ──
export type UserOut = S['UserOut']
export type RegisterOut = S['RegisterOut']
export type LoginOut = S['LoginOut']
export type LogoutOut = S['LogoutOut']
export type OkOut = S['OkOut']

// ── systems / prompts ──
export type SystemRow = S['SystemRow']
export type SystemBrief = S['SystemBrief']
export type ManifestOut = S['ManifestOut']
export type StageVar = S['StageVar']
export type StageContext = S['StageContext']
export type PromptRef = S['PromptRef']
export type PromptVersionRow = S['PromptVersionRow']
export type PromptContent = S['PromptContent']
export type PromptSaved = S['PromptSaved']
export type RestoreOut = S['RestoreOut']
export type DeleteOut = S['DeleteOut']
export type RunStarted = S['RunStarted']

// ── portfolios / curve ──
export type PortfolioRow = S['PortfolioRow']
export type CurvePoint = S['CurvePoint']
export type DailyPoint = S['DailyPoint']
export type CurveOut = S['CurveOut']

// ── runs ──
export type RunRow = S['RunRow']
export type ReplayStarted = S['ReplayStarted']
export type RoundBrief = S['RoundBrief']
export type RoundsOverview = S['RoundsOverview']
export type Step = S['Step']
export type RoundDetail = S['RoundDetail']
export type EventRow = S['EventRow']
export type LiveSteps = S['LiveSteps']
export type StopOut = S['StopOut']
export type SealOut = S['SealOut']
export type PositionRow = S['PositionRow']
export type FillRow = S['FillRow']
export type RunTrading = S['RunTrading']
export type AccountOut = S['AccountOut']

// ── documents / watchlists ──
export type RunDocumentRow = S['RunDocumentRow']
export type RunDocumentContent = S['RunDocumentContent']
export type DocumentBrief = S['DocumentBrief']
export type DocContent = S['DocContent']
export type WatchlistSummary = S['WatchlistSummary']
export type WatchlistMember = S['WatchlistMember']

// ── tools ──
export type ToolParam = S['ToolParam']
export type ToolInfo = S['ToolInfo']
export type TestUser = S['TestUser']
export type ToolsCatalog = S['ToolsCatalog']
export type ToolCallOut = S['ToolCallOut']

// ── chat / coach ──
export type ChatAnchor = S['ChatAnchor']
export type ChatMessage = S['ChatMessage']
export type ChatReplyOut = S['ChatReplyOut']
export type ChatHistory = S['ChatHistory']
export type CoachConvRow = S['CoachConvRow']
export type CoachNewOut = S['CoachNewOut']
export type CoachHistory = S['CoachHistory']
export type CoachArchiveOut = S['CoachArchiveOut']
export type CoachReplyOut = S['CoachReplyOut']

// ── 阶段定义(前端本地契约,非生成)──────────────────────
/** manifest.stages 条目的消费面。后端 manifest 是自由 JSON(设置页可视化编辑,
 *  不进后端 schema,分层见 ADR-0014);已声明字段是渲染/校验依赖的形状,
 *  索引签名放行编辑器管理的其余键(window/skip_lunch/request_limit…)。 */
export interface StageOutputSpec {
  label?: string
  kind?: 'artifact' | 'document' | 'resource' | 'action' | 'metric'
  doc_type?: string
  [key: string]: unknown
}
export interface StageInputSpec {
  from?: string | { stage?: string; output?: string }
  kind?: string
  selector?: 'latest' | 'previous' | 'recent' | 'all'
  limit?: number
  max_chars?: number
  label?: string          // 编辑器:显示名称
  required?: boolean      // 编辑器:必需输入开关
  [key: string]: unknown
}
export interface StageDef {
  kind?: 'single' | 'loop'
  label?: string
  prompt?: string
  vars?: string[]
  interval?: number
  request_limit?: number   // 编辑器:单轮最大模型请求数
  window?: string          // 编辑器:运行窗口 "09:35-15:05"
  skip_lunch?: boolean     // 编辑器:循环跳过午休
  outputs?: Record<string, StageOutputSpec>
  inputs?: Record<string, StageInputSpec>
  [key: string]: unknown
}
export type Stages = Record<string, StageDef>
