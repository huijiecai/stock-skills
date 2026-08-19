import { Layout as AntLayout, Menu, Button, Space, Tag } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { get, clearToken } from '../api/client'

const { Header, Content } = AntLayout

export default function Layout() {
  const nav = useNavigate()
  const loc = useLocation()
  const me = useQuery({ queryKey: ['me'], queryFn: () => get('/auth/me') })

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ color: '#fff', fontWeight: 700, fontSize: 16 }}>trader 平台</div>
        <Menu
          theme="dark" mode="horizontal" selectedKeys={[loc.pathname]}
          onClick={(e) => nav(e.key)}
          items={[
            { key: '/', label: '工作台' },
            { key: '/runs', label: '场次' },
            { key: '/systems', label: '我的系统' },
          ]}
          style={{ flex: 1, minWidth: 0 }}
        />
        <Space>
          {me.data && <Tag color={me.data.is_admin ? 'gold' : 'blue'}>{me.data.display_name || me.data.email}</Tag>}
          <Button size="small" onClick={() => { clearToken(); nav('/login') }}>退出</Button>
        </Space>
      </Header>
      <Content style={{ padding: 20, maxWidth: 1200, margin: '0 auto', width: '100%' }}>
        <Outlet />
      </Content>
    </AntLayout>
  )
}
