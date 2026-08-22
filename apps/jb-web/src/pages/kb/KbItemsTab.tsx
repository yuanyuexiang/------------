import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography, Upload, message } from 'antd'
import { PlusOutlined, UploadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { api, Attachment, KbItem } from '../../api'
import { FieldSpec, KindSpec } from './fields'

const DATE_RULE = { pattern: /^\d{4}(-\d{2}(-\d{2})?)?$/, message: '格式 YYYY-MM-DD（可只填到月）' }
const BOOL3 = [{ value: true, label: '是' }, { value: false, label: '否' }]

/** 键值对 ↔ "k=v" 多行文本（产品参数表） */
const kvToText = (o: Record<string, string> | undefined) => Object.entries(o ?? {}).map(([k, v]) => `${k}=${v}`).join('\n')
const textToKv = (t: string | undefined) => Object.fromEntries(
  (t ?? '').split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
    const i = l.indexOf('=')
    return i < 0 ? [l, ''] : [l.slice(0, i).trim(), l.slice(i + 1).trim()]
  }))

function renderCell(f: FieldSpec, v: unknown) {
  switch (f.type) {
    case 'bool3':
      return v === true ? <Tag color="green">是</Tag> : v === false ? <Tag>否</Tag> : <Tag color="orange">未录入</Tag>
    case 'tags':
      return (v as string[] | undefined)?.map((x) => <Tag key={x}>{x}</Tag>)
    case 'kv': {
      const o = (v ?? {}) as Record<string, string>
      const n = Object.keys(o).length
      return <Tooltip title={<pre style={{ margin: 0 }}>{kvToText(o)}</pre>}>{n} 项</Tooltip>
    }
    case 'textarea':
      return <Typography.Paragraph ellipsis={{ rows: 2, tooltip: String(v ?? '') }} style={{ margin: 0 }}>{String(v ?? '')}</Typography.Paragraph>
    case 'select':
      if (f.key === 'status') return v === 'draft' ? <Tag color="orange">待审核</Tag> : <Tag color="green">已审核</Tag>
      return String(v ?? '')
    default:
      return v === null || v === undefined || v === '' ? <Typography.Text type="secondary">—</Typography.Text> : String(v)
  }
}

function FieldInput({ f }: { f: FieldSpec }) {
  switch (f.type) {
    case 'textarea': return <Input.TextArea rows={f.key === 'text' ? 8 : 4} />
    case 'number': return <InputNumber style={{ width: '100%' }} />
    case 'date': return <Input placeholder="YYYY-MM-DD" />
    case 'bool3': return <Select allowClear placeholder="未录入" options={BOOL3} />
    case 'tags': return <Select mode="tags" tokenSeparators={[',', '，', ' ']} options={f.options?.map((o) => ({ value: o }))} />
    case 'kv': return <Input.TextArea rows={8} placeholder={'参数名=值\n例：CPU=2*32Core@2.6GHz'} />
    case 'select': return <Select allowClear={f.key !== 'status'} options={f.options?.map((o) => ({ value: o, label: o === 'approved' ? '已审核' : o === 'draft' ? '待审核' : o }))} />
    default: return <Input />
  }
}

