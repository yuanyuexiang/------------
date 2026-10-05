import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import { BankOutlined, PlusOutlined } from '@ant-design/icons'
import { api, fmtUtc, KbKind, ProfileSummary } from '../../api'
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
            { title: '更新', dataIndex: 'updated_at', width: 160, render: fmtUtc },
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
            尚无企业档案。点击右上角“新建企业”，录入企业基本信息后，再补齐证照、人员与业绩资料。
          </Typography.Paragraph>
        )}
      </Card>

      <Modal className="jb-dialog" centered cancelText="取消" open={creating} width={560} okText="创建档案" title={<span className="dialog-title"><span className="dialog-title-icon"><BankOutlined /></span><span>新建企业档案<small>建立企业资料，开启投标准备</small></span></span>} onCancel={() => setCreating(false)} onOk={() => form.validateFields().then((v) => create.mutate(v))} confirmLoading={create.isPending}>
        <div className="dialog-intro">先填写企业基本信息，创建后可继续补齐证照、人员及业绩材料。</div>
        <Form form={form} layout="vertical">

          <Form.Item name="name" label="企业名称" extra="请填写与营业执照一致的企业全称" rules={[{ required: true, message: '请填写企业名称' }]}><Input placeholder="请输入企业全称" autoComplete="organization" /></Form.Item>
          <Form.Item name="credit_code" label="统一社会信用代码" extra="18 位数字或大写字母，可在创建后补充" rules={[{ pattern: /^[0-9A-Z]{18}$/, message: '18 位数字/大写字母' }]}><Input maxLength={18} placeholder="请输入统一社会信用代码" /></Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
