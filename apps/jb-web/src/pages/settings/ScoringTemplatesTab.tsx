import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Checkbox, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Typography, Upload, message } from 'antd'
import { PlusOutlined, UploadOutlined } from '@ant-design/icons'
import { api, fmtUtc, ScoringTemplateFull, ScoringTemplateSummary } from '../../api'

const KIND_CN: Record<string, string> = { tech: '技术', biz: '商务', price: '价格', other: '其他' }
const ORIGIN_CN: Record<string, string> = { parsed: '解析入库', upload: '上传', manual: '手工' }
type Item = ScoringTemplateFull['items'][number]

/** 评分模板库：解析招标文件时自动入库；可上传 xlsx / 手工录入；按名称被各包评审办法引用，模拟评分缺细则时兜底。 */
export default function ScoringTemplatesTab() {
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: ['scoring-templates'], queryFn: api.scoringTemplates })
  const [editing, setEditing] = useState<ScoringTemplateFull | 'new' | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [overwrite, setOverwrite] = useState(false)
  const [form] = Form.useForm()
  const refresh = () => qc.invalidateQueries({ queryKey: ['scoring-templates'] })

  const open = async (row: ScoringTemplateSummary | 'new') => {
    if (row === 'new') {
      setEditing('new'); setItems([{ group: '', element: '', content: '', score_min: null, score_max: null }])
      form.setFieldsValue({ name: '', kind: 'tech', note: '' })
      return
    }
    const full = await api.scoringTemplate(row.id)
    setEditing(full); setItems(full.items)
    form.setFieldsValue({ name: full.name, kind: full.kind, note: full.note })
  }
  const save = useMutation({
    mutationFn: async () => {
      const v = await form.validateFields()
      const body = { ...v, items: items.filter((i) => i.element || i.content) }
      return editing === 'new' ? api.createScoringTemplate(body) : api.updateScoringTemplate((editing as ScoringTemplateFull).id, body)
    },
    onSuccess: () => { message.success('已保存'); setEditing(null); refresh() },
    onError: (e) => message.error(String(e)),
  })
  const upload = async (file: File) => {
    try { const t = await api.uploadScoringTemplate(file, overwrite); message.success(`已入库：${t.name}（${t.item_count} 项）`); refresh() } catch (e) { message.error(String(e)) }
    return false
  }
  const setItem = (i: number, patch: Partial<Item>) => setItems(items.map((x, k) => k === i ? { ...x, ...patch } : x))

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="info" showIcon message="解析招标文件包时，带评审要素的评分细则自动入库（不覆盖已维护的同名模板）。各包评审办法按模板名称引用；TRM 里只有模板名、没有细则时，模拟评分按名称到这里兜底——只按名称匹配，不按类别乱配。" />
      <Space wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => open('new')}>手工新建</Button>
        <Upload accept=".xlsx,.xls" beforeUpload={upload} showUploadList={false}><Button icon={<UploadOutlined />}>上传评分细则 xlsx</Button></Upload>
        <Checkbox checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)}>同名覆盖</Checkbox>
        <Typography.Text type="secondary">xlsx 格式同国网模板库：首行模板名，次行表头（评审要素 | 评审内容），要素内嵌分值区间如"项目团队（12-20 分）"</Typography.Text>
      </Space>
      <Table<ScoringTemplateSummary> size="small" rowKey="id" loading={isLoading} dataSource={data} pagination={false}
        columns={[
          { title: '模板名称', dataIndex: 'name', render: (v, r) => <a onClick={() => open(r)}>{v}</a> },
          { title: '类别', dataIndex: 'kind', width: 80, render: (k: string) => <Tag color={k === 'tech' ? 'blue' : k === 'biz' ? 'green' : 'default'}>{KIND_CN[k] ?? k}</Tag> },
          { title: '要素数', dataIndex: 'item_count', width: 80 },
          { title: '来源', dataIndex: 'origin', width: 90, render: (o: string) => ORIGIN_CN[o] ?? o },
          { title: '出处', dataIndex: 'source', ellipsis: true },
          { title: '更新', dataIndex: 'updated_at', width: 200, render: (v: string, r) => `${fmtUtc(v)}${r.updated_by ? ` · ${r.updated_by}` : ''}` },
          { title: '操作', width: 120, render: (_, r) => (
            <Space size="small">
              <Button size="small" type="link" onClick={() => open(r)}>编辑</Button>
              <Popconfirm title="删除模板？" onConfirm={async () => { await api.deleteScoringTemplate(r.id); refresh() }}><Button size="small" type="link" danger>删除</Button></Popconfirm>
            </Space>
          ) },
        ]} />

      <Modal open={editing !== null} width={960} title={editing === 'new' ? '新建评分模板' : '编辑评分模板'} onCancel={() => setEditing(null)} onOk={() => save.mutate()} confirmLoading={save.isPending} destroyOnClose>
        <Form form={form} layout="inline" style={{ marginBottom: 12 }}>
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '必填' }]} style={{ flex: 1 }}><Input placeholder="如 FWSW01：服务类通用商务详评细则" style={{ width: 360 }} /></Form.Item>
          <Form.Item name="kind" label="类别"><Select style={{ width: 100 }} options={Object.entries(KIND_CN).map(([v, l]) => ({ value: v, label: l }))} /></Form.Item>
          <Form.Item name="note" label="备注"><Input style={{ width: 200 }} /></Form.Item>
        </Form>
        <Table<Item> size="small" rowKey={(_, i) => String(i)} dataSource={items} pagination={false} scroll={{ y: 380 }}
          columns={[
            { title: '分组', dataIndex: 'group', width: 150, render: (v, _, i) => <Input size="small" value={v} onChange={(e) => setItem(i, { group: e.target.value })} /> },
            { title: '评审要素', dataIndex: 'element', width: 220, render: (v, _, i) => <Input size="small" value={v} onChange={(e) => setItem(i, { element: e.target.value })} placeholder="如 项目团队（12-20 分）" /> },
            { title: '评审内容 / 档位标准', dataIndex: 'content', render: (v, _, i) => <Input.TextArea size="small" autoSize={{ minRows: 1, maxRows: 4 }} value={v} onChange={(e) => setItem(i, { content: e.target.value })} /> },
            { title: '最低', dataIndex: 'score_min', width: 70, render: (v, _, i) => <Input size="small" value={v ?? ''} onChange={(e) => setItem(i, { score_min: e.target.value === '' ? null : Number(e.target.value) })} /> },
            { title: '最高', dataIndex: 'score_max', width: 70, render: (v, _, i) => <Input size="small" value={v ?? ''} onChange={(e) => setItem(i, { score_max: e.target.value === '' ? null : Number(e.target.value) })} /> },
            { title: '', width: 50, render: (_, __, i) => <Button size="small" type="link" danger onClick={() => setItems(items.filter((_, k) => k !== i))}>删</Button> },
          ]} />
        <Button size="small" style={{ marginTop: 8 }} icon={<PlusOutlined />} onClick={() => setItems([...items, { group: '', element: '', content: '', score_min: null, score_max: null }])}>加一行</Button>
      </Modal>
    </Space>
  )
}
