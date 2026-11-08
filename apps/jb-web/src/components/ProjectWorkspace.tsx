import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Drawer, Select, Space, Spin, Tabs, Typography } from 'antd'
import { api, ProjectDetail } from '../api'
import ProjectDetailPage from '../pages/ProjectDetailPage'
import { useAuth } from '../auth'
import { errorMessage } from '../uiLabels'
import { packageIndex, ProjectSelection, ProjectView, projectUrl } from '../projectNavigation'
import './ProjectWorkspace.css'

interface Workspace {
  project: ProjectDetail
  profile?: string
  pkgIndex: number
  setProfile: (value: string) => void
  setPkgIndex: (value: number) => void
  href: (route?: string, index?: number, view?: ProjectView) => string
  selectionLocked: boolean
  setSelectionLocked: (value: boolean) => void
}
const Context = createContext<Workspace | null>(null)
export function useProjectWorkspace() {
  const value = useContext(Context)
  if (!value) throw new Error('ProjectWorkspace is required')
  return value
}

export default function ProjectWorkspace() {
  const { id = '' } = useParams()
  return <WorkspaceContent key={id} id={id} />
}

function WorkspaceContent({ id }: { id: string }) {
  const username = useAuth(s => s.user?.username)
  const storageKey = `jinbang.project.${username}.${id}`
  const [saved] = useState<ProjectSelection>(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey) || '{}')
      return value && typeof value === 'object' ? value : {}
    } catch { return {} }
  })
  const [params, setParams] = useSearchParams()
  const { pathname } = useLocation()
  const nav = useNavigate()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [selectionLocked, setSelectionLocked] = useState(false)
  const { data: project, error, isLoading } = useQuery({
    queryKey: ['project-detail', id], queryFn: () => api.projectDetail(id), refetchInterval: 5000,
  })
  const { data: profiles = [], error: profileError, isSuccess: profilesLoaded } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const pkgIndex = packageIndex(params.get('pkg') ?? saved.pkgIndex, project?.package_list.length ?? 0)
  const selectedKey = project?.package_list[pkgIndex]?.result_key
  const requestedProfile = params.get('profile') ?? saved.profile ?? project?.results.generate?.[selectedKey ?? '']?.profile ?? project?.results.qualify?.profile
  const profile = profiles.some(p => p.name === requestedProfile) ? requestedProfile
    : requestedProfile ? undefined : profiles.length === 1 ? profiles[0].name : undefined
  const href = (route = '', index = pkgIndex, view?: ProjectView) => projectUrl(id, route, { profile, pkgIndex: index }, view)
  const select = (selection: ProjectSelection) => {
    setParams(current => {
      const next = new URLSearchParams(current)
      if (selection.profile !== undefined) next.set('profile', selection.profile)
      if (selection.pkgIndex !== undefined) next.set('pkg', String(selection.pkgIndex))
      next.delete('view') // 新企业或新包从资料准备开始，避免沿用其他包的审阅位置。
      next.delete('requirement')
      next.delete('task')
      return next
    }, { replace: true })
  }
  useEffect(() => {
    if (!project || !profilesLoaded) return
    try { sessionStorage.setItem(storageKey, JSON.stringify({ profile, pkgIndex })) } catch { /* URL still preserves the selection. */ }
  }, [storageKey, project, profile, pkgIndex, profilesLoaded])
  // 把恢复后的选择写入当前 URL，使刷新、复制链接和浏览器前进后退保持一致。
  useEffect(() => {
    if (!project || !profilesLoaded || (!profile && !project.package_list.length)) return
    if ((profile && params.get('profile') !== profile) || params.get('pkg') !== String(pkgIndex)) {
      setParams(current => {
        const next = new URLSearchParams(current)
        if (profile) next.set('profile', profile)
        next.set('pkg', String(pkgIndex))
        return next
      }, { replace: true })
    }
  }, [project, profile, pkgIndex, params, setParams, profilesLoaded])
  if (error) return <Alert type="error" showIcon message="无法读取项目" description={errorMessage(error)} />
  if (isLoading || !project) return <Spin />
  const ready = ['parsed', 'confirmed'].includes(project.status)
  const active = pathname.endsWith('/trm') ? 'trm' : pathname.endsWith('/qualify') ? 'workbench'
    : pathname.endsWith('/workbench') ? params.get('view') === 'review' ? 'review' : 'workbench' : 'overview'
  const value = { project, profile, pkgIndex, setProfile: (v: string) => select({ profile: v }),
    setPkgIndex: (v: number) => select({ pkgIndex: v }), href, selectionLocked, setSelectionLocked }
  return <Context.Provider value={value}>
    <Card size="small" className="project-workspace">
      <div className="project-workspace-heading">
        <div><Typography.Text type="secondary">{project.batch_no || '读取中'} · 截止 {project.deadline || '待核对'}</Typography.Text>
          <Typography.Title level={1}>{project.batch_name || project.filename}</Typography.Title></div>
        <Space wrap><Button onClick={() => nav('/')}>全部投标项目</Button>
          <Button onClick={() => setDetailsOpen(true)}>项目信息</Button></Space>
      </div>
      <div className="project-workspace-selection">
        <div><label htmlFor="project-company">本次投标企业</label><Select id="project-company" placeholder="选择企业档案" value={profile}
          disabled={selectionLocked} onChange={value.setProfile} options={profiles.map(p => ({ value: p.name, label: p.name }))} /></div>
        <div><label htmlFor="project-package">当前采购包</label><Select id="project-package" value={project.package_list.length ? pkgIndex : undefined}
          disabled={selectionLocked || !ready} onChange={value.setPkgIndex} placeholder="采购包尚未读取"
          options={project.package_list.map((p, i) => ({ value: i, label: `${p.sub_no} ${p.pkg_no} · ${p.project_name || p.sub_name || '采购包'}` }))} /></div>
      </div>
      {profileError && <Alert type="error" message="无法读取企业档案" description={errorMessage(profileError)} />}
      {!profileError && requestedProfile && !profile && profiles.length > 0 && <Alert type="warning" message="原选择的企业已不可用，请重新选择" />}
    </Card>
    <section className="project-workspace-panel">
      <Tabs className="project-workspace-nav" activeKey={active} onChange={key => nav(href(key === 'overview' ? '' : key === 'review' ? 'workbench' : key,
        pkgIndex, key === 'review' ? 'review' : key === 'workbench' ? 'prepare' : undefined))}
        items={[{ key: 'trm', label: '1. 核对采购信息', disabled: !ready },
          { key: 'workbench', label: '2. 准备投标文件', disabled: !ready },
          { key: 'review', label: '3. 检查并导出', disabled: !ready }]} />
      <div className="project-workspace-content"><Outlet /></div>
    </section>
    <Drawer title="项目信息" width="min(1100px, 96vw)" open={detailsOpen} onClose={() => setDetailsOpen(false)} destroyOnClose><ProjectDetailPage /></Drawer>
  </Context.Provider>
}

export function ProjectEntry() {
  const { project, href, pkgIndex } = useProjectWorkspace()
  if (!['parsed', 'confirmed'].includes(project.status) || ['won', 'lost', 'abandoned'].includes(project.outcome)) return <ProjectDetailPage />
  return <Navigate replace to={href(project.confirmed ? 'workbench' : 'trm', pkgIndex, project.confirmed ? 'prepare' : undefined)} />
}

export function QualificationRedirect() {
  const { href, pkgIndex } = useProjectWorkspace()
  return <Navigate replace to={href('workbench', pkgIndex, 'prepare')} />
}
