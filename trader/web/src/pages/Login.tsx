import { Card, Form, Input, Button, Tabs, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { post, setToken } from '../api/client'

export default function Login() {
  const nav = useNavigate()

  async function onLogin(v: { email: string; password: string }) {
    try {
      const r = await post<{ token: string }>('/auth/login', v)
      setToken(r.token)
      nav('/')
    } catch (e: any) { message.error(e.message) }
  }

  async function onRegister(v: { email: string; password: string; display_name?: string }) {
    try {
      await post('/auth/register', v)
      message.success('注册成功,自动登录中…')
      await onLogin({ email: v.email, password: v.password })
    } catch (e: any) { message.error(e.message) }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f2f5' }}>
      <Card title="trader 平台" style={{ width: 380 }}>
        <Tabs items={[
          {
            key: 'login', label: '登录',
            children: (
              <Form onFinish={onLogin} layout="vertical">
                <Form.Item name="email" label="邮箱" rules={[{ required: true }]}>
                  <Input placeholder="you@example.com" />
                </Form.Item>
                <Form.Item name="password" label="密码" rules={[{ required: true }]}>
                  <Input.Password />
                </Form.Item>
                <Button type="primary" htmlType="submit" block>登录</Button>
              </Form>
            ),
          },
          {
            key: 'register', label: '注册',
            children: (
              <Form onFinish={onRegister} layout="vertical">
                <Form.Item name="email" label="邮箱" rules={[{ required: true, type: 'email' }]}>
                  <Input placeholder="you@example.com" />
                </Form.Item>
                <Form.Item name="display_name" label="昵称(可选)">
                  <Input />
                </Form.Item>
                <Form.Item name="password" label="密码" rules={[{ required: true, min: 6 }]}>
                  <Input.Password />
                </Form.Item>
                <Button htmlType="submit" block>注册并登录</Button>
              </Form>
            ),
          },
        ]} />
      </Card>
    </div>
  )
}
