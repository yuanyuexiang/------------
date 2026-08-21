import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Alert, Button, Card, Collapse, Descriptions, Form, Input, InputNumber, Select, Space, Spin, Switch, Table, Tabs, Tag, Typography, message,
} from 'antd'
import { api, KeyTerms, PackageTRM, TRM } from '../api'

const { Text } = Typography

/** 未抽到（None）的字段高亮，提醒人工补录；LLM 填充的字段打标。 */
function Missing({ v }: { v: unknown }) {
  return v === null || v === undefined || v === '' ? <Tag color="orange">未抽到，待确认</Tag> : <>{String(v)}</>
}

function KeyTermsForm({ kt, onChange }: { kt: KeyTerms; onChange: (k: KeyTerms) => void }) {
  const set = <K extends keyof KeyTerms>(k: K, v: KeyTerms[K]) => onChange({ ...kt, [k]: v })
  const llm = (k: string) => kt.llm_filled.includes(k) ? <Tag color="purple">LLM 兜底</Tag> : null
  return (
    <Form layout="vertical" style={{ maxWidth: 720 }}>
      <Form.Item label={<>投标有效期（日）{llm('validity_days')}<Text type="secondary"> 条款 {kt.validity_clause}</Text></>}>
        <InputNumber value={kt.validity_days ?? undefined} onChange={(v) => set('validity_days', v ?? null)} min={1} />
        {kt.validity_days === null && <Tag color="orange" style={{ marginLeft: 8 }}>未抽到</Tag>}
      </Form.Item>
      <Form.Item label={<>保证金模式 {llm('deposit_mode')}<Text type="secondary"> 条款 {kt.deposit_clause}</Text></>}>
        <Select value={kt.deposit_mode ?? undefined} onChange={(v) => set('deposit_mode', v)} allowClear style={{ width: 240 }}
          options={['none', '诚信担保', '年度保证金', '按包保证金'].map((v) => ({ value: v, label: v === 'none' ? '不要求保证金' : v }))} />
      </Form.Item>
      <Space size="large">
        <Form.Item label="整体电子签章"><Switch checked={!!kt.sign_whole_doc} onChange={(v) => set('sign_whole_doc', v)} /></Form.Item>
        <Form.Item label="不接收纸质文件"><Switch checked={!!kt.paperless} onChange={(v) => set('paperless', v)} /></Form.Item>
        <Form.Item label="电子招标投标"><Switch checked={!!kt.electronic} onChange={(v) => set('electronic', v)} /></Form.Item>
      </Space>
      <Form.Item label="澄清截止时间"><Input value={kt.clarify_deadline ?? ''} onChange={(e) => set('clarify_deadline', e.target.value || null)} /></Form.Item>
      <Form.Item label={`最高限价说明（条款 ${kt.max_price_clause || '-'}）`}><Input.TextArea value={kt.max_price_note} onChange={(e) => set('max_price_note', e.target.value)} autoSize /></Form.Item>
      <Form.Item label="增值税说明"><Input.TextArea value={kt.vat_note} onChange={(e) => set('vat_note', e.target.value)} autoSize /></Form.Item>
    </Form>
  )
}

