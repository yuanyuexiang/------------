/** jb-api 客户端：所有请求走 /api（dev 由 Vite 代理到 8000，部署由 Nginx 反代）。 */

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const json = (body: unknown, method = 'PUT'): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

export interface Project {
  id: string; filename: string; status: string; batch_name: string; batch_no: string
  error: string; created_at: string; confirmed: boolean
}
export interface Task {
  id: string; project_id: string; kind: string; status: string; progress: number
  message: string; result: Record<string, unknown> | null
}
export interface KeyTerms {
  validity_days: number | null; validity_clause: string
  deposit_mode: string | null; deposit_clause: string
  sign_whole_doc: boolean | null; sign_clause: string
  paperless: boolean | null; electronic: boolean | null
  clarify_deadline: string | null; max_price_clause: string; max_price_note: string
  vat_note: string; llm_filled: string[]
}
export interface SpecParamRow { row: number; name: string; unit: string; required: string; star: boolean; response: string | null }
export interface SpecDoc { spec_id: string; title: string; source: string; structured: boolean; param_rows: SpecParamRow[] }
export interface Material { sub_no: string; pkg: string; project: string; desc: string; unit: string; qty: string; deliver_date: string; deliver_place: string; spec_id: string }
export interface QualificationItem {
  sub_name: string; pkg: string; performance_req: string; test_report_req: string
  other_reqs: Record<string, string>; accept_agent: string
  perf_years: number | null; perf_scope: string; report_required: boolean | null; llm_extracted: boolean
}
export interface ScoringRef {
  price_method: string; benchmark_c: number | null; biz_template: string; tech_template: string
  weight_biz: number | null; weight_tech: number | null; weight_price: number | null
}
export interface PackageTRM {
  sub_no: string; sub_name: string; pkg_no: string; project_name: string; project_unit: string; scope: string
  budget_yuan: number | null; max_price: string; duration_days: number | null; price_mode: string
  allow_consortium: boolean | null; scoring_ref: ScoringRef
  materials: Material[]; qualification: QualificationItem[]; spec_docs: SpecDoc[]
}
export interface TRM {
  batch_name: string; batch_no: string; terminology: string; source_zip: string
  prenotice: { clause_no: string; name: string; content: string }[]
  rejection_rules: { category: string; aspect: string; text: string }[]
  submission_table: { seq: string; item: string; channels: string[]; port: string; section: string }[]
  packages: PackageTRM[]
  key_terms: KeyTerms
  scoring_templates: { name: string; kind: string; source: string; items: { element: string; content: string; score_min: number | null; score_max: number | null }[] }[]
  warnings: string[]
}
export interface Check { item: string; status: string; reason: string; evidence: string[]; requirement: string; by_llm: boolean }
export interface FeasibilityReport {
  batch_name: string; company: string
  packages: { sub_no: string; sub_name: string; pkg_no: string; project_name: string; verdict: string; checks: Check[] }[]
}

export interface Performance { project: string; buyer: string; buyer_is_end_user: boolean | null; amount_wan: number | null; signed_date: string; evidence: string[]; source: string }
export interface CompanyProfile {
  name: string; credit_code: string; registered_capital_wan: number | null; staff_total: number | null
  certificates: { name: string; cert_type: string; valid_until: string }[]
  personnel: { name: string; title: string; credentials: string[] }[]
  performances: Performance[]
  [k: string]: unknown
}

export interface Finding { rule_id: string; level: string; title: string; message: string; location: string; source: string }
export interface ItemScore { element: string; kind: string; score_min: number; score_max: number; predicted: number | null; method: string; basis: string; missing: string[] }
export interface ScoreReport { pkg_no: string; items: ItemScore[]; tech_total: number | null; biz_total: number | null; tech_max: number; biz_max: number; weighted: number | null; notes: string[] }
export interface GenResult {
  summary: { commercial: string; technical: string; todo_count: number; export_blocked: boolean; tech_params: { spec_id: string; rows: number; satisfied: number; deviation: number; unknown: number; missing: number }[] }
  todos: Record<string, string[]>; files: string[]; draft_markdown: string
  tech_params: { spec_id: string; responses: { row: number; name: string; required: string; star: boolean; response: string; verdict: string; reason: string }[] }[]
}

export const api = {
  generate: (id: string, profile: string, pkgIndex: number, withDraft: boolean) =>
    req<{ task_id: string; mode: string }>(`/api/projects/${id}/generate?profile=${encodeURIComponent(profile)}&pkg_index=${pkgIndex}&with_draft=${withDraft}`, { method: 'POST' }),
  review: (id: string, profile: string, pkgIndex: number) =>
    req<{ blocked: boolean; counts: Record<string, number>; findings: Finding[]; markdown: string }>(`/api/projects/${id}/review?profile=${encodeURIComponent(profile)}&pkg_index=${pkgIndex}`, { method: 'POST' }),
  score: (id: string, profile: string, pkgIndex: number, llm: boolean, taskId?: string) =>
    req<{ report: ScoreReport; heatmap: { element: string; loss: number; predicted: number; max: number; missing: string[] }[]; markdown: string }>(
      `/api/projects/${id}/score?profile=${encodeURIComponent(profile)}&pkg_index=${pkgIndex}&llm=${llm}${taskId ? `&task_id=${taskId}` : ''}`, { method: 'POST' }),
  exportFile: (id: string, filename: string, force = false) =>
    req<{ ok: boolean; blocked_count: number; blocked_by: string[]; pdf: string | null; notes: string[] }>(`/api/projects/${id}/export?filename=${encodeURIComponent(filename)}&force=${force}`, { method: 'POST' }),
  submissionMatrix: (id: string, pkgIndex: number) =>
    req<{ rows: { section: string; seq: string; item: string; channels: string[]; port: string; generated_file: string | null; status: string }[] }>(`/api/projects/${id}/submission-matrix?pkg_index=${pkgIndex}`),
  fileUrl: (id: string, filename: string) => `/api/projects/${id}/files/${encodeURIComponent(filename)}`,
  profile: (name: string) => req<CompanyProfile>(`/api/profiles/${encodeURIComponent(name)}`),
  saveProfile: (name: string, p: CompanyProfile) => req<{ ok: boolean }>(`/api/profiles/${encodeURIComponent(name)}`, json(p)),
  health: () => req<{ status: string; task_mode: string }>('/api/health'),
  projects: () => req<Project[]>('/api/projects'),
  project: (id: string) => req<Project>(`/api/projects/${id}`),
  upload: (file: File) => {
    const form = new FormData(); form.append('file', file)
    return req<{ id: string; task_id: string; mode: string }>('/api/projects', { method: 'POST', body: form })
  },
  task: (id: string) => req<Task>(`/api/tasks/${id}`),
  trm: (id: string, confirmed = false) => req<TRM>(`/api/projects/${id}/trm?confirmed=${confirmed}`),
  confirmTrm: (id: string, trm: TRM) => req<{ ok: boolean }>(`/api/projects/${id}/trm`, json(trm)),
  profiles: () => req<{ name: string; credit_code: string }[]>('/api/profiles'),
  qualify: (id: string, profile: string, llm: boolean) =>
    req<{ report: FeasibilityReport; markdown: string }>(
      `/api/projects/${id}/qualify?profile=${encodeURIComponent(profile)}&llm=${llm}`, { method: 'POST' }),
}
