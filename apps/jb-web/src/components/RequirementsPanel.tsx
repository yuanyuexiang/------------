import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Checkbox, Collapse, Drawer, Empty, Input, Select, Space, Spin, Table, Tag, Typography, message } from 'antd'
import { api, fmtUtc, RequirementRow } from '../api'
import { errorMessage } from '../uiLabels'
import { useProjectWorkspace } from './ProjectWorkspace'
import SourceDocument, { DocumentReader } from './DocumentReader'
import './RequirementsPanel.css'

const STATUS = { unlinked: ['未关联', 'default'], linked: ['已关联，待核对', 'blue'], confirmed: ['已人工核对', 'green'], stale: ['关联需复核', 'orange'] }
const KIND: Record<string, string> = { certificates: '证照', personnel: '人员', performances: '业绩', financials: '财务', products: '产品', test_reports: '检测报告' }

export default function RequirementsPanel() {
  const { id = '' } = useParams()
  const { profile, pkgIndex, href, selectionLocked } = useProjectWorkspace()
  const [params, setParams] = useSearchParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [group, setGroup] = useState<string>()
  const [status, setStatus] = useState<string>()
  const [evidenceIds, setEvidenceIds] = useState<string[]>([])
  const [filename, setFilename] = useState<string>()
  const [blockId, setBlockId] = useState<string>()
  const [note, setNote] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [linkRevision, setLinkRevision] = useState('')
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['requirements', id, profile, pkgIndex],
    queryFn: () => api.requirements(id, profile!, pkgIndex), enabled: !!profile })
  const row = data?.requirements.find(r => r.id === params.get('requirement'))
  const { data: preview, isLoading: previewLoading, error: previewError } = useQuery({
    queryKey: ['document-preview', id, profile, pkgIndex, filename, data?.generation_id],
    queryFn: () => api.documentPreview(id, profile!, pkgIndex, filename!), enabled: !!row && !!filename && !!profile, retry: false })
  useEffect(() => {
    if (!row) return
    setLinkRevision(row.link_revision)
    setEvidenceIds(row.link.evidence_ids ?? [])
    setFilename(data?.files.includes(row.link.response?.filename ?? '') ? row.link.response?.filename : undefined)
    setBlockId(row.status === 'stale' ? undefined : row.link.response?.block_id)
    setNote(row.link.note ?? '')
    setConfirmed(row.status === 'confirmed')
  }, [row?.id, profile, pkgIndex])
  const focus = (value?: RequirementRow) => setParams(current => {
    const next = new URLSearchParams(current)
    if (value) next.set('requirement', value.id); else next.delete('requirement')
    return next
  }, { replace: true })
  const save = async () => {
    if (!row || !data || !profile) return
    setSaving(true)
    try {
      await api.saveRequirement(id, profile, pkgIndex, row.id, { revision: data.revision, link_revision: linkRevision, evidence_ids: evidenceIds,
        response: filename && blockId && preview?.generation_id ? { filename, block_id: blockId, generation_id: preview.generation_id } : null, note, confirmed })
      await qc.invalidateQueries({ queryKey: ['requirements', id] })
      message.success('关联已保存；人工核对记录不代表整份投标文件已通过审查')
      focus()
    } catch (e) { message.error(errorMessage(e)) } finally { setSaving(false) }
  }
  if (!profile) return <Card title="本包要求与证据"><Empty description="请选择投标企业，查看本包要求及当前选材" /></Card>
  if (error) return <Alert type="error" message="要求清单读取失败" description={errorMessage(error)} action={<Button onClick={() => void refetch()}>重试</Button>} />
  if (isLoading || !data) return <Spin />
  const rows = data.requirements.filter(r => (!group || r.group === group) && (!status || r.status === status)
    && (!search || `${r.title}${r.text}${r.source}`.includes(search)))
  return <>
    <Card size="small" title="本包要求与证据" extra={<Typography.Text type="secondary">关联记录不替代合规审查</Typography.Text>}>
      <Typography.Paragraph type="secondary">清单汇总已解析的采购要求，仍需对照完整原件核查遗漏；关联材料不等于满足要求。</Typography.Paragraph>
      <div className="requirement-summary"><span>采购要求 {data.requirements.length} 项</span><span>已关联 {data.requirements.filter(r => r.status !== 'unlinked').length} 项</span>
        <span>关联需复核 {data.requirements.filter(r => r.status === 'stale').length} 项</span><span>当前生成版本 {data.generation_id?.slice(0, 8) || '尚未生成'}</span></div>
      <div className="requirement-filters">
        <Input.Search placeholder="查找要求、条款或原文" aria-label="查找采购要求" value={search} onChange={e => setSearch(e.target.value)} allowClear />
        <Select allowClear placeholder="全部要求类型" style={{ minWidth: 160 }} value={group} onChange={setGroup} options={Object.entries(data.groups).map(([value, label]) => ({ value, label }))} />
        <Select allowClear placeholder="全部关联状态" style={{ minWidth: 160 }} value={status} onChange={setStatus} options={Object.entries(STATUS).map(([value, [label]]) => ({ value, label }))} />
      </div>
      <Table<RequirementRow> size="small" rowKey="id" scroll={{ x: 760 }} dataSource={rows} pagination={{ pageSize: 6, showSizeChanger: true }} columns={[
        { title: '采购要求', render: (_, r) => <><Button type="link" style={{ padding: 0, whiteSpace: 'normal', height: 'auto', textAlign: 'left' }} onClick={() => focus(r)}>{r.title}</Button><div><Typography.Text type="secondary">{r.source}</Typography.Text></div></> },
        { title: '类型', width: 140, render: (_, r) => data.groups[r.group] },
        { title: '关联情况', width: 170, render: (_, r) => <Tag color={STATUS[r.status][1]}>{STATUS[r.status][0]}</Tag> },
        { title: '材料 / 响应', width: 170, render: (_, r) => `${r.link.evidence_ids?.length ?? 0} 项材料 · ${r.link.response ? '已定位响应' : '未定位响应'}` },
        { title: '操作', width: 100, render: (_, r) => <Button size="small" onClick={() => focus(r)}>查看与关联</Button> },
      ]} />
      {params.get('requirement') && !row && <Alert type="warning" message="这条要求已变化或不属于当前包，请从当前清单重新选择" />}
    </Card>
    <Drawer open={!!row} width="94vw" title={row?.title} destroyOnClose onClose={() => focus()}
      footer={<div className="requirement-footer"><Typography.Text type="secondary">仅关联本包当前选材与当前生成版本；最终导出仍需通过本版本审查。</Typography.Text><Space><Button onClick={() => focus()}>取消</Button><Button type="primary" loading={saving} disabled={selectionLocked || (!!filename && (!blockId || !preview))} onClick={save}>保存关联与核对记录</Button></Space></div>}>
      {row && <div className="requirement-columns">
        <div><Typography.Title level={5}>1. 采购要求与原文</Typography.Title><Typography.Text type="secondary">{row.source}</Typography.Text><p className="requirement-original">{row.text}</p>
          {row.document ? <Collapse items={[{ key: row.document, label: '查看本包采购原件内容', children: <SourceDocument id={id} pkgIndex={pkgIndex} source={row.document} /> }]} />
            : <Typography.Text type="secondary">本条来自已解析资格表，当前未提供 Excel 内容预览，请<a href={api.sourceArchiveUrl(id)}>下载采购压缩包</a>核对资格表原件。</Typography.Text>}</div>
        <div><Typography.Title level={5}>2. 证明材料与人工核对</Typography.Title>
          {row.status === 'stale' && <Alert type="warning" showIcon message="材料或生成版本已变化，请重新核对关联" style={{ marginBottom: 12 }} />}
          <Typography.Paragraph type="secondary">以下是本包已选资料，并不表示已满足这条要求。请选择真正支持本条要求的材料。</Typography.Paragraph>
          <Select mode="multiple" aria-label="关联证明材料" placeholder="选择证明材料" value={evidenceIds} onChange={values => { setEvidenceIds(values); setConfirmed(false) }} optionFilterProp="label"
            options={data.evidence.map(e => ({ value: e.id, label: `${KIND[e.kind]} · ${e.title}` }))} />
          {evidenceIds.map(key => { const item = data.evidence.find(e => e.id === key); return <Card size="small" key={key} style={{ marginTop: 12 }} title={item?.title || '已取消选用或已删除的材料'}>
            {item?.attachments.length ? item.attachments.map(a => <div key={a.id}><a href={api.attachmentUrl(a.id)} target="_blank" rel="noreferrer">{a.filename}</a></div>) : <Typography.Text type="secondary">未关联可查看的附件，请核对记录依据。</Typography.Text>}
          </Card> })}
          <Space wrap style={{ marginBlock: 12 }}><Button onClick={() => nav(`${href('workbench', pkgIndex, 'prepare')}&task=${row.evidence_kinds.includes('personnel') ? 'team' : row.evidence_kinds.includes('performances') ? 'performance' : 'registration'}`)}>处理本包准备事项</Button>
            <Button onClick={() => nav(`/kb/${encodeURIComponent(profile)}?tab=${row.evidence_kinds[0] || 'attachments'}&returnTo=${encodeURIComponent(`${href('workbench', pkgIndex, 'prepare')}&requirement=${row.id}`)}`)}>查看企业资料</Button></Space>
          <Input.TextArea aria-label="本条核对依据" rows={4} maxLength={5000} showCount placeholder="记录本条适用性、证据依据或尚需解决的问题" value={note} onChange={e => { setNote(e.target.value); setConfirmed(false) }} />
          <Checkbox style={{ marginTop: 18 }} checked={confirmed} disabled={data.generation_stale && !!filename} onChange={e => setConfirmed(e.target.checked)}>我已核对本条要求与所关联的证据、响应</Checkbox>
          {row.link.actor && <Typography.Paragraph type="secondary">上次记录：{row.link.actor} · {fmtUtc(row.link.updated_at)}</Typography.Paragraph>}
        </div>
        <div><Typography.Title level={5}>3. 文件响应与审阅</Typography.Title>
          {data.generation_stale && <Alert type="warning" message="生成输入已变化，旧文件仅供参考，请更新标书后重新定位" style={{ marginBottom: 12 }} />}
          <Select allowClear aria-label="选择响应文件" placeholder="选择本包当前生成文件" value={filename} onChange={value => { setFilename(value); setBlockId(undefined); setConfirmed(false) }} options={data.files.map(f => ({ value: f, label: f }))} />
          {filename && <Typography.Paragraph style={{ marginTop: 8 }}><a href={api.fileUrl(id, filename)} target="_blank" rel="noreferrer">下载此版 Word 核对原版式</a></Typography.Paragraph>}
          {previewLoading && <Spin />}{previewError && <Alert type="error" message="响应文件无法读取" description={errorMessage(previewError)} />}
          {preview && filename && <DocumentReader document={preview} selected={blockId} onSelect={value => { setBlockId(value); setConfirmed(false) }} />}
          {!data.files.length && <Empty description="尚无本企业、本包的生成版本，可先关联材料" />}
          <Typography.Paragraph type="secondary" style={{ marginTop: 16 }}>本版本审查：{!data.review ? '尚未检查' : data.review_stale ? '已有审查记录已失效，请更新或复查' : data.review.blocked ? '存在需处理问题' : '未发现自动否决项，仍需人工审阅'}。规则审查为整份文件结果，不自动等于本条要求已通过。</Typography.Paragraph>
          <Button onClick={() => nav(href('workbench', pkgIndex, 'review'))}>进入本版本审阅与导出</Button>
        </div>
      </div>}
    </Drawer>
  </>
}
