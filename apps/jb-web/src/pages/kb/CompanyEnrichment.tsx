import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { InboxOutlined } from '@ant-design/icons'
import { Alert, Button, Checkbox, List, Modal, Select, Space, Tag, Typography, Upload, message } from 'antd'
import { api, fmtUtc, type EnrichmentCandidate, type EnrichmentPreview, type EnrichmentResult, type EvidenceOrigin } from '../../api'
import { errorMessage } from '../../uiLabels'

const MATERIALS = [
  { value: 'registry', label: '营业执照或登记报告', upload: 'certificate' },
  { value: 'credit', label: '信用查询报告', upload: 'certificate' },
  { value: 'certificate', label: '资质证书', upload: 'certificate' },
  { value: 'contract', label: '业绩合同', upload: 'performance' },
  { value: 'award', label: '中标或成交公告', upload: 'performance' },
  { value: 'financial', label: '审计或财务材料', upload: 'financial' },
  { value: 'test_report', label: '检测与试验报告', upload: 'test_report' },
]
const REQUIRED_FIELDS = new Set(['field-name', 'field-credit_code'])
const NUMBERS: Record<string, string> = {
  number: '编号', issuer: '发证机构', cert_type: '证照类型', valid_from: '起始或查询日期', valid_until: '有效期至',
  buyer: '采购人', award_date: '中标公告日期', award_project_no: '项目编号', award_amount_wan: '中标金额（万元）',
  signed_date: '签署日期', amount_wan: '合同金额（万元）', service_scope: '服务范围', year: '年度',
  revenue_wan: '营业收入（万元）', net_profit_wan: '净利润（万元）', asset_wan: '资产（万元）',
  liability_wan: '负债（万元）', agency: '检测机构', issued_date: '出具日期', covered_models: '覆盖型号',
}

export function EvidenceLink({ origin }: { origin: EvidenceOrigin }) {
  const href = origin.attachment_id ? api.attachmentUrl(origin.attachment_id) : /^https?:\/\//i.test(origin.url) ? origin.url : ''
  const label = origin.title + (origin.page ? ` · 第${origin.page}页` : '')
  return <Space wrap size={6}>
    {href ? <a href={href} target="_blank" rel="noreferrer">{label}</a> : <Typography.Text>{label}</Typography.Text>}
    <Typography.Text type="secondary">{fmtUtc(origin.fetched_at)}</Typography.Text>
  </Space>
}

function CandidateValue({ item }: { item: EnrichmentCandidate }) {
  if (item.kind === 'field') return <>
    <Typography.Text>{String(item.value ?? '')}</Typography.Text>
    {item.current != null && item.current !== '' && item.current !== item.value &&
      <Typography.Text type="secondary">当前值 {item.current}</Typography.Text>}
    {item.origin.excerpt && <Typography.Text type="secondary">{item.origin.excerpt}</Typography.Text>}
  </>
  return <Space size={[8, 4]} wrap>
    {Object.entries(item.data).filter(([key, value]) => NUMBERS[key] && value != null && value !== '')
      .map(([key, value]) => <Typography.Text type="secondary" key={key}>{NUMBERS[key]} {String(value)}
        {item.field_origins[key]?.page ? `（第${item.field_origins[key].page}页）` : ''}</Typography.Text>)}
    {item.origin.excerpt && <Typography.Text type="secondary">{item.origin.excerpt}</Typography.Text>}
  </Space>
}

