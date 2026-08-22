import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Breadcrumb, Button, Card, Form, Input, InputNumber, Popconfirm, Select, Space, Spin, Table, Tabs, Tag, Typography, Upload, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import { api, Attachment, CompanyProfile, ExpiryItem } from '../../api'
import { KIND_SPECS } from './fields'
import KbItemsTab from './KbItemsTab'

const LEVEL: Record<ExpiryItem['level'], { color: string; text: string }> = {
  expired: { color: 'red', text: '已过期' }, d30: { color: 'volcano', text: '30 天内' }, d60: { color: 'orange', text: '60 天内' },
  d90: { color: 'gold', text: '90 天内' }, ok: { color: 'green', text: '有效' }, unknown: { color: 'default', text: '未录入' },
}
const KIND_CN: Record<string, string> = { certificates: '证照', test_reports: '检测报告' }

/** 主档：标量字段表单（名称/法人/注册资本/联系方式…），只更新主档不动子表。 */
function MainTab({ company, profile }: { company: string; profile: CompanyProfile }) {
  const qc = useQueryClient()
  const [form] = Form.useForm()
  useEffect(() => { form.setFieldsValue(profile) }, [profile, form])
  const save = useMutation({
    mutationFn: (v: Partial<CompanyProfile>) => api.saveMain(company, v),
    onSuccess: () => { message.success('主档已保存'); qc.invalidateQueries({ queryKey: ['profile', company] }); qc.invalidateQueries({ queryKey: ['profiles'] }) },
    onError: (e) => message.error(String(e)),
  })
  const text = (name: string, label: string, span = 1) => (
    <Form.Item name={name} label={label} style={{ gridColumn: `span ${span}` }}><Input /></Form.Item>
  )
  const num = (name: string, label: string) => (
    <Form.Item name={name} label={label}><InputNumber style={{ width: '100%' }} /></Form.Item>
  )
  return (
    <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', columnGap: 16 }}>
        {text('credit_code', '统一社会信用代码')}
        {text('legal_person', '法定代表人')}
        {text('legal_or_admin', '行政/技术负责人')}
        {text('company_type', '单位性质')}
        {text('founded', '成立时间')}
        {num('registered_capital_wan', '注册资本（万）')}
        {text('authorized_rep', '常用被授权人')}
        {text('authorized_rep_title', '被授权人职务')}
        {text('address', '单位地址及邮编', 2)}
        {text('bank', '开户银行及账号', 2)}
        {text('contact', '联系人')}
        {text('phone', '电话')}
        {text('email', 'E-mail')}
        {text('website', '网址')}
        {num('staff_total', '员工总数')}
        {num('staff_technical', '技术人员')}
        {num('senior_engineers', '高级职称')}
        {num('engineers', '中级职称')}
        <Form.Item name="business_scope" label="经营范围" style={{ gridColumn: '1 / -1' }}><Input.TextArea rows={3} /></Form.Item>
      </div>
      <Space>
        <Button type="primary" htmlType="submit" loading={save.isPending}>保存主档</Button>
        <Typography.Text type="secondary">建档依据：{profile.sources?.length ? profile.sources.join('；') : '（无）'}</Typography.Text>
      </Space>
    </Form>
  )
}

/** 有效期看板：证照 + 检测报告，按开标日推算。 */
function ExpiryTab({ company }: { company: string }) {
  const [days, setDays] = useState(90)
  const [on, setOn] = useState('')
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(on)
  const { data, isLoading } = useQuery({ queryKey: ['expiry', company, days, valid ? on : ''], queryFn: () => api.expiry(company, days, valid ? on : undefined) })
  const s = data?.summary ?? {}
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Space wrap>
        <span>预警范围</span>
        <Select value={days} onChange={setDays} style={{ width: 110 }} options={[30, 60, 90, 180, 365].map((d) => ({ value: d, label: `${d} 天内` }))} />
        <span>按开标日推算</span>
        <Input placeholder="YYYY-MM-DD（默认今天）" value={on} onChange={(e) => setOn(e.target.value)} style={{ width: 200 }} status={on && !valid ? 'error' : undefined} />
        {(['expired', 'd30', 'd60', 'd90', 'unknown'] as const).map((lv) => (
          <Tag key={lv} color={(s[lv] ?? 0) > 0 ? LEVEL[lv].color : 'default'}>{LEVEL[lv].text} {s[lv] ?? 0}</Tag>
        ))}
      </Space>
      <Table<ExpiryItem> size="small" rowKey={(r) => `${r.kind}-${r.id}`} loading={isLoading} dataSource={data?.items ?? []} pagination={false}
        columns={[
          { title: '状态', dataIndex: 'level', width: 100, render: (l: ExpiryItem['level']) => <Tag color={LEVEL[l].color}>{LEVEL[l].text}</Tag> },
          { title: '类别', dataIndex: 'kind', width: 100, render: (k: string) => KIND_CN[k] ?? k },
          { title: '名称', dataIndex: 'name' },
          { title: '编号', dataIndex: 'number', width: 180 },
          { title: '有效期至', dataIndex: 'valid_until', width: 120, render: (v: string) => v || <Typography.Text type="secondary">未录入</Typography.Text> },
          { title: '剩余天数', dataIndex: 'days_left', width: 100, render: (d: number | null) => d === null ? '—' : d },
        ]} />
    </Space>
  )
}

