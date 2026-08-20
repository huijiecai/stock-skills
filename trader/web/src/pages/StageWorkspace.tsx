/** 阶段工作区:单一阶段的 场次|提示词 双 Tab——prompt 与用它跑的场次在同一上下文。
 * 运行入口统一在工作台头部 ▶ 运行(预选当前阶段)。_system(系统设定)只有提示词。 */
import { Button, Empty, Space, Tabs } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { get } from '../api/client'
import { stageIcon, stageLabel, kindLabel } from '../lib/system'
import DocsBrowser from '../components/DocsBrowser'

export default function StageWorkspace() {
  const { name = '', stage = '' } = useParams()
  const nav = useNavigate()
  const loc = useLocation()
  const system = name
  const detail = useQuery({ queryKey: ['systemDetail', system], queryFn: () => get(`/systems/${encodeURIComponent(system)}`) })

  const stages: Record<string, any> = detail.data?.manifest?.stages ?? {}
  const def = stages[stage]
  const isSystem = stage === '_system'
  const base = `/systems/${encodeURIComponent(system)}/stage/${encodeURIComponent(stage)}`
  const seg = loc.pathname.split('/')[5]
  const tab = isSystem ? 'prompts' : (seg === 'prompts' ? 'prompts' : 'runs')

  if (stage === '_docs') return <DocsBrowser />
  if (!isSystem && !def)
    return <Empty style={{ marginTop: 60 }} description={
      <span>阶段「{stage}」不存在(可能已被删除)<br />
        <Button type="link" onClick={() => nav(`/systems/${encodeURIComponent(system)}/settings`)}>到设置里看看</Button>
      </span>} />

  return (
    <div>
      {/* 阶段头部 */}
      <div className="wk-header" style={{ marginBottom: 4 }}>
        <Space align="center" size={10}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>
            {stageIcon(stage)} {stageLabel(stage, def)}
          </span>
          {!isSystem && <span className={`st-badge ${def?.kind === 'single' ? 'st-neutral' : (def?.interval != null || stage.includes('replay')) ? 'st-run' : 'st-live'}`}>
            {kindLabel(stage, def)}
          </span>}
          {!isSystem && def?.kind === 'loop' && def?.interval != null &&
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>每 {def.interval ?? 5} 分钟/轮</span>}
        </Space>
      </div>

      {/* 场次 | 提示词 */}
      {!isSystem && (
        <Tabs style={{ marginTop: 4 }} activeKey={tab} onChange={(k) => nav(`${base}/${k}`)} items={[
          { key: 'runs', label: '📊 场次' },
          { key: 'prompts', label: '📝 提示词' },
        ]} />
      )}
      <Outlet />
    </div>
  )
}
