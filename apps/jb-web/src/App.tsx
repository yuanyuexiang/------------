import { Link, Route, Routes } from 'react-router-dom'
import { Layout, Typography } from 'antd'
import ProjectsPage from './pages/ProjectsPage'
import TrmConfirmPage from './pages/TrmConfirmPage'
import QualifyPage from './pages/QualifyPage'
import ProfilePage from './pages/ProfilePage'
import WorkbenchPage from './pages/WorkbenchPage'

const { Header, Content } = Layout

export default function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <Link to="/" style={{ color: '#fff', fontSize: 18, fontWeight: 600 }}>Jinbang 金榜</Link>
        <Typography.Text style={{ color: '#bbb' }}>国网智能投标工作台 · 原型</Typography.Text>
      </Header>
      <Content style={{ padding: 24, maxWidth: 1400, margin: '0 auto', width: '100%' }}>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:id/trm" element={<TrmConfirmPage />} />
          <Route path="/projects/:id/qualify" element={<QualifyPage />} />
          <Route path="/profiles/:name" element={<ProfilePage />} />
          <Route path="/projects/:id/workbench" element={<WorkbenchPage />} />
        </Routes>
      </Content>
    </Layout>
  )
}