/** 附件库：上传 / 下载 / 删除；条目表单里可挂接。 */
function AttachmentsTab({ company }: { company: string }) {
  const qc = useQueryClient()
  const [kind, setKind] = useState('other')
  const { data = [], isLoading } = useQuery({ queryKey: ['attachments', company], queryFn: () => api.attachments(company) })
  const refresh = () => qc.invalidateQueries({ queryKey: ['attachments', company] })
  const upload = async (file: File) => {
    try { const a = await api.uploadAttachment(company, kind, file); message.success(`已上传 ${a.filename}`); refresh() } catch (e) { message.error(String(e)) }
    return false
  }
  const kinds = [['certificate', '证照'], ['person', '人员'], ['performance', '业绩'], ['financial', '财务'], ['product', '产品'], ['test_report', '检测报告'], ['other', '其他']]
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Space>
        <span>归类</span>
        <Select value={kind} onChange={setKind} style={{ width: 140 }} options={kinds.map(([v, l]) => ({ value: v, label: l }))} />
      </Space>
      <Upload.Dragger beforeUpload={upload} showUploadList={false} multiple>
        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
        <p>拖入扫描件（PDF/图片），同一文件按内容去重</p>
      </Upload.Dragger>
      <Table<Attachment> size="small" rowKey="id" loading={isLoading} dataSource={data} pagination={data.length > 20 ? { pageSize: 20 } : false}
        columns={[
          { title: '文件', dataIndex: 'filename', render: (v: string, r) => <a href={api.attachmentUrl(r.id)} target="_blank" rel="noreferrer">{v}</a> },
          { title: '归类', dataIndex: 'kind', width: 110, render: (k: string) => kinds.find(([v]) => v === k)?.[1] ?? k },
          { title: '大小', dataIndex: 'size', width: 100, render: (n: number) => n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB` },
          { title: '上传时间', dataIndex: 'uploaded_at', width: 170, render: (v: string) => v.replace('T', ' ').slice(0, 16) },
          { title: '操作', width: 80, render: (_, r) => (
            <Popconfirm title="删除附件？已挂接的条目会失去该文件" onConfirm={async () => { await api.deleteAttachment(company, r.id); refresh() }}>
              <Button size="small" type="link" danger>删除</Button>
            </Popconfirm>
          ) },
        ]} />
    </Space>
  )
}

/** 企业知识库详情：主档 / 有效期看板 / 各类条目 / 附件库。Tab 记在 URL（?tab=）便于回跳。 */
export default function KbCompanyPage() {
  const { name = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'main'
  const { data: profile, isLoading } = useQuery({ queryKey: ['profile', name], queryFn: () => api.profile(name) })
  const { data: expiry } = useQuery({ queryKey: ['expiry', name, 90, ''], queryFn: () => api.expiry(name, 90) })
  if (isLoading || !profile) return <Spin />
  const alert = (expiry?.summary.expired ?? 0) + (expiry?.summary.d30 ?? 0) + (expiry?.summary.d60 ?? 0) + (expiry?.summary.d90 ?? 0)

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Breadcrumb items={[{ title: <Link to="/kb">企业知识库</Link> }, { title: profile.name }]} />
      <Card size="small" title={<Space>{profile.name}<Typography.Text type="secondary" style={{ fontWeight: 400 }}>{profile.credit_code}</Typography.Text></Space>}>
        <Tabs activeKey={tab} onChange={(k) => setParams({ tab: k })} destroyInactiveTabPane
          items={[
            { key: 'main', label: '主档', children: <MainTab company={name} profile={profile} /> },
            { key: 'expiry', label: <Badge count={alert} size="small" offset={[10, 0]}>有效期看板</Badge>, children: <ExpiryTab company={name} /> },
            ...KIND_SPECS.map((spec) => ({
              key: spec.kind, label: `${spec.title}（${profile[spec.kind]?.length ?? 0}）`,
              children: <KbItemsTab company={name} spec={spec} />,
            })),
            { key: 'attachments', label: '附件库', children: <AttachmentsTab company={name} /> },
          ]} />
      </Card>
    </Space>
  )
}
