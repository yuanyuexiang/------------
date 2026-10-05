import { ReactNode, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Alert, Avatar, Breadcrumb, Button, Dropdown, Form, Input, Layout, Menu, Modal, Space, Tag, Typography, message } from 'antd'
import { DatabaseOutlined, DownOutlined, FileTextOutlined, MenuFoldOutlined, MenuUnfoldOutlined, FileSearchOutlined, SettingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { api } from '../api'
import { useAuth } from '../auth'
import './AdminLayout.css'

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
  const section = selected === '/kb' ? '企业知识库' : selected === '/settings' ? '配置中心' : selected === '/users' ? '用户与权限' : '投标项目'
  const page = pathname.endsWith('/workbench') ? { title: '生成与审查工作台', description: '准备投标文件，核查问题，并完成正式导出。' }
    : pathname.endsWith('/qualify') ? { title: '资格自检', description: '对照招标要求，逐项核查企业资格与证明材料。' }
    : pathname.endsWith('/trm') ? { title: '招标要求确认', description: '核对关键条款与分包要求，确认后用于后续投标准备。' }
    : pathname.startsWith('/projects/') ? { title: '项目详情', description: '掌握项目进度、关键日期和文件产出。' }
    : pathname.startsWith('/kb/') ? { title: '企业档案', description: '统一维护企业事实与证明材料，为投标文件提供依据。' }
    : selected === '/kb' ? { title: section, description: '集中管理企业信息、证照、人员、业绩与产品资料。' }
    : selected === '/settings' ? { title: section, description: '维护评分模板、合规规则与模型连接设置。' }
    : selected === '/users' ? { title: section, description: '管理团队账号、角色与价格数据访问权限。' }
    : { title: section, description: '从导入招标文件开始，有序推进每一个投标项目。' }


  return (
    <Layout className="admin-shell">
      <Sider className="admin-sidebar" collapsed={collapsed} onCollapse={setCollapsed} breakpoint="lg" collapsedWidth={72} width={224}>
        <Link to="/" className="admin-logo" aria-label="金榜首页">
          <span className="admin-logo-icon"><FileTextOutlined /></span>
          {!collapsed && <span className="admin-logo-name">金榜<small>JINBANG</small></span>}
        </Link>
        {!collapsed && <div className="admin-nav-label">工作空间</div>}
        <Menu theme="dark" mode="inline" selectedKeys={[selected]}
          items={[
            { key: '/', icon: <FileSearchOutlined />, label: <Link to="/">投标项目</Link> },
            { key: '/kb', icon: <DatabaseOutlined />, label: <Link to="/kb">企业知识库</Link> },
            { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">配置中心</Link> },
            ...(isAdmin ? [{ key: '/users', icon: <TeamOutlined />, label: <Link to="/users">用户与权限</Link> }] : []),
          ]} />
      </Sider>
      <Layout className="admin-main">
        <Header className="admin-header">
          <Button type="text" className="admin-menu-toggle" aria-label={collapsed ? '展开导航' : '收起导航'} icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />} onClick={() => setCollapsed(!collapsed)} />
          <Breadcrumb items={page.title === section ? [{ title: section }] : [{ title: <Link to={selected}>{section}</Link> }, { title: page.title }]} />
          <div className="admin-header-spacer" />
          {user && (
            <Dropdown menu={{ items: [
              { key: 'pw', label: '修改密码', onClick: () => setPwOpen(true) },
              { type: 'divider' },
              { key: 'logout', label: '退出登录', onClick: () => { logout(); nav('/login') } },
            ] }}>
              <Space className="admin-user-menu">
                <Avatar size={30} icon={<UserOutlined />} />
                <span>{user.display_name || user.username}</span>
                <Tag color={isAdmin ? 'gold' : 'blue'} style={{ marginInlineEnd: 0 }}>{user.role_cn}</Tag>
                {user.can_view_price && <Tag color="green" style={{ marginInlineEnd: 0 }}>可见价格</Tag>}
                <DownOutlined style={{ fontSize: 10 }} />
              </Space>
            </Dropdown>
          )}
        </Header>
        <Content className="admin-content">
          <div className="admin-page-heading"><div><h1>{page.title}</h1><p>{page.description}</p></div><span className="admin-workspace-label">企业工作空间</span></div>
          {isAdmin && devSecret && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="正在使用开发默认签名密钥：部署时请设置环境变量 JB_SECRET_KEY（任意长随机串），否则令牌可被伪造。" />}
          {children}
        </Content>
      </Layout>
      <PasswordModal open={pwOpen || !!user?.must_change_password} forced={!!user?.must_change_password} onClose={() => setPwOpen(false)} />
    </Layout>
  )
}
