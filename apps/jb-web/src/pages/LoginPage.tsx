import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '../auth'

export default function LoginPage() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const login = useAuth((s) => s.login)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const submit = async (v: { username: string; password: string }) => {
    setLoading(true); setError('')
    try {
      await login(v.username, v.password)
      nav(params.get('next') || '/', { replace: true })
    } catch (e) { setError(String(e instanceof Error ? e.message : e)) } finally { setLoading(false) }
  }
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f2f5' }}>
      <Card style={{ width: 380 }}>
        <Typography.Title level={3} style={{ textAlign: 'center', marginBottom: 4 }}>Jinbang 金榜</Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: 'center' }}>国网智能投标管理系统 · 供应商自用</Typography.Paragraph>
        {error && <Alert type="error" message={error} style={{ marginBottom: 12 }} />}
        <Form onFinish={submit} layout="vertical" size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}><Input prefix={<UserOutlined />} placeholder="用户名" autoFocus /></Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}><Input.Password prefix={<LockOutlined />} placeholder="密码" /></Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>登录</Button>
        </Form>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
          首次部署自动创建管理员 admin / admin，登录后请立即修改密码。
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