function PackagePanel({ pkg, onChange }: { pkg: PackageTRM; onChange: (p: PackageTRM) => void }) {
  const sr = pkg.scoring_ref
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Descriptions size="small" bordered column={3}>
        <Descriptions.Item label="项目名称" span={3}><Missing v={pkg.project_name} /></Descriptions.Item>
        <Descriptions.Item label="项目单位"><Missing v={pkg.project_unit} /></Descriptions.Item>
        <Descriptions.Item label="预算（元）"><Missing v={pkg.budget_yuan} /></Descriptions.Item>
        <Descriptions.Item label="最高限价"><Missing v={pkg.max_price} /></Descriptions.Item>
        <Descriptions.Item label="工期（日）"><Missing v={pkg.duration_days} /></Descriptions.Item>
        <Descriptions.Item label="报价方式"><Missing v={pkg.price_mode} /></Descriptions.Item>
        <Descriptions.Item label="联合体">{pkg.allow_consortium === null ? <Missing v={null} /> : pkg.allow_consortium ? '允许' : '不允许'}</Descriptions.Item>
        <Descriptions.Item label="评审办法" span={3}>
          {sr.price_method || '-'}（C={sr.benchmark_c ?? '?'}）｜商务 {sr.biz_template || '-'} {sr.weight_biz ?? '?'}%｜技术 {sr.tech_template || '-'} {sr.weight_tech ?? '?'}%｜价格 {sr.weight_price ?? '?'}%
        </Descriptions.Item>
      </Descriptions>
      <Collapse items={[
        { key: 'q', label: `资格要求（${pkg.qualification.length}）`, children: (
          <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={pkg.qualification}
            columns={[
              { title: '业绩要求', dataIndex: 'performance_req', render: (v, r) => <>{v || <Missing v="" />}{r.llm_extracted && <Tag color="purple" style={{ marginLeft: 6 }}>LLM</Tag>}</> },
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
              { title: '交货', dataIndex: 'deliver_date', width: 110 }, { title: '规范书ID', dataIndex: 'spec_id', width: 190 },
            ]} />
        ) },
        ...pkg.spec_docs.map((sd, si) => ({
          key: `s${si}`,
          label: <>技术规范书 {sd.spec_id || sd.title}（参数 {sd.param_rows.length} 行，★{sd.param_rows.filter((r) => r.star).length}）{!sd.structured && <Tag style={{ marginLeft: 8 }}>非结构化·附件逐项响应</Tag>}</>,
          children: (
            <Table size="small" rowKey="row" pagination={{ pageSize: 20 }} dataSource={sd.param_rows}
              columns={[
                { title: '#', dataIndex: 'row', width: 50 },
                { title: '参数名称', dataIndex: 'name', width: 140 },
                { title: '项目需求值', dataIndex: 'required', render: (v: string, r) => <>{r.star && <Tag color="red">★</Tag>}{v}</> },
                { title: '投标人保证值（S3 自动填）', dataIndex: 'response', width: 200, render: (v: string | null, r) => (
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

/** TRM 确认页：机器解析结果逐项核对/修改 → 提交人工确认版（下游一律以确认版为准）。 */
export default function TrmConfirmPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const { data, isLoading, error } = useQuery({ queryKey: ['trm', id], queryFn: () => api.trm(id, true) })
  const [trm, setTrm] = useState<TRM | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => { if (data) setTrm(data) }, [data])

  if (isLoading || !trm) return <Spin />
  if (error) return <Alert type="error" message={String(error)} />

  const save = async () => {
    setSaving(true)
    try {
      await api.confirmTrm(id, trm)
      message.success('确认版已保存，下游流程将以此为准')
      nav('/')
    } catch (e) { message.error(String(e)) } finally { setSaving(false) }
  }
  const setPkg = (i: number, p: PackageTRM) => setTrm({ ...trm, packages: trm.packages.map((x, k) => k === i ? p : x) })

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <Text strong>{trm.batch_name || trm.source_zip}</Text>
          <Tag>{trm.batch_no || '批次号未抽到'}</Tag>
          <Tag color="blue">{trm.terminology}体系</Tag>
          <Text type="secondary">前附表 {trm.prenotice.length} 条 · 否决 {trm.rejection_rules.length} 条 · 提交项 {trm.submission_table.length} · 标包 {trm.packages.length} · 评分模板 {trm.scoring_templates.length}</Text>
        </Space>
        {trm.warnings.length > 0 && <Alert style={{ marginTop: 8 }} type="warning" message={trm.warnings.join('；')} />}
      </Card>
      <Tabs items={[
        { key: 'kt', label: '关键条件', children: <KeyTermsForm kt={trm.key_terms} onChange={(k) => setTrm({ ...trm, key_terms: k })} /> },
        { key: 'pk', label: `标包（${trm.packages.length}）`, children: (
          <Tabs tabPosition="left" items={trm.packages.map((p, i) => ({
            key: String(i), label: `${p.sub_no} ${p.sub_name} ${p.pkg_no}`.trim() || `包 ${i + 1}`,
            children: <PackagePanel pkg={p} onChange={(np) => setPkg(i, np)} />,
          }))} />
        ) },
        { key: 'rj', label: `否决规则（${trm.rejection_rules.length}）`, children: (
          <Table size="small" rowKey={(_, i) => String(i)} pagination={{ pageSize: 15 }} dataSource={trm.rejection_rules}
            columns={[{ title: '类别', dataIndex: 'category', width: 110 }, { title: '方面', dataIndex: 'aspect', width: 110 }, { title: '否决情形', dataIndex: 'text' }]} />
        ) },
        { key: 'sb', label: `提交方式表（${trm.submission_table.length}）`, children: (
          <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={trm.submission_table}
            columns={[
              { title: '文件', dataIndex: 'section', width: 160 }, { title: '序号', dataIndex: 'seq', width: 70 },
              { title: '内容', dataIndex: 'item' },
              { title: '渠道', dataIndex: 'channels', width: 200, render: (c: string[]) => c.map((x) => <Tag key={x}>{x}</Tag>) },
              { title: '投标工具端口', dataIndex: 'port', width: 240 },
            ]} />
        ) },
        { key: 'pn', label: `前附表（${trm.prenotice.length}）`, children: (
          <Table size="small" rowKey={(_, i) => String(i)} pagination={{ pageSize: 20 }} dataSource={trm.prenotice}
            columns={[{ title: '条款', dataIndex: 'clause_no', width: 100 }, { title: '名称', dataIndex: 'name', width: 200 }, { title: '编列内容', dataIndex: 'content' }]} />
        ) },
      ]} />
      <Card size="small">
        <Space>
          <Button type="primary" loading={saving} onClick={save}>确认并保存为人工确认版</Button>
          <Button onClick={() => nav('/')}>返回</Button>
          <Text type="secondary">确认后下游（资格自检/生成/审查）一律使用确认版</Text>
        </Space>
      </Card>
    </Space>
  )
}
