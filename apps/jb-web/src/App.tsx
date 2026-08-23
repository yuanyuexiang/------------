import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { Spin } from 'antd'
import AdminLayout from './layout/AdminLayout'
import { useAuth } from './auth'
import LoginPage from './pages/LoginPage'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import TrmConfirmPage from './pages/TrmConfirmPage'
import QualifyPage from './pages/QualifyPage'
import WorkbenchPage from './pages/WorkbenchPage'
import KbListPage from './pages/kb/KbListPage'
import KbCompanyPage from './pages/kb/KbCompanyPage'
import SettingsPage from './pages/settings/SettingsPage'
import UsersPage from './pages/UsersPage'

/** 旧链接 /profiles/:name → 知识库企业页。 */
function ProfileRedirect() {
  const { name = '' } = useParams()
  return <Navigate to={`/kb/${encodeURIComponent(name)}`} replace />
}

/** 未登录 → 登录页（带回跳）；管理员专属路由对成员重定向首页。 */
function Guard({ admin, children }: { admin?: boolean; children: JSX.Element }) {
  const { user, loaded } = useAuth()
  const loc = useLocation()
  if (!loaded) return <Spin style={{ display: 'block', margin: '20vh auto' }} />
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  if (admin && user.role !== 'admin') return <Navigate to="/" replace />
  return children
}

export default function App() {
  const load = useAuth((s) => s.load)
  useEffect(() => { load() }, [load])
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={
        <Guard>
          <AdminLayout>
            <Routes>
              <Route path="/" element={<ProjectsPage />} />
              <Route path="/projects/:id" element={<ProjectDetailPage />} />
              <Route path="/projects/:id/trm" element={<TrmConfirmPage />} />
              <Route path="/projects/:id/qualify" element={<QualifyPage />} />
              <Route path="/projects/:id/workbench" element={<WorkbenchPage />} />
              <Route path="/kb" element={<KbListPage />} />
              <Route path="/kb/:name" element={<KbCompanyPage />} />
              <Route path="/profiles/:name" element={<ProfileRedirect />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/users" element={<Guard admin><UsersPage /></Guard>} />
            </Routes>
          </AdminLayout>
        </Guard>
      } />
    </Routes>
  )
}
