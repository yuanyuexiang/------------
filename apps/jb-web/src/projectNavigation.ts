import type { Project } from './api'

export interface ProjectSelection { profile?: string; pkgIndex?: number }
export type ProjectView = 'prepare' | 'generate' | 'review'

export function projectUrl(id: string, route = '', selection: ProjectSelection = {}, view?: ProjectView) {
  const params = new URLSearchParams()
  if (selection.profile) params.set('profile', selection.profile)
  if (selection.pkgIndex !== undefined) params.set('pkg', String(selection.pkgIndex))
  if (view) params.set('view', view)
  return `/projects/${id}${route ? `/${route}` : ''}${params.size ? `?${params}` : ''}`
}

export function nextProjectAction(project: Project, selection?: { resultKey: string; profile?: string }) {
  if (['won', 'lost', 'abandoned'].includes(project.outcome)) return { label: '查看项目结果', route: '' }
  if (!['parsed', 'confirmed'].includes(project.status)) return { label: '查看项目状态', route: '' }
  if (!project.confirmed) return { label: '核对采购信息', route: 'trm' }
  const generated = selection ? project.results.generate?.[selection.resultKey]
    : Object.values(project.results.generate ?? {})[0]
  if (generated && (!selection || generated.profile === selection.profile)) return { label: '继续审阅标书', route: 'workbench', view: 'review' as const }
  if (project.results.qualify && (!selection || project.results.qualify.profile === selection.profile)) return { label: '继续准备资料', route: 'workbench', view: 'prepare' as const }
  return { label: '检查投标资格', route: 'qualify' }
}

export function packageIndex(raw: string | number | undefined | null, count: number) {
  const index = Number(raw ?? 0)
  return Number.isInteger(index) && index >= 0 && index < count ? index : 0
}
