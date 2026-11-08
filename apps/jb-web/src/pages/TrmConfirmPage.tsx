import { errorMessage, purchaseWarningLabel } from '../uiLabels'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useBeforeUnload, useBlocker, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useProjectWorkspace } from '../components/ProjectWorkspace'
import {
  Alert, Button, Card, Collapse, Drawer, Descriptions, Form, Input, InputNumber, Modal, Select, Space, Spin, Table, Tabs, Tag, Typography, message,
} from 'antd'
import { api, KeyTerms, PackageTRM, TRM } from '../api'
import SourceDocument from '../components/DocumentReader'

const { Text } = Typography

/** 未识别（None）的字段高亮，提醒人工补录；LLM 填充的字段打标。 */
function Missing({ v }: { v: unknown }) {
  return v === null || v === undefined || v === '' ? <Tag color="orange">未识别，请核对</Tag> : <>{String(v)}</>
}

function KeyTermsForm({ kt, onChange }: { kt: KeyTerms; onChange: (k: KeyTerms) => void }) {
  const set = <K extends keyof KeyTerms>(k: K, v: KeyTerms[K]) => onChange({ ...kt, [k]: v })
  const llm = (k: string) => kt.llm_filled.includes(k) ? <Tag color="purple">AI 提取，请核对</Tag> : null
  return (
    <Form layout="vertical" className="key-terms-form">
      <Form.Item label={<>投标有效期（日）{llm('validity_days')}<Text type="secondary"> 条款 {kt.validity_clause}</Text></>}>
        <InputNumber value={kt.validity_days ?? undefined} onChange={(v) => set('validity_days', v ?? null)} min={1} />
        {kt.validity_days === null && <Tag color="orange" style={{ marginLeft: 8 }}>未识别</Tag>}
      </Form.Item>
      <Form.Item label={<>保证金要求 {llm('deposit_mode')}<Text type="secondary"> 条款 {kt.deposit_clause}</Text></>}>
        <Select value={kt.deposit_mode ?? undefined} onChange={(v) => set('deposit_mode', v)} allowClear style={{ width: 240 }}
          options={['none', '诚信担保', '年度保证金', '按包保证金'].map((v) => ({ value: v, label: v === 'none' ? '不要求保证金' : v }))} />
      </Form.Item>
      <Space size="large" wrap className="key-terms-switches">
        {([['sign_whole_doc', '整份文件统一电子签章'], ['paperless', '仅提交电子文件（不接收纸质文件）'], ['electronic', '通过电子平台投标']] as const).map(([key, label]) =>
          <Form.Item key={key} label={label}><Select style={{ width: 170 }} value={kt[key] === null ? 'unknown' : String(kt[key])}
            onChange={value => set(key, value === 'unknown' ? null : value === 'true')}
            options={[{ value: 'unknown', label: '未识别，请核对' }, { value: 'true', label: '是' }, { value: 'false', label: '否' }]} /></Form.Item>)}
      </Space>
      <Form.Item label="采购问题澄清截止时间"><Input value={kt.clarify_deadline ?? ''} onChange={(e) => set('clarify_deadline', e.target.value || null)} /></Form.Item>
      <Form.Item label={`最高限价说明（条款 ${kt.max_price_clause || '-'}）`}><Input.TextArea value={kt.max_price_note} onChange={(e) => set('max_price_note', e.target.value)} autoSize /></Form.Item>
      <Form.Item label="增值税要求"><Input.TextArea value={kt.vat_note} onChange={(e) => set('vat_note', e.target.value)} autoSize /></Form.Item>
    </Form>
  )
}

