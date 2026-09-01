/** 图标体系(T3.2):@ant-design/icons 三类映射表,全 app 唯一出口。
 * 新增图标来这里登记,禁止散落用 emoji。图标默认 1em 随字号,颜色继承 currentColor。
 * 三类:NAV 导航/品牌 · STATUS 状态 · OP 操作/功能。 */
import { createElement } from 'react'
import {
  HomeOutlined, LineChartOutlined, RobotOutlined, InboxOutlined, HddOutlined,
  RollbackOutlined, PlusOutlined,
  CheckCircleOutlined, CloseCircleOutlined, WarningOutlined, StopOutlined,
  FlagOutlined, ExclamationCircleOutlined,
  SendOutlined, FileTextOutlined, FileDoneOutlined, BookOutlined, ReadOutlined,
  SettingOutlined, ToolOutlined, BarChartOutlined, CommentOutlined, StarOutlined,
  ExperimentOutlined, SearchOutlined, SyncOutlined, GlobalOutlined,
  CalendarOutlined, ProfileOutlined, EditOutlined, EyeOutlined, ClockCircleOutlined,
  HistoryOutlined, ThunderboltOutlined, WalletOutlined, CompassOutlined,
  FolderOutlined, SafetyOutlined, BulbOutlined, AimOutlined, SwapOutlined,
  ArrowLeftOutlined, FormOutlined, DatabaseOutlined, RocketOutlined, RiseOutlined,
  CloseOutlined, PlayCircleOutlined,
} from '@ant-design/icons'

/** 导航/品牌 */
export const NAV = {
  home: HomeOutlined,          // 工作台(今日)
  asset: LineChartOutlined,    // 资产/履历
  system: RobotOutlined,       // 交易系统(AI 代理)
  archived: InboxOutlined,     // 已归档系统
  archive: HddOutlined,        // 归档操作
  restore: RollbackOutlined,   // 恢复操作
  create: PlusOutlined,        // 新建系统
  brand: RiseOutlined,         // 侧栏品牌(交易终端)
}

/** 状态 */
export const STATUS = {
  done: CheckCircleOutlined,       // 已完成/已封场
  fail: CloseCircleOutlined,       // 失败/错误
  warn: WarningOutlined,           // 警示(实盘交易/占位符)
  stall: ExclamationCircleOutlined,// 疑似僵死
  stop: StopOutlined,              // 停止
  finish: FlagOutlined,            // 本轮完成
  live: null,                      // ● 用文本(配 stg-pulse 动画)
}

/** 操作/功能 */
export const OP = {
  input: InboxOutlined,        // 输入区
  output: SendOutlined,        // 产出区
  task: AimOutlined,           // 本次任务
  doc: FileTextOutlined,       // 文档/指令
  lib: BookOutlined,           // 文档库/输入文档
  read: ReadOutlined,          // 预览/阅读
  settings: SettingOutlined,   // 系统设定/过程
  tool: ToolOutlined,          // 工作台/工具
  market: BarChartOutlined,    // 行情数据
  chat: CommentOutlined,       // 讨论/教练
  star: StarOutlined,          // 自选组/收藏
  lab: ExperimentOutlined,     // 实验/模拟
  search: SearchOutlined,      // 研究
  sync: SyncOutlined,          // 回放/刷新
  globe: GlobalOutlined,       // 联网搜索
  calendar: CalendarOutlined,  // 按日期
  profile: ProfileOutlined,    // 轮指令/档案
  edit: EditOutlined,          // 编辑
  eye: EyeOutlined,            // 预览 tab
  clock: ClockCircleOutlined,  // 何时:现在
  history: HistoryOutlined,    // 何时:重演/执行史
  bolt: ThunderboltOutlined,   // 交易执行
  wallet: WalletOutlined,      // 账户
  compass: CompassOutlined,    // 扫描
  folder: FolderOutlined,      // 按类型/目录
  shield: SafetyOutlined,      // 值守日
  idea: BulbOutlined,          // 思考流/AI 建议
  swap: SwapOutlined,          // 版本对比
  back: ArrowLeftOutlined,     // 返回/回退
  form: FormOutlined,          // 提示词
  db: DatabaseOutlined,        // 数据区
  rocket: RocketOutlined,      // 启动/加速
  review: FileDoneOutlined,    // 盘后复盘
  premarket: RiseOutlined,     // 盘前(早盘)
  close: CloseOutlined,        // 关闭浮层
  play: PlayCircleOutlined,    // 试运行/播放
}

/** 阶段图标(emoji 时代退役,迁移自 lib/system.ts)。
 * 返回 ReactNode;消费处保持 `{stageIcon(s)}` 写法不变。 */
export function stageIcon(s: string): React.ReactNode {
  if (s === '_system' || s === '(system)') return createElement(OP.settings)
  if (s.includes('live')) return createElement(OP.market)
  if (s.includes('premarket')) return createElement(OP.premarket)
  if (s.includes('close')) return createElement(OP.review)
  if (s.includes('research')) return createElement(OP.search)
  if (s.includes('replay')) return createElement(OP.sync)
  return createElement(OP.doc)
}
