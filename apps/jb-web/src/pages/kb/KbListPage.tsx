import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api, KbKind, ProfileSummary } from '../../api'
import { KIND_TITLES } from './fields'

const COUNT_KINDS: KbKind[] = ['certificates', 'personnel', 'performances', 'financials', 'products', 'test_reports', 'boilerplates']

/** 企业知识库列表：各企业档案概览（条目数）+ 新建 / 删除。系统为供应商自用，通常只有本企业一条。 */
export default function KbListPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()
  const create = useMutation({
    mutationFn: (v: { name: string; credit_code: string }) => api.saveMain(v.name, { credit_code: v.credit_code }),
    onSuccess: (_, v) => { message.success('已新建'); setCreating(false); qc.invalidateQueries({ queryKey: ['profiles'] }); nav(`/kb/${encodeURIComponent(v.name)}`) },
    onError: (e) => message.error(String(e)),
  })
  const remove = useMutation({
    mutationFn: (name: string) => api.deleteProfile(name),
    onSuccess: () => { message.success('已删除'); qc.invalidateQueries({ queryKey: ['profiles'] }) },
    onError: (e) => message.error(String(e)),
  })

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="info" showIcon message="知识库是投标文件中所有事实字段的唯一来源：企业信息、证照、人员、业绩、产品参数只从这里填入，系统不会生成。证照与检测报告录入有效期后自动预警。" />
      <Card size="small" title="企业档案" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreating(true) }}>新建企业</Button>}>
        <Table<ProfileSummary> rowKey="name" loading={isLoading} dataSource={data} pagination={false}
          columns={[
            { title: '企业', dataIndex: 'name', render: (v: string) => <a onClick={() => nav(`/kb/${encodeURIComponent(v)}`)}>{v}</a> },
            { title: '统一社会信用代码', dataIndex: 'credit_code', width: 200 },
            { title: '档案概览', dataIndex: 'counts', render: (c: Record<KbKind, number>) => (
              <Space size={[4, 4]} wrap>
                {COUNT_KINDS.map((k) => <Tag key={k} color={c[k] ? 'blue' : 'default'}>{KIND_TITLES[k]} {c[k] ?? 0}</Tag>)}
              </Space>
            ) },
            { title: '更新', dataIndex: 'updated_at', width: 160, render: (v: string) => v.replace('T', ' ').slice(0, 16) },
            { title: '操作', width: 160, render: (_, r) => (
              <Space>
                <Button size="small" type="primary" onClick={() => nav(`/kb/${encodeURIComponent(r.name)}`)}>管理</Button>
                <Popconfirm title={`删除 ${r.name} 及其全部档案？`} onConfirm={() => remove.mutate(r.name)}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            ) },
          ]} />
        {!isLoading && data.length === 0 && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
            尚无企业档案。可点"新建企业"手工建档，或用 <code>scripts/demo.py</code> / <code>jb_kb.build_profile</code> 从历史投标文件成品导入后在此补全。
          </Typography.Paragraph>
        )}
      </Card>

      <Modal open={creating} title="新建企业档案" onCancel={() => setCreating(false)} onOk={() => form.validateFields().then((v) => create.mutate(v))} confirmLoading={create.isPending}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="企业名称（须与营业执照一致）" rules={[{ required: true, message: '请填写企业名称' }]}><Input /></Form.Item>
          <Form.Item name="credit_code" label="统一社会信用代码" rules={[{ pattern: /^[0-9A-Z]{18}$/, message: '18 位数字/大写字母' }]}><Input maxLength={18} /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
