import { ReactNode, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Layout, Menu, Typography } from 'antd'
import { DatabaseOutlined, FileSearchOutlined, SettingOutlined, TeamOutlined } from '@ant-design/icons'

const { Sider, Header, Content } = Layout

/** 管理后台外壳：侧边栏菜单（投标项目 / 企业知识库 / 配置中心 / 用户权限），内容区路由渲染。 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const selected = pathname.startsWith('/kb') ? '/kb'
    : pathname.startsWith('/settings') ? '/settings'
    : pathname.startsWith('/users') ? '/users' : '/'

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
            { key: '/settings', icon: <SettingOutlined />, label: '配置中心', disabled: true },
            { key: '/users', icon: <TeamOutlined />, label: '用户与权限', disabled: true },
          ]} />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', gap: 16, borderBottom: '1px solid #f0f0f0' }}>
          <Typography.Text strong>国网智能投标管理系统</Typography.Text>
          <Typography.Text type="secondary">供应商自用 · 事实只来自档案，不由模型生成</Typography.Text>
        </Header>
        <Content style={{ padding: 24, maxWidth: 1500, width: '100%', margin: '0 auto' }}>{children}</Content>
      </Layout>
    </Layout>
  )
}
