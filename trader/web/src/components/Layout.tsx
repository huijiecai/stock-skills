/** 全局骨架:左侧系统栏(自绘,统一对齐)+ 瘦顶栏。
 * 显示名优先中文(display_name 列),路由仍用英文 slug。 */
import { Layout as AntLayout, Button, Space, Tag, Dropdown, Modal, Input, message, Typography, Spin } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { get, post, put, del, clearToken } from '../api/client'
import { systemDisplayName } from '../lib/system'

const { Sider, Header, Content } = AntLayout

const STARTER_MANIFEST = {
  stages: { run: { kind: 'single', prompt: 'PLACEHOLDER-run', request_limit: 100 } },
  policy: { web_search: false, resource_write: false,
            simulation_trading: true, live_trading: false },
  doc_classes: { library: ['note', 'research'], ephemeral: ['report'] },
}

/** 自绘侧栏行:图标列定宽对齐 + 名称 ellipsis + 悬停才出 ⋯。 */
function NavItem({ icon, label, active, onClick, dim, extra }: {
  icon: React.ReactNode; label: string; active?: boolean; onClick?: () => void; dim?: boolean; extra?: React.ReactNode
}) {
  return (
    <div className={`sn-item${active ? ' sn-active' : ''}${dim ? ' sn-dim' : ''}`} onClick={onClick}>
      <span className="sn-icon">{icon}</span>
      <span className="sn-label" title={label}>{label}</span>
      {extra != null && <span className="sn-extra">{extra}</span>}
    </div>
  )
}

export default function Layout() {
  const nav = useNavigate()
  const loc = useLocation()
  const qc = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: () => get('/auth/me') })
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get('/systems') })

  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newLabel, setNewLabel] = useState('')

  const sysName = loc.pathname.startsWith('/systems/') ? decodeURIComponent(loc.pathname.split('/')[2]) : ''
  const selected = loc.pathname === '/' ? '/' : sysName

  const createModal = (
      <Modal title="新建交易系统" open={creating} onCancel={() => setCreating(false)}
             onOk={handleCreate} okText="创建" width={420}
             okButtonProps={{ disabled: !newName.trim() }}>
        <Space orientation="vertical" style={{ width: '100%' }} size={10}>
          <Input placeholder="系统名(中文,如:预期管理)" value={newLabel}
                 onChange={(e) => setNewLabel(e.target.value)}
                 onPressEnter={handleCreate} />
          <Input placeholder="标识(英文,用于路由与 prompt,如 expectation)" value={newName}
                 onChange={(e) => setNewName(e.target.value)}
                 onPressEnter={handleCreate} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            创建后进入设置添加阶段，然后专注编写交易逻辑 Prompt；行情和组合数据按需调用工具。
          </Typography.Text>
        </Space>
      </Modal>
  )

  async function handleCreate() {
    const name = newName.trim()
    if (!name) return
    try {
      await post('/systems', {
        slug: name,
        display_name: newLabel.trim() || name,
        manifest: {
          ...STARTER_MANIFEST,
          system_prompt: `${name}-system`,
          stages: { run: { ...STARTER_MANIFEST.stages.run, prompt: `${name}-run` } },
        },
      })
      message.success(`系统 ${newLabel.trim() || name} 已建`)
      setCreating(false); setNewName(''); setNewLabel('')
      qc.invalidateQueries({ queryKey: ['systems'] })
      nav(`/systems/${encodeURIComponent(name)}/settings`)
    } catch (e: any) { message.error(e.message) }
  }

  async function archive(name: string) {
    try {
      await del(`/systems/${encodeURIComponent(name)}`)
      message.success('已归档')
      qc.invalidateQueries({ queryKey: ['systems'] })
      qc.invalidateQueries({ queryKey: ['systemDetail', name] })
    } catch (e: any) { message.error(e.message) }
  }

  async function restore(name: string) {
    try {
      await put(`/systems/${encodeURIComponent(name)}/restore`)
      message.success('已恢复')
      qc.invalidateQueries({ queryKey: ['systems'] })
      qc.invalidateQueries({ queryKey: ['systemDetail', name] })
    } catch (e: any) { message.error(e.message) }
  }

  const list: any[] = systems.data ?? []
  const active = list.filter(s => s.status !== 'archived')
  const archived = list.filter(s => s.status === 'archived')

  const moreMenu = (s: any) => (
    <Dropdown trigger={['click']} menu={{ items: [
      s.status === 'archived'
        ? { key: 'restore', label: '♻️ 恢复' }
        : { key: 'archive', label: '🗄️ 归档' },
    ], onClick: ({ key }) => key === 'restore' ? restore(s.slug) : archive(s.slug) }}>
      <span className="sn-extra-btn" onClick={e => e.stopPropagation()}>⋯</span>
    </Dropdown>
  )

  // 系统页 = 全屏工作区(资产/工作台自带顶栏),应用侧栏退场(原型形态)
  const onSystemPage = loc.pathname.startsWith('/systems/')
  const onEvidencePage = loc.pathname.startsWith('/runs/') || loc.pathname.startsWith('/compare')
  if (onSystemPage || onEvidencePage)
    return (
      <AntLayout style={{ minHeight: '100vh' }}>
        <Content style={{ width: '100%' }}>
          <Outlet />
        </Content>
        {creating && null}
        {createModal}
      </AntLayout>
    )

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sider width={216} theme="dark" breakpoint="lg" collapsedWidth={0}
             style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0 }}>
        <div className="sn-brand">📈 trader</div>
        <nav className="sn-nav">
          <NavItem icon="🏠" label="工作台(今日)" active={selected === '/'}
                   onClick={() => nav('/')} />
          <div className="sn-group">交易系统 · {active.length}</div>
          {active.map(s => (
            <NavItem key={s.slug} icon={s.status === 'archived' ? '📦' : '◾'}
                     label={systemDisplayName(s)} active={selected === s.slug}
                     onClick={() => nav(`/systems/${encodeURIComponent(s.slug)}`)}
                     extra={moreMenu(s)} />
          ))}
          {archived.length > 0 && <div className="sn-group">已归档</div>}
          {archived.map(s => (
            <NavItem key={s.slug} icon="📦" dim label={systemDisplayName(s)}
                     active={selected === s.slug}
                     onClick={() => nav(`/systems/${encodeURIComponent(s.slug)}`)}
                     extra={moreMenu(s)} />
          ))}
          <NavItem icon="＋" label="新建系统" onClick={() => setCreating(true)} />
        </nav>
      </Sider>
      <AntLayout style={{ marginLeft: 216 }} className="sider-collapsed-margin">
        <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                         background: '#fff', padding: '0 20px', height: 48, lineHeight: '48px',
                         borderBottom: '1px solid #f0f0f0' }}>
          <Space>
            {systems.isLoading && <Spin size="small" />}
            {me.data && <Tag color={me.data.is_admin ? 'gold' : 'blue'}>{me.data.display_name || me.data.email}</Tag>}
            <Button size="small" onClick={() => { clearToken(); nav('/login') }}>退出</Button>
          </Space>
        </Header>
        <Content style={{ padding: 20, maxWidth: 1280, margin: '0 auto', width: '100%' }}>
          <Outlet />
        </Content>
      </AntLayout>

      {/* 新建:中文名(显示)+ 英文标识(路由/prompt 前缀) */}
      {createModal}
          </AntLayout>
  )
}