export default function CompanyEnrichment({ company = '', initialKind = '', initialAttachment = '', onClose, onManual, onSaved }: {
  company?: string; initialKind?: string; initialAttachment?: string
  onClose: () => void; onManual?: () => void; onSaved: (result: EnrichmentResult) => void
}) {
  const qc = useQueryClient()
  const [kind, setKind] = useState(MATERIALS.find(item => item.value === initialKind)?.value ?? MATERIALS[0].value)
  const [attachmentId, setAttachmentId] = useState(initialAttachment)
  const [registryFile, setRegistryFile] = useState<File>()
  const [preview, setPreview] = useState<EnrichmentPreview>()
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState<'lookup' | 'upload' | 'save'>()
  const [error, setError] = useState('')
  const { data: files = [] } = useQuery({
    queryKey: ['attachments', company], queryFn: () => api.attachments(company), enabled: !!company,
  })
  const { data: sources = [] } = useQuery({ queryKey: ['company-sources'], queryFn: api.companySources })
  const relatedSources = sources.filter(source => source.materials.includes(kind))
  const clear = () => { setPreview(undefined); setSelected([]); setError('') }
  const showPreview = (result: EnrichmentPreview) => {
    setPreview(result)
    setSelected(result.candidates.filter(x => !x.unchanged && (!company || (x.kind === 'field' &&
      (x.current == null || x.current === '' || x.current === x.value)))).map(x => x.id))
  }

  const lookup = async () => {
    clear()
    setBusy('lookup')
    try {
      showPreview(await api.readCompanyAttachment(company, attachmentId, kind))
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(undefined) }
  }

  const upload = async (file: File) => {
    clear()
    if (!file.size || file.size > 30_000_000) { setError('请选择大小在 30 MB 以内的非空原件'); return false }
    setBusy('upload')
    try {
      if (company) {
        const item = await api.uploadAttachment(company, MATERIALS.find(x => x.value === kind)?.upload ?? 'other', file)
        setAttachmentId(item.id)
        await qc.invalidateQueries({ queryKey: ['attachments', company] })
        showPreview(await api.readCompanyAttachment(company, item.id, kind))
      } else {
        setRegistryFile(file)
        showPreview(await api.previewCompanyRegistry(file))
      }
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(undefined) }
    return false
  }

  const save = async () => {
    if (!preview?.token || !selected.length) return
    setBusy('save')
    setError('')
    try {
      const result = registryFile
        ? await api.createCompanyFromRegistry(registryFile, preview.token, selected)
        : await api.applyCompanyEnrichment(preview.token, selected)
      const keys = [['profiles'], ['profile', result.company], ['kb', result.company], ['expiry', result.company],
        ['materials'], ['workflow'], ['preparation'], ['requirements'], ['qualification'], ['attachments', result.company]]
      await Promise.all(keys.map(queryKey => qc.invalidateQueries({ queryKey })))
      message.success(result.records_added || result.records_updated
        ? `已保存，新增 ${result.records_added} 条、补充 ${result.records_updated} 条待审核资料` : '已保存所选企业字段')
      onSaved(result)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(undefined) }
  }

  const optional = (item: EnrichmentCandidate) => !item.unchanged && (!!company || !REQUIRED_FIELDS.has(item.id))
  const optionalItems = preview?.candidates.filter(optional) ?? []
  const optionalSelected = optionalItems.filter(item => selected.includes(item.id)).length
  return <Modal open title={company ? '补全企业资料' : '从登记原件新建企业'} width={780}
    onCancel={() => { if (!busy) onClose() }} cancelText="关闭" okText={company ? '保存所选资料' : '创建并保存'}
    onOk={() => void save()} confirmLoading={busy === 'save'} okButtonProps={{ disabled: !!busy || !selected.length }}>
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {company && <Space wrap>
        <Select aria-label="原件用途" value={kind} options={MATERIALS} disabled={!!busy}
          onChange={value => { setKind(value); clear() }} />
        <Select aria-label="选择已有原件" placeholder="选择附件库原件" value={attachmentId || undefined} style={{ minWidth: 210, maxWidth: 310 }}
          showSearch optionFilterProp="label" options={files.map(file => ({ value: file.id, label: file.filename }))}
          disabled={!!busy} onChange={value => { setAttachmentId(value); clear() }} />
        <Button type="primary" loading={busy === 'lookup'} disabled={!!busy || !attachmentId} onClick={() => void lookup()}>提取字段</Button>
      </Space>}
      <Upload.Dragger accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.docx" showUploadList={false} beforeUpload={upload} disabled={!!busy}>
        <div className="ant-upload-drag-icon"><InboxOutlined /></div>
        <p className="ant-upload-text">{busy === 'upload' ? '正在识别原件' : company ? '点击或拖入原件' : '点击或拖入营业执照或登记报告'}</p>
        <p className="ant-upload-hint">支持 PDF、图片或 Word，单份不超过 30 MB</p>
      </Upload.Dragger>
      {(relatedSources.length > 0 || onManual) && <Space wrap size={[12, 4]}>
        {relatedSources.length > 0 && <Typography.Text type="secondary">缺少原件？前往</Typography.Text>}
        {relatedSources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}</a>)}
        {onManual && <Button type="link" size="small" disabled={!!busy} onClick={onManual}>手动新建</Button>}
      </Space>}
      {error && <Alert type="error" showIcon message={error} />}
      {preview && <>
        {preview.checks.length > 0 && <List size="small" dataSource={preview.checks} renderItem={check =>
          <List.Item><Space wrap><Typography.Text strong>{check.title}</Typography.Text>
            <Tag color={check.status.includes('无法') || check.status.includes('未配置') ? 'orange' : 'blue'}>{check.status}</Tag>
            <Typography.Text type="secondary">{check.detail}</Typography.Text></Space></List.Item>} />}
        {preview.candidates.length > 0 && <>
          {optionalItems.length > 0 && <Checkbox disabled={!!busy} checked={optionalSelected === optionalItems.length}
            indeterminate={optionalSelected > 0 && optionalSelected < optionalItems.length}
            onChange={e => setSelected([
              ...selected.filter(id => !company && REQUIRED_FIELDS.has(id)),
              ...(e.target.checked ? optionalItems.map(item => item.id) : []),
            ])}>全选可采用项</Checkbox>}
          <div style={{ maxHeight: '42vh', overflowY: 'auto' }}>
            <List size="small" dataSource={preview.candidates} renderItem={item => <List.Item>
              <Space align="start" style={{ width: '100%' }}>
                <Checkbox aria-label={`采用${item.title}`} checked={selected.includes(item.id)} disabled={!!busy || !optional(item)}
                  onChange={e => setSelected(values => e.target.checked ? [...values, item.id] : values.filter(x => x !== item.id))} />
                <Space direction="vertical" size={2} style={{ overflowWrap: 'anywhere' }}>
                  <Space wrap><Typography.Text strong>{item.title}</Typography.Text>
                    {item.unchanged ? <Tag>已录入</Tag> : item.kind === 'field'
                      ? item.current != null && item.current !== '' && item.current !== item.value && <Tag color="orange">有差异</Tag>
                      : <Tag color="orange">{item.existing_id ? '补充原件和空字段' : '待审核'}</Tag>}</Space>
                  <CandidateValue item={item} />
                  <EvidenceLink origin={item.origin} />
                </Space>
              </Space>
            </List.Item>} />
          </div>
        </>}
      </>}
    </Space>
  </Modal>
}