function PackagePanel({ pkg, onChange }: { pkg: PackageTRM; onChange: (p: PackageTRM) => void }) {
  const sr = pkg.scoring_ref
  return (
    <Space className="workspace-page" direction="vertical" style={{ width: '100%' }} size="middle">
      <Descriptions size="small" bordered column={3}>
        <Descriptions.Item label="项目名称" span={3}><Missing v={pkg.project_name} /></Descriptions.Item>
        <Descriptions.Item label="项目单位"><Missing v={pkg.project_unit} /></Descriptions.Item>
        <Descriptions.Item label="预算（元）"><Missing v={pkg.budget_yuan} /></Descriptions.Item>
        <Descriptions.Item label="最高限价"><Missing v={pkg.max_price} /></Descriptions.Item>
        <Descriptions.Item label="工期（日）"><Missing v={pkg.duration_days} /></Descriptions.Item>
        <Descriptions.Item label="报价方式"><Missing v={pkg.price_mode} /></Descriptions.Item>
        <Descriptions.Item label="联合体">{pkg.allow_consortium === null ? <Missing v={null} /> : pkg.allow_consortium ? '允许' : '不允许'}</Descriptions.Item>
        <Descriptions.Item label="评审办法" span={3}>
          {sr.price_method || '-'}（价格计算系数：{sr.benchmark_c ?? '未识别'}）｜商务 {sr.biz_template || '-'} {sr.weight_biz ?? '?'}%｜技术 {sr.tech_template || '-'} {sr.weight_tech ?? '?'}%｜价格 {sr.weight_price ?? '?'}%
        </Descriptions.Item>
      </Descriptions>
      <Collapse items={[
        { key: 'q', label: `资格要求（${pkg.qualification.length}）`, children: (
          <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={pkg.qualification}
            columns={[
              { title: '业绩要求', dataIndex: 'performance_req', render: (v, r) => <>{v || <Missing v="" />}{r.llm_extracted && <Tag color="purple" style={{ marginLeft: 6 }}>AI 提取</Tag>}</> },
              { title: '年限', dataIndex: 'perf_years', width: 70, render: (v) => <Missing v={v} /> },
              { title: '范围', dataIndex: 'perf_scope' },
              { title: '试验报告要求', dataIndex: 'test_report_req' },
              { title: '其他', dataIndex: 'other_reqs', render: (o: Record<string, string>) => Object.entries(o).map(([k, v]) => <div key={k}><Text type="secondary">{k}：</Text>{v}</div>) },
            ]} />
        ) },
        { key: 'm', label: `货物清单（${pkg.materials.length} 行）`, children: (
          <Table size="small" rowKey={(_, i) => String(i)} pagination={{ pageSize: 10 }} dataSource={pkg.materials}
            columns={[
              { title: '项目', dataIndex: 'project' }, { title: '物资描述', dataIndex: 'desc' },
              { title: '数量', dataIndex: 'qty', width: 70 }, { title: '单位', dataIndex: 'unit', width: 60 },
              { title: '交货', dataIndex: 'deliver_date', width: 110 }, { title: '规范书编号', dataIndex: 'spec_id', width: 190 },
            ]} />
        ) },
        ...pkg.spec_docs.map((sd, si) => ({
          key: `s${si}`,
          label: <>技术规范书 {sd.spec_id || sd.title}（参数 {sd.param_rows.length} 行，重点要求 {sd.param_rows.filter((r) => r.star).length} 项）{!sd.structured && <Tag style={{ marginLeft: 8 }}>按附件逐项响应</Tag>}</>,
          children: (
            <Table size="small" rowKey="row" pagination={{ pageSize: 20 }} dataSource={sd.param_rows}
              columns={[
                { title: '序号', dataIndex: 'row', width: 50 },
                { title: '参数名称', dataIndex: 'name', width: 140 },
                { title: '采购方要求的参数', dataIndex: 'required', render: (v: string, r) => <>{r.star && <Tag color="red">★</Tag>}{v}</> },
                { title: '我方提供的参数（生成标书时填写）', dataIndex: 'response', width: 200, render: (v: string | null, r) => (
                  <Input size="small" value={v ?? ''} placeholder="待填" onChange={(e) => {
                    const rows = sd.param_rows.map((x) => x.row === r.row ? { ...x, response: e.target.value || null } : x)
                    const docs = pkg.spec_docs.map((d, i) => i === si ? { ...d, param_rows: rows } : d)
                    onChange({ ...pkg, spec_docs: docs })
                  }} />
                ) },
              ]} />
          ),
        })),
      ]} />
    </Space>
  )
}

