/** jb-api 客户端：所有请求走 /api（dev 由 Vite 代理到 8000，部署由 Nginx 反代）。 */

const TOKEN_KEY = 'jb_token'
export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY) ?? '' } catch { return '' } }
export const setToken = (t: string) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ } }
/** 下载链接（<a href>）带不了 header，用 ?token= 传令牌。 */
export const withToken = (url: string) => `${url}${url.includes('?') ? '&' : '?'}token=${encodeURIComponent(getToken())}`

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const token = getToken()
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(url, { ...init, headers })
  if (res.status === 401 && !url.startsWith('/api/auth/login')) {
    setToken('')
    if (!window.location.pathname.startsWith('/login')) window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

/** 后端时间戳为 naive UTC ISO（无时区后缀）→ 本地 "YYYY-MM-DD HH:mm"。投标截止等业务时间是墙钟字符串，不经此转换。 */
export function fmtUtc(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const json = (body: unknown, method = 'PUT'): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

export interface Project {
  id: string; filename: string; status: string; batch_name: string; batch_no: string
  error: string; created_at: string; updated_at: string; confirmed: boolean
  deadline: string; open_time: string; deadline_manual: boolean; days_left: number | null
  stage: string; stage_cn: string; outcome: string; outcome_cn: string; active: boolean; notes: string
  pkg_nos: string[]; packages: number
  results: {
    qualify?: { profile: string; verdicts: Record<string, string>; llm: boolean }
    generate?: Record<string, { todo_count: number; export_blocked: boolean; files: string[]; with_draft: boolean; profile: string }>
    review?: Record<string, { blocked: boolean; counts: Record<string, number>; profile: string }>
    score?: Record<string, { weighted: number | null; tech_total: number | null; tech_max: number; biz_total: number | null; biz_max: number; llm: boolean }>
  }
}
export interface ProjectEvent { id: string; kind: string; message: string; data: Record<string, unknown> | null; actor: string; created_at: string }
export interface ProjectDetail extends Project {
  key_terms: Partial<KeyTerms> & { bid_deadline?: string | null; bid_deadline_text?: string; bid_open_time?: string | null; bid_open_note?: string }
  package_list: { pkg_no: string; sub_no: string; sub_name: string; project_name: string; budget_yuan: number | null; max_price: string; materials: number; spec_docs: number }[]
  events: ProjectEvent[]
  tasks: { id: string; kind: string; status: string; progress: number; message: string; created_at: string }[]
  files: { name: string; size: number; modified: string }[]
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

// ---- 企业知识库（与 jb_kb.models 对齐；条目通用字段 id/status/attachments/source） ----
export interface KbItem { id: string; status?: string; attachments?: string[]; source?: string; [k: string]: unknown }
export interface Certificate extends KbItem { name: string; cert_type: string; number: string; issuer: string; level: string; valid_from: string; valid_until: string }
export interface Person extends KbItem { name: string; title: string; major: string; education: string; social_insurance_unit: string; available: boolean | null; credentials: string[] }
export interface Performance extends KbItem {
  project: string; buyer: string; buyer_type: string; buyer_is_end_user: boolean | null; in_sgcc: boolean | null
  amount_wan: number | null; signed_date: string; commissioned_date: string; material_category: string; voltage_level: string; evidence: string[]
}
export interface FinancialYear extends KbItem { year: string; revenue_wan: number | null; net_profit_wan: number | null; asset_wan: number | null; liability_ratio: string }
export interface Product extends KbItem { model: string; name: string; category: string; params: Record<string, string>; features: string[]; test_reports: string[]; spec_ids: string[] }
export interface TestReport extends KbItem { name: string; report_type: string; agency: string; number: string; issued_date: string; valid_until: string; covered_models: string[] }
export interface Boilerplate extends KbItem { topic: string; title: string; text: string; applicable_types: string[]; approved: boolean }
export interface Attachment { id: string; kind: string; filename: string; content_type: string; size: number; sha256: string; storage_path: string; uploaded_at: string }
export type KbKind = 'certificates' | 'personnel' | 'performances' | 'financials' | 'products' | 'test_reports' | 'boilerplates'
export interface CompanyProfile {
  name: string; credit_code: string; legal_person: string; legal_or_admin: string; authorized_rep: string; authorized_rep_title: string
  founded: string; registered_capital_wan: number | null; company_type: string; address: string; bank: string
  contact: string; phone: string; email: string; website: string; business_scope: string
  staff_total: number | null; staff_technical: number | null; senior_engineers: number | null; engineers: number | null
  certificates: Certificate[]; personnel: Person[]; performances: Performance[]; financials: FinancialYear[]
  products: Product[]; test_reports: TestReport[]; boilerplates: Boilerplate[]; sources: string[]
  [k: string]: unknown
}
export interface ProfileSummary { name: string; credit_code: string; updated_at: string; counts: Record<KbKind, number> }
export interface ExpiryItem { kind: string; id: string; name: string; number: string; valid_until: string; days_left: number | null; level: 'expired' | 'd30' | 'd60' | 'd90' | 'ok' | 'unknown' }
export interface ExpiryReport { items: ExpiryItem[]; summary: Record<string, number> }

export interface Finding { rule_id: string; level: string; title: string; message: string; location: string; source: string }
export interface ItemScore { element: string; kind: string; score_min: number; score_max: number; predicted: number | null; method: string; basis: string; missing: string[] }
export interface ScoreReport { pkg_no: string; items: ItemScore[]; tech_total: number | null; biz_total: number | null; tech_max: number; biz_max: number; weighted: number | null; notes: string[] }
export interface GenResult {
  summary: { commercial: string; technical: string; todo_count: number; export_blocked: boolean; tech_params: { spec_id: string; rows: number; satisfied: number; deviation: number; unknown: number; missing: number }[] }
  todos: Record<string, string[]>; files: string[]; draft_markdown: string
  tech_params: { spec_id: string; responses: { row: number; name: string; required: string; star: boolean; response: string; verdict: string; reason: string }[] }[]
}

// ---- 配置中心 ----
export interface ScoringTemplateSummary { id: string; name: string; kind: string; source: string; origin: string; note: string; item_count: number; updated_at: string; updated_by: string }
export interface ScoringTemplateFull extends ScoringTemplateSummary { items: { group: string; element: string; content: string; score_min: number | null; score_max: number | null }[] }
export interface RuleEntry {
  rule_id: string; level: string; title: string; source: string; doc: string; default_params: Record<string, unknown>
  enabled: boolean; level_override: string; params: Record<string, unknown>; note: string; updated_at: string | null
}
export interface LlmConfig {
  effective: { base_url: string; model: string; temperature: number; timeout: number; key_configured: boolean }
  saved: { base_url: string | null; model: string | null; temperature: number | null; timeout: number | null }
  env: { base_url: string; model: string }
  available: boolean
  usage: {
    days: number; calls: number; failed: number; prompt_tokens: number; completion_tokens: number; avg_latency_ms: number
    by_purpose: { purpose: string; calls: number; prompt_tokens: number; completion_tokens: number }[]
    by_day: { day: string; calls: number; tokens: number }[]
    recent: { created_at: string; model: string; purpose: string; ok: boolean; latency_ms: number; prompt_tokens: number | null; completion_tokens: number | null; error: string }[]
  }
}

// ---- 用户与权限 ----
export interface User {
  id: string; username: string; display_name: string; role: 'admin' | 'member'; role_cn: string
  can_view_price: boolean; active: boolean; must_change_password: boolean; created_at: string; last_login_at: string | null
}

export const api = {
  login: (username: string, password: string) => req<{ token: string; user: User; dev_secret: boolean }>('/api/auth/login', json({ username, password }, 'POST')),
  me: () => req<{ user: User; dev_secret: boolean }>('/api/auth/me'),
  changePassword: (old_password: string, new_password: string) => req<{ ok: boolean }>('/api/auth/password', json({ old_password, new_password })),
  users: () => req<User[]>('/api/users'),
  createUser: (body: { username: string; password: string; display_name?: string; role?: string; can_view_price?: boolean }) => req<User>('/api/users', json(body, 'POST')),
  updateUser: (id: string, body: Partial<Pick<User, 'display_name' | 'role' | 'can_view_price' | 'active'>> & { reset_password?: string }) => req<User>(`/api/users/${id}`, json(body)),
  deleteUser: (id: string) => req<{ ok: boolean }>(`/api/users/${id}`, { method: 'DELETE' }),
  scoringTemplates: () => req<ScoringTemplateSummary[]>('/api/config/scoring-templates'),
  scoringTemplate: (id: string) => req<ScoringTemplateFull>(`/api/config/scoring-templates/${id}`),
  createScoringTemplate: (body: Partial<ScoringTemplateFull>) => req<ScoringTemplateFull>('/api/config/scoring-templates', json(body, 'POST')),
  updateScoringTemplate: (id: string, body: Partial<ScoringTemplateFull>) => req<ScoringTemplateFull>(`/api/config/scoring-templates/${id}`, json(body)),
  deleteScoringTemplate: (id: string) => req<{ ok: boolean }>(`/api/config/scoring-templates/${id}`, { method: 'DELETE' }),
  uploadScoringTemplate: (file: File, overwrite: boolean) => {
    const form = new FormData(); form.append('file', file)
    return req<ScoringTemplateFull>(`/api/config/scoring-templates/upload?overwrite=${overwrite}`, { method: 'POST', body: form })
  },
  rules: () => req<{ levels: string[]; rules: RuleEntry[] }>('/api/config/rules'),
  updateRule: (id: string, body: Partial<Pick<RuleEntry, 'enabled' | 'level_override' | 'params' | 'note'>>) => req<{ ok: boolean }>(`/api/config/rules/${id}`, json(body)),
  resetRule: (id: string) => req<{ ok: boolean }>(`/api/config/rules/${id}`, { method: 'DELETE' }),
  llmConfig: (days = 30) => req<LlmConfig>(`/api/config/llm?days=${days}`),
  saveLlm: (body: Record<string, unknown>) => req<{ saved: Record<string, unknown>; effective: LlmConfig['effective'] }>('/api/config/llm', json(body)),
  testLlm: (base_url?: string, model?: string) => {
    const q = new URLSearchParams(); if (base_url) q.set('base_url', base_url); if (model) q.set('model', model)
    return req<{ ok: boolean; latency_ms: number; model: string; reply?: string; error?: string }>(`/api/config/llm/test${q.toString() ? `?${q}` : ''}`, { method: 'POST' })
  },
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
  fileUrl: (id: string, filename: string) => withToken(`/api/projects/${id}/files/${encodeURIComponent(filename)}`),
  profile: (name: string) => req<CompanyProfile>(`/api/profiles/${encodeURIComponent(name)}`),
  saveProfile: (name: string, p: CompanyProfile) => req<{ ok: boolean }>(`/api/profiles/${encodeURIComponent(name)}`, json(p)),
  health: () => req<{ status: string; task_mode: string }>('/api/health'),
  projects: (active?: boolean) => req<Project[]>(`/api/projects${active === undefined ? '' : `?active=${active}`}`),
  project: (id: string) => req<Project>(`/api/projects/${id}`),
  projectDetail: (id: string) => req<ProjectDetail>(`/api/projects/${id}/detail`),
  patchProject: (id: string, fields: Partial<Pick<Project, 'deadline' | 'open_time' | 'outcome' | 'notes'>>) =>
    req<Project>(`/api/projects/${id}`, json(fields, 'PATCH')),
  deleteProject: (id: string) => req<{ ok: boolean }>(`/api/projects/${id}`, { method: 'DELETE' }),
  upload: (file: File) => {
    const form = new FormData(); form.append('file', file)
    return req<{ id: string; task_id: string; mode: string }>('/api/projects', { method: 'POST', body: form })
  },
  task: (id: string) => req<Task>(`/api/tasks/${id}`),
  trm: (id: string, confirmed = false) => req<TRM>(`/api/projects/${id}/trm?confirmed=${confirmed}`),
  confirmTrm: (id: string, trm: TRM) => req<{ ok: boolean }>(`/api/projects/${id}/trm`, json(trm)),
  profiles: () => req<ProfileSummary[]>('/api/profiles'),
  saveMain: (name: string, fields: Partial<CompanyProfile>) => req<CompanyProfile>(`/api/profiles/${encodeURIComponent(name)}/main`, json(fields)),
  deleteProfile: (name: string) => req<{ ok: boolean }>(`/api/profiles/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  expiry: (name: string, days = 90, on?: string) =>
    req<ExpiryReport>(`/api/profiles/${encodeURIComponent(name)}/expiry?days=${days}${on ? `&on=${on}` : ''}`),
  kbList: <T extends KbItem>(name: string, kind: KbKind) => req<T[]>(`/api/profiles/${encodeURIComponent(name)}/${kind}`),
  kbCreate: <T extends KbItem>(name: string, kind: KbKind, item: Partial<T>) =>
    req<T>(`/api/profiles/${encodeURIComponent(name)}/${kind}`, json(item, 'POST')),
  kbUpdate: <T extends KbItem>(name: string, kind: KbKind, id: string, item: Partial<T>) =>
    req<T>(`/api/profiles/${encodeURIComponent(name)}/${kind}/${id}`, json(item)),
  kbDelete: (name: string, kind: KbKind, id: string) =>
    req<{ ok: boolean }>(`/api/profiles/${encodeURIComponent(name)}/${kind}/${id}`, { method: 'DELETE' }),
  attachments: (name: string, kind = '') => req<Attachment[]>(`/api/profiles/${encodeURIComponent(name)}/attachments${kind ? `?kind=${kind}` : ''}`),
  uploadAttachment: (name: string, kind: string, file: File) => {
    const form = new FormData(); form.append('file', file)
    return req<Attachment>(`/api/profiles/${encodeURIComponent(name)}/attachments?kind=${kind}`, { method: 'POST', body: form })
  },
  deleteAttachment: (name: string, id: string) => req<{ ok: boolean }>(`/api/profiles/${encodeURIComponent(name)}/attachments/${id}`, { method: 'DELETE' }),
  attachmentUrl: (id: string) => withToken(`/api/attachments/${id}`),
  qualify: (id: string, profile: string, llm: boolean) =>
    req<{ report: FeasibilityReport; markdown: string }>(
      `/api/projects/${id}/qualify?profile=${encodeURIComponent(profile)}&llm=${llm}`, { method: 'POST' }),
}
