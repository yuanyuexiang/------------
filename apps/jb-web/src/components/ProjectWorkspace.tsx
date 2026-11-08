import { createContext, useContext, useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Select, Space, Spin, Tabs, Tag, Typography } from 'antd'
import { api, ProjectDetail } from '../api'
import { useAuth } from '../auth'
import { errorMessage } from '../uiLabels'
import { nextProjectAction, packageIndex, ProjectSelection, ProjectView, projectUrl } from '../projectNavigation'
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
  const { data: qualification } = useQuery({ queryKey: ['qualification', id, profile],
    queryFn: () => api.qualification(id, profile!),
    enabled: !!profile && !!project && ['parsed', 'confirmed'].includes(project.status), refetchInterval: 15000 })
  const href = (route = '', index = pkgIndex, view?: ProjectView) => projectUrl(id, route, { profile, pkgIndex: index }, view)
  const select = (selection: ProjectSelection) => {
    setParams(current => {
      const next = new URLSearchParams(current)
      if (selection.profile !== undefined) next.set('profile', selection.profile)
      if (selection.pkgIndex !== undefined) next.set('pkg', String(selection.pkgIndex))
      next.delete('view') // 新企业或新包从资料准备开始，避免沿用其他包的审阅位置。
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
  const active = pathname.endsWith('/trm') ? 'trm' : pathname.endsWith('/qualify') ? 'qualify'
    : pathname.endsWith('/workbench') ? params.get('view') === 'review' ? 'review' : 'workbench' : 'overview'
  const next = qualification?.stale && project.confirmed && !['won', 'lost', 'abandoned'].includes(project.outcome)
    ? { label: '重新检查投标资格', route: 'qualify' }
    : nextProjectAction(project, { resultKey: selectedKey ?? '', profile })
  const value = { project, profile, pkgIndex, setProfile: (v: string) => select({ profile: v }),
    setPkgIndex: (v: number) => select({ pkgIndex: v }), href, selectionLocked, setSelectionLocked }
  return <Context.Provider value={value}>
    <Card size="small" className="project-workspace">
      <div className="project-workspace-heading">
        <div><Typography.Text type="secondary">当前投标项目 · {project.batch_no || '读取中'}</Typography.Text>
          <Typography.Title level={4}>{project.batch_name || project.filename}</Typography.Title></div>
        <Space wrap><Button onClick={() => nav('/')}>全部投标项目</Button>
          <Button type="primary" onClick={() => nav(href(next.route, pkgIndex, next.view))}>{next.label}</Button></Space>
      </div>
      <div className="project-workspace-selection">
        <div><label htmlFor="project-company">本次投标企业</label><Select id="project-company" placeholder="选择企业档案" value={profile}
          disabled={selectionLocked} onChange={value.setProfile} options={profiles.map(p => ({ value: p.name, label: p.name }))} /></div>
        <div><label htmlFor="project-package">当前采购包</label><Select id="project-package" value={project.package_list.length ? pkgIndex : undefined}
          disabled={selectionLocked || !ready} onChange={value.setPkgIndex} placeholder="采购包尚未读取"
          options={project.package_list.map((p, i) => ({ value: i, label: `${p.sub_no} ${p.pkg_no} · ${p.project_name || p.sub_name || '采购包'}` }))} /></div>
        <Tag color={project.confirmed ? 'green' : 'orange'}>{project.confirmed ? '采购信息已确认' : '采购信息待确认'}</Tag>
      </div>
      {profileError && <Alert type="error" message="无法读取企业档案" description={errorMessage(profileError)} />}
      {!profileError && requestedProfile && !profile && profiles.length > 0 && <Alert type="warning" message="原选择的企业已不可用，请重新选择" />}
      <Tabs activeKey={active} onChange={key => nav(href(key === 'overview' ? '' : key === 'review' ? 'workbench' : key,
        pkgIndex, key === 'review' ? 'review' : key === 'workbench' ? 'prepare' : undefined))}
        items={[{ key: 'overview', label: '项目概览' }, { key: 'trm', label: '核对采购信息', disabled: !ready },
          { key: 'qualify', label: '检查投标资格', disabled: !ready }, { key: 'workbench', label: '准备与生成', disabled: !ready },
          { key: 'review', label: '审阅与导出', disabled: !ready }]} />
    </Card>
    <Outlet />
  </Context.Provider>
}
