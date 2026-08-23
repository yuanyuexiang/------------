import { ReactNode, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Alert, Dropdown, Form, Input, Layout, Menu, Modal, Space, Tag, Typography, message } from 'antd'
import { DatabaseOutlined, DownOutlined, FileSearchOutlined, SettingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { api } from '../api'
import { useAuth } from '../auth'

const { Sider, Header, Content } = Layout

/** 改密弹窗：初始密码/管理员重置后 must_change_password 为真时自动弹出。 */
function PasswordModal({ open, onClose, forced }: { open: boolean; onClose: () => void; forced: boolean }) {
  const [form] = Form.useForm()
  const refresh = useAuth((s) => s.refresh)
  const submit = async () => {
    const v = await form.validateFields()
    try { await api.changePassword(v.old_password, v.new_password); message.success('密码已修改'); await refresh(); onClose() } catch (e) { message.error(String(e)) }
  }
  return (
    <Modal open={open} title="修改密码" onOk={submit} onCancel={forced ? undefined : onClose} closable={!forced} maskClosable={false}
      cancelButtonProps={{ style: forced ? { display: 'none' } : undefined }} destroyOnClose>
      {forced && <Alert type="warning" showIcon message="当前是初始密码，请先修改后再使用系统" style={{ marginBottom: 12 }} />}
      <Form form={form} layout="vertical">
        <Form.Item name="old_password" label="原密码" rules={[{ required: true }]}><Input.Password /></Form.Item>
        <Form.Item name="new_password" label="新密码（至少 6 位）" rules={[{ required: true, min: 6, message: '至少 6 位' }]}><Input.Password /></Form.Item>
        <Form.Item name="confirm" label="确认新密码" dependencies={['new_password']} rules={[{ required: true }, ({ getFieldValue }) => ({ validator: (_, v) => v === getFieldValue('new_password') ? Promise.resolve() : Promise.reject(new Error('两次输入不一致')) })]}><Input.Password /></Form.Item>
      </Form>
    </Modal>
  )
}

/** 管理后台外壳：侧边栏菜单（投标项目 / 企业知识库 / 配置中心 / 用户与权限·仅管理员），顶栏用户菜单。 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const nav = useNavigate()
  const { user, devSecret, logout } = useAuth()
  const [collapsed, setCollapsed] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)
  const selected = pathname.startsWith('/kb') ? '/kb'
    : pathname.startsWith('/settings') ? '/settings'
    : pathname.startsWith('/users') ? '/users' : '/'
  const isAdmin = user?.role === 'admin'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} width={208}>
        <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: collapsed ? 16 : 18, fontWeight: 600 }}>
          {collapsed ? '金榜' : 'Jinbang 金榜'}
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]}
          items={[
            { key: '/', icon: <FileSearchOutlined />, label: <Link to="/">投标项目</Link> },
            { key: '/kb', icon: <DatabaseOutlined />, label: <Link to="/kb">企业知识库</Link> },
            { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">配置中心</Link> },
            ...(isAdmin ? [{ key: '/users', icon: <TeamOutlined />, label: <Link to="/users">用户与权限</Link> }] : []),
          ]} />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', gap: 16, borderBottom: '1px solid #f0f0f0' }}>
          <Typography.Text strong>国网智能投标管理系统</Typography.Text>
          <Typography.Text type="secondary">供应商自用 · 事实只来自档案，不由模型生成</Typography.Text>
          <div style={{ flex: 1 }} />
          {user && (
            <Dropdown menu={{ items: [
              { key: 'pw', label: '修改密码', onClick: () => setPwOpen(true) },
              { type: 'divider' },
              { key: 'logout', label: '退出登录', onClick: () => { logout(); nav('/login') } },
            ] }}>
              <Space style={{ cursor: 'pointer' }}>
                <UserOutlined />
                <span>{user.display_name || user.username}</span>
                <Tag color={isAdmin ? 'gold' : 'blue'} style={{ marginInlineEnd: 0 }}>{user.role_cn}</Tag>
                {user.can_view_price && <Tag color="green" style={{ marginInlineEnd: 0 }}>可见价格</Tag>}
                <DownOutlined style={{ fontSize: 10 }} />
              </Space>
            </Dropdown>
          )}
        </Header>
        <Content style={{ padding: 24, maxWidth: 1500, width: '100%', margin: '0 auto' }}>
          {isAdmin && devSecret && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="正在使用开发默认签名密钥：部署时请设置环境变量 JB_SECRET_KEY（任意长随机串），否则令牌可被伪造。" />}
          {children}
        </Content>
      </Layout>
      <PasswordModal open={pwOpen || !!user?.must_change_password} forced={!!user?.must_change_password} onClose={() => setPwOpen(false)} />
    </Layout>
  )
}
