import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Descriptions, Input, Select, Space, Spin, Table, Tag, message } from 'antd'
import { api, CompanyProfile, Performance } from '../api'

/** 企业档案页：查看主档，补录业绩关键字段（签约日期/买方是否最终用户/金额）。 */
export default function ProfilePage() {
  const { name = '' } = useParams()
  const nav = useNavigate()
  const { data, isLoading } = useQuery({ queryKey: ['profile', name], queryFn: () => api.profile(name) })
  const [p, setP] = useState<CompanyProfile | null>(null)
  useEffect(() => { if (data) setP(data) }, [data])
  if (isLoading || !p) return <Spin />

  const setPerf = (i: number, patch: Partial<Performance>) =>
    setP({ ...p, performances: p.performances.map((x, k) => k === i ? { ...x, ...patch } : x) })
  const save = async () => {
    try { await api.saveProfile(name, p); message.success('档案已保存') } catch (e) { message.error(String(e)) }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small" title={p.name} extra={<Space><Button type="primary" onClick={save}>保存</Button><Button onClick={() => nav('/')}>返回</Button></Space>}>
        <Descriptions size="small" column={4}>
          <Descriptions.Item label="统一社会信用代码">{p.credit_code}</Descriptions.Item>
          <Descriptions.Item label="注册资本（万）">{p.registered_capital_wan ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="员工">{p.staff_total ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="人员/证书">{p.personnel.length} / {p.certificates.length}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card size="small" title={`业绩（${p.performances.length}）— 补全签约日期与最终用户后，资格自检才能判"满足"`}>
        <Table<Performance> size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={p.performances}
          columns={[
            { title: '项目', dataIndex: 'project' },
            { title: '买方', dataIndex: 'buyer', width: 220, render: (v, _, i) => <Input size="small" value={v} onChange={(e) => setPerf(i, { buyer: e.target.value })} /> },
            { title: '最终用户？', dataIndex: 'buyer_is_end_user', width: 130, render: (v, _, i) => (
              <Select size="small" style={{ width: 110 }} value={v === null ? undefined : v} placeholder="未录入" allowClear
                onChange={(val) => setPerf(i, { buyer_is_end_user: val ?? null })}
                options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
            ) },
            { title: '签约日期', dataIndex: 'signed_date', width: 140, render: (v, _, i) => <Input size="small" placeholder="YYYY-MM-DD" value={v} onChange={(e) => setPerf(i, { signed_date: e.target.value })} /> },
            { title: '金额（万）', dataIndex: 'amount_wan', width: 110, render: (v, _, i) => <Input size="small" value={v ?? ''} onChange={(e) => setPerf(i, { amount_wan: e.target.value ? Number(e.target.value) : null })} /> },
            { title: '证据', dataIndex: 'evidence', width: 120, render: (e: string[]) => e.map((x) => <Tag key={x}>{x}</Tag>) },
          ]} />
      </Card>
    </Space>
  )
}