/** 某类知识库条目的通用管理页：表格 + 新增/编辑弹窗 + 删除 + 附件挂载。字段由 KindSpec 驱动。 */
export default function KbItemsTab({ company, spec }: { company: string; spec: KindSpec }) {
  const qc = useQueryClient()
  const key = ['kb', company, spec.kind]
  const { data: items = [], isLoading } = useQuery({ queryKey: key, queryFn: () => api.kbList<KbItem>(company, spec.kind) })
  const { data: attachments = [] } = useQuery({ queryKey: ['attachments', company], queryFn: () => api.attachments(company) })
  const [editing, setEditing] = useState<KbItem | null | 'new'>(null)
  const [form] = Form.useForm()
  const invalidate = () => {
    for (const k of [key, ['profiles'], ['profile', company], ['expiry', company]]) qc.invalidateQueries({ queryKey: k })
  }

  const save = useMutation({
    mutationFn: (payload: Partial<KbItem>) => editing && editing !== 'new'
      ? api.kbUpdate(company, spec.kind, editing.id, payload)
      : api.kbCreate(company, spec.kind, payload),
    onSuccess: () => { message.success('已保存'); setEditing(null); invalidate() },
    onError: (e) => message.error(String(e)),
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.kbDelete(company, spec.kind, id),
    onSuccess: () => { message.success('已删除'); invalidate() },
    onError: (e) => message.error(String(e)),
  })

  const open = (item: KbItem | 'new') => {
    setEditing(item)
    const init: Record<string, unknown> = item === 'new' ? { status: 'approved' } : { ...item }
    for (const f of spec.fields) if (f.type === 'kv') init[f.key] = kvToText(init[f.key] as Record<string, string>)
    form.resetFields()
    form.setFieldsValue(init)
  }
  const submit = async () => {
    const v = await form.validateFields()
    for (const f of spec.fields) {
      if (f.type === 'kv') v[f.key] = textToKv(v[f.key])
      if (f.key === 'approved') v[f.key] = v[f.key] ?? false
    }
    save.mutate(v)
  }
  const uploadInForm = async (file: File) => {
    try {
      const a = await api.uploadAttachment(company, spec.attachmentKind, file)
      qc.invalidateQueries({ queryKey: ['attachments', company] })
      form.setFieldValue('attachments', Array.from(new Set([...(form.getFieldValue('attachments') ?? []), a.id])))
      message.success(`已上传 ${a.filename}`)
    } catch (e) { message.error(String(e)) }
    return false
  }
  const attName = (id: string) => attachments.find((a: Attachment) => a.id === id)

  const columns: ColumnsType<KbItem> = [
    ...spec.fields.filter((f) => f.width).map((f) => ({
      title: f.label, dataIndex: f.key, width: f.width, ellipsis: f.type !== 'tags' && f.type !== 'textarea',
      render: (v: unknown) => renderCell(f, v),
    })),
    { title: '附件', dataIndex: 'attachments', width: 110, render: (ids: string[] = []) => ids.map((id) => {
      const a = attName(id)
      return a ? <a key={id} href={api.attachmentUrl(id)} target="_blank" rel="noreferrer" style={{ marginRight: 6 }}>{a.filename}</a> : null
    }) },
    { title: '操作', width: 90, render: (_, r) => (
      <Space size="small">
        <Button size="small" type="link" onClick={() => open(r)}>编辑</Button>
        <Popconfirm title="确认删除？" onConfirm={() => remove.mutate(r.id)}><Button size="small" type="link" danger>删除</Button></Popconfirm>
      </Space>
    ) },
  ]

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {spec.note && <Alert type="info" showIcon message={spec.note} />}
      <Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => open('new')}>新增{spec.title}</Button>
        <Typography.Text type="secondary">共 {items.length} 条</Typography.Text>
      </Space>
      <Table<KbItem> size="small" rowKey="id" loading={isLoading} dataSource={items} columns={columns} tableLayout="fixed"
        scroll={{ x: columns.reduce((n, c) => n + Number(c.width ?? 0), 0) }} pagination={items.length > 20 ? { pageSize: 20 } : false} />

      <Modal open={editing !== null} title={editing === 'new' ? `新增${spec.title}` : `编辑${spec.title}`} width={720}
        onCancel={() => setEditing(null)} onOk={submit} confirmLoading={save.isPending} destroyOnClose>
        <Form form={form} layout="vertical" style={{ maxHeight: '65vh', overflowY: 'auto', paddingRight: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', columnGap: 16 }}>
            {spec.fields.map((f) => {
              const wide = f.type === 'textarea' || f.type === 'kv' || f.type === 'tags'
              return (
                <Form.Item key={f.key} name={f.key} label={f.label} extra={f.hint} style={wide ? { gridColumn: '1 / -1' } : undefined}
                  rules={[...(f.required ? [{ required: true, message: `请填写${f.label}` }] : []), ...(f.type === 'date' ? [DATE_RULE] : [])]}>
                  <FieldInput f={f} />
                </Form.Item>
              )
            })}
            <Form.Item name="attachments" label="扫描件附件" style={{ gridColumn: '1 / -1' }}
              extra="可从已上传附件中选择，或直接上传（自动归入本类）">
              <Select mode="multiple" placeholder="选择附件" optionFilterProp="label"
                options={attachments.map((a: Attachment) => ({ value: a.id, label: `${a.filename}（${a.kind}）` }))} />
            </Form.Item>
            <Upload beforeUpload={uploadInForm} showUploadList={false} multiple>
              <Button icon={<UploadOutlined />}>上传新附件</Button>
            </Upload>
          </div>
        </Form>
      </Modal>
    </Space>
  )
}
