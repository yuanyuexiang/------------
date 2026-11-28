import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Checkbox, Collapse, Input, List, Modal, Segmented, Select, Space, Tag, Typography, Upload, message } from 'antd'
import { api, fmtUtc, type EnrichmentCandidate, type EnrichmentPreview, type EnrichmentResult, type EvidenceOrigin } from '../../api'
import { errorMessage } from '../../uiLabels'

type Mode = 'online' | 'attachment'

const MATERIALS = [
  { value: 'registry', label: '营业执照或登记报告', upload: 'certificate' },
  { value: 'credit', label: '信用查询报告', upload: 'certificate' },
  { value: 'certificate', label: '资质证书', upload: 'certificate' },
  { value: 'contract', label: '业绩合同', upload: 'performance' },
  { value: 'award', label: '中标或成交公告', upload: 'performance' },
  { value: 'financial', label: '审计或财务材料', upload: 'financial' },
  { value: 'test_report', label: '检测与试验报告', upload: 'test_report' },
]
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
  if (item.kind === 'field' || item.kind === 'registry') return <>
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

export default function CompanyEnrichment({ company = '', initialCode = '', initialMode = 'online', initialAttachment = '', onClose, onSaved }: {
  company?: string; initialCode?: string; initialMode?: Mode; initialAttachment?: string; onClose: () => void; onSaved: (result: EnrichmentResult) => void
}) {
  const qc = useQueryClient()
  const [mode, setMode] = useState<Mode>(initialMode)
  const [code, setCode] = useState(initialCode)
  const [kind, setKind] = useState(MATERIALS[0].value)
  const [attachmentId, setAttachmentId] = useState(initialAttachment)
  const [preview, setPreview] = useState<EnrichmentPreview>()
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState<'lookup' | 'upload' | 'save'>()
  const [error, setError] = useState('')
  const { data: files = [] } = useQuery({
    queryKey: ['attachments', company], queryFn: () => api.attachments(company), enabled: !!company && mode === 'attachment',
  })
  const clear = () => { setPreview(undefined); setSelected([]); setError('') }

  const lookup = async () => {
    clear()
    setBusy('lookup')
    try {
      const result = mode === 'online' ? await api.lookupCompany(company, code) : await api.readCompanyAttachment(company, attachmentId, kind)
      setPreview(result)
      setSelected(result.candidates.filter(x => !x.unchanged && (x.kind === 'field' || x.kind === 'registry')
        && (x.current == null || x.current === '' || x.current === x.value)).map(x => x.id))
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(undefined) }
  }

  const upload = async (file: File) => {
    clear()
    if (file.size > 30_000_000) { setError('文件超过 30 MB，请选取关键原件页上传'); return false }
    setBusy('upload')
    try {
      const item = await api.uploadAttachment(company, MATERIALS.find(x => x.value === kind)?.upload ?? 'other', file)
      await qc.invalidateQueries({ queryKey: ['attachments', company] })
      setAttachmentId(item.id)
      message.success('原件已上传')
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(undefined) }
    return false
  }

  const save = async () => {
    if (!preview?.token || !selected.length) return
    setBusy('save')
    setError('')
    try {
      const result = await api.applyCompanyEnrichment(preview.token, selected)
      const keys = [['profiles'], ['profile', result.company], ['kb', result.company], ['expiry', result.company],
        ['materials'], ['workflow'], ['preparation'], ['requirements'], ['qualification']]
      await Promise.all(keys.map(queryKey => qc.invalidateQueries({ queryKey })))
      message.success(result.records_added || result.records_updated
        ? `已保存，新增 ${result.records_added} 条、补充 ${result.records_updated} 条待审核资料` : '已保存所选企业字段')
      onSaved(result)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(undefined) }
  }

  return <Modal open title={company ? `${company} · 补全资料` : '联网新建企业'} width={780}
    onCancel={() => { if (!busy) onClose() }} cancelText="关闭" okText={company ? '保存所选资料' : '创建并保存'}
    onOk={() => void save()} confirmLoading={busy === 'save'} okButtonProps={{ disabled: !!busy || !selected.length }}>
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {company && <Segmented<Mode> value={mode} disabled={!!busy}
        options={[{ value: 'online', label: '联网查询' }, { value: 'attachment', label: '识别原件' }]}
        onChange={value => { setMode(value); clear() }} />}
      {mode === 'online' ? <Space.Compact block>
        <Input aria-label="统一社会信用代码" placeholder="输入18位统一社会信用代码" maxLength={18} value={code} disabled={!!busy}
          onChange={e => { setCode(e.target.value.toUpperCase()); clear() }}
          onPressEnter={() => { if (!busy && code.trim().length === 18) void lookup() }} />
        <Button type="primary" loading={busy === 'lookup'} disabled={!!busy || code.trim().length !== 18} onClick={() => void lookup()}>查询企业</Button>
      </Space.Compact> : <Space wrap>
        <Select aria-label="原件用途" value={kind} options={MATERIALS} disabled={!!busy}
          onChange={value => { setKind(value); clear() }} />
        <Select aria-label="选择已有原件" placeholder="选择附件库原件" value={attachmentId || undefined} style={{ minWidth: 210, maxWidth: 310 }}
          showSearch optionFilterProp="label" options={files.map(file => ({ value: file.id, label: file.filename }))}
          disabled={!!busy} onChange={value => { setAttachmentId(value); clear() }} />
        <Upload accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.docx" showUploadList={false} beforeUpload={upload} disabled={!!busy}>
          <Button loading={busy === 'upload'}>上传原件</Button>
        </Upload>
        <Button type="primary" loading={busy === 'lookup'} disabled={!!busy || !attachmentId} onClick={() => void lookup()}>提取字段</Button>
      </Space>}
      {error && <Alert type="error" showIcon message={error} />}
      {preview && <>
        {preview.extra['登记全称'] && <Alert type="warning" showIcon message={`登记全称为${preview.extra['登记全称']}，请核对企业更名`} />}
        {preview.checks.length > 0 && <List size="small" dataSource={preview.checks} renderItem={check =>
          <List.Item><Space wrap><Typography.Text strong>{check.title}</Typography.Text>
            <Tag color={check.status.includes('无法') || check.status.includes('未配置') ? 'orange' : 'blue'}>{check.status}</Tag>
            <Typography.Text type="secondary">{check.detail}</Typography.Text></Space></List.Item>} />}
        {preview.candidates.length > 0 && <>
          <Checkbox disabled={!!busy} checked={preview.candidates.filter(x => !x.unchanged).every(x => selected.includes(x.id))}
            indeterminate={selected.length > 0 && preview.candidates.some(x => !x.unchanged && !selected.includes(x.id))}
            onChange={e => setSelected(e.target.checked ? preview.candidates.filter(x => !x.unchanged).map(x => x.id) : [])}>全选可采用项</Checkbox>
          <div style={{ maxHeight: '42vh', overflowY: 'auto' }}>
            <List size="small" dataSource={preview.candidates} renderItem={item => <List.Item>
              <Space align="start" style={{ width: '100%' }}>
                <Checkbox aria-label={`采用${item.title}`} checked={selected.includes(item.id)} disabled={item.unchanged || !!busy}
                  onChange={e => setSelected(values => e.target.checked ? [...values, item.id] : values.filter(x => x !== item.id))} />
                <Space direction="vertical" size={2} style={{ overflowWrap: 'anywhere' }}>
                  <Space wrap><Typography.Text strong>{item.title}</Typography.Text>
                    {item.unchanged ? <Tag>已录入</Tag> : item.kind === 'field' || item.kind === 'registry'
                      ? item.current != null && item.current !== '' && item.current !== item.value && <Tag color="orange">有差异</Tag>
                      : <Tag color="orange">{item.existing_id ? '补充原件和空字段' : '待审核'}</Tag>}</Space>
                  <CandidateValue item={item} />
                  <EvidenceLink origin={item.origin} />
                </Space>
              </Space>
            </List.Item>} />
          </div>
        </>}
        <Collapse size="small" defaultActiveKey={!preview.candidates.length ? ['sources'] : []}
          items={[{ key: 'sources', label: '从官方入口获取原件', children: <Space wrap>
            {preview.sources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}</a>)}
            {company && mode === 'online' && <Button type="link" onClick={() => { setMode('attachment'); clear() }}>已有原件，提取字段</Button>}
          </Space> }]} />
      </>}
    </Space>
  </Modal>
}
