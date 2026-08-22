import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import AdminLayout from './layout/AdminLayout'
import ProjectsPage from './pages/ProjectsPage'
import ProjectDetailPage from './pages/ProjectDetailPage'
import TrmConfirmPage from './pages/TrmConfirmPage'
import QualifyPage from './pages/QualifyPage'
import WorkbenchPage from './pages/WorkbenchPage'
import KbListPage from './pages/kb/KbListPage'
import KbCompanyPage from './pages/kb/KbCompanyPage'

/** 旧链接 /profiles/:name → 知识库企业页。 */
function ProfileRedirect() {
  const { name = '' } = useParams()
  return <Navigate to={`/kb/${encodeURIComponent(name)}`} replace />
}

export default function App() {
  return (
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
      </Routes>
    </AdminLayout>
  )
}