/** 采购信息核对页：逐项核对解析结果，保存后用于后续投标准备。 */
export default function TrmConfirmPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { href, pkgIndex, setPkgIndex } = useProjectWorkspace()
  const [sourceOpen, setSourceOpen] = useState(false)
  const [source, setSource] = useState('main')
  useEffect(() => { setSource('main') }, [pkgIndex])
  const { data, isLoading, error } = useQuery({ queryKey: ['trm', id], queryFn: () => api.trm(id, true) })
  const [trm, setTrm] = useState<TRM | null>(null)
  const [saving, setSaving] = useState(false)
  const saved = useRef('')
  const dirty = !!trm && JSON.stringify(trm) !== saved.current
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && !saving && currentLocation.pathname !== nextLocation.pathname)
  useBeforeUnload(useCallback((event: BeforeUnloadEvent) => {
    if (dirty) { event.preventDefault(); event.returnValue = '' }
  }, [dirty]))
  useEffect(() => {
    if (blocker.state !== 'blocked') return
    const dialog = Modal.confirm({ title: '采购信息尚未保存', content: '离开后将丢弃本次修改。请先保存，或确认放弃修改。',
      okText: '放弃修改并离开', cancelText: '继续核对', onOk: () => blocker.proceed(), onCancel: () => blocker.reset() })
    return () => dialog.destroy()
  }, [blocker])
  useEffect(() => { if (data) { saved.current = JSON.stringify(data); setTrm(data) } }, [data])

  if (error) return <Alert type="error" message={errorMessage(error)} />
  if (isLoading || !trm) return <Spin />

  const save = async (continueToQualification = false) => {
    setSaving(true)
    try {
      await api.confirmTrm(id, trm)
      saved.current = JSON.stringify(trm)
      qc.setQueryData(['trm', id], trm)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['project-detail', id] }),
        qc.invalidateQueries({ queryKey: ['projects'] }),
        qc.invalidateQueries({ queryKey: ['qualification', id] }),
        qc.invalidateQueries({ queryKey: ['workflow', id] }),
        qc.invalidateQueries({ queryKey: ['preparation', id] }),
      ])
      message.success('采购信息已保存，将用于检查投标资格、标书生成和审查')
      if (continueToQualification) nav(href('workbench', pkgIndex, 'prepare'))
    } catch (e) { message.error(errorMessage(e)) } finally { setSaving(false) }
  }
  const setPkg = (i: number, p: PackageTRM) => setTrm({ ...trm, packages: trm.packages.map((x, k) => k === i ? p : x) })

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}><Text type="secondary">核对系统提取的信息，确认后开始准备文件。</Text><Button onClick={() => setSourceOpen(true)}>查看采购原文</Button></Space>
      {trm.warnings.length > 0 && <Collapse items={[{ key: 'warnings', label: `有 ${trm.warnings.length} 条提取提醒，展开核对`, children: <ul>{trm.warnings.map((warning, i) => <li key={i}>{purchaseWarningLabel(warning)}</li>)}</ul> }]} />}
      <div><Tabs items={[
        { key: 'kt', label: '关键投标要求', children: <KeyTermsForm kt={trm.key_terms} onChange={(k) => setTrm({ ...trm, key_terms: k })} /> },
        { key: 'pk', label: `采购包（${trm.packages.length}）`, children: (
          <Tabs className="package-tabs" tabPosition="top" activeKey={String(pkgIndex)} onChange={key => setPkgIndex(Number(key))} items={trm.packages.map((p, i) => ({
            key: String(i), label: `${p.sub_no} ${p.sub_name} ${p.pkg_no}`.trim() || `包 ${i + 1}`,
            children: <PackagePanel pkg={p} onChange={(np) => setPkg(i, np)} />,
          }))} />
        ) },
        { key: 'rj', label: `可能导致投标无效的情形（${trm.rejection_rules.length}）`, children: (
          <Table size="small" rowKey={(_, i) => String(i)} pagination={{ pageSize: 15 }} dataSource={trm.rejection_rules}
            columns={[{ title: '类别', dataIndex: 'category', width: 110 }, { title: '方面', dataIndex: 'aspect', width: 110 }, { title: '具体情形', dataIndex: 'text' }]} />
        ) },
        { key: 'sb', label: `投标文件怎么提交（${trm.submission_table.length}）`, children: (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text type="secondary">查看需要提交哪些材料、通过什么渠道提交，以及在投标工具中的上传位置。</Text>
            <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={trm.submission_table}
              locale={{ emptyText: '未识别到文件提交要求，请对照采购文件核对。' }}
            columns={[
              { title: '文件类别', dataIndex: 'section', width: 160 }, { title: '序号', dataIndex: 'seq', width: 70 },
              { title: '提交材料', dataIndex: 'item' },
              { title: '提交渠道', dataIndex: 'channels', width: 200, render: (c: string[]) => c.map((x) => <Tag key={x}>{x}</Tag>) },
              { title: '投标工具上传位置', dataIndex: 'port', width: 240 },
            ]} />
          </Space>
        ) },
        { key: 'pn', label: `采购重要事项（${trm.prenotice.length}）`, children: (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text type="secondary">汇总采购文件中的重要事项，可按条款编号对照原文。</Text>
            <Table size="small" rowKey={(_, i) => String(i)} pagination={{ pageSize: 20 }} dataSource={trm.prenotice}
              columns={[{ title: '条款编号', dataIndex: 'clause_no', width: 100 }, { title: '事项', dataIndex: 'name', width: 200 }, { title: '具体要求', dataIndex: 'content' }]} />
          </Space>
        ) },
      ]} /></div><Drawer title="采购原文" width="min(900px, 96vw)" open={sourceOpen} onClose={() => setSourceOpen(false)}>
        <Select aria-label="选择采购原件" style={{ width: '100%', marginBottom: 16 }} value={source} onChange={setSource}
          options={[{ value: 'main', label: '采购主文件' }, ...(trm.packages[pkgIndex]?.spec_docs ?? []).map((spec, index) => ({ value: `spec:${index}`, label: spec.title || spec.spec_id || spec.source }))]} />
        <SourceDocument id={id} pkgIndex={pkgIndex} source={source} />
      </Drawer>
      <Card size="small" className="confirmation-actions workflow-footer">
        <Space wrap>
          <Button type="primary" loading={saving} onClick={() => save(true)}>确认并准备投标文件</Button>
          <Button disabled={saving} onClick={() => save()}>仅保存，留在本页</Button>
          <Text type="secondary">请对照采购原件核对；保存后的信息将用于检查投标资格、标书生成和审查</Text>
        </Space>
      </Card>
    </Space>
  )
}
