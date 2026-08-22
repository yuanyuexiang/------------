import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { api, Check, FeasibilityReport } from '../api'

const VERDICT: Record<string, string> = { 可投: 'green', 有风险: 'orange', 不可投: 'red' }
const STATUS: Record<string, string> = { 满足: 'green', 风险: 'orange', 不满足: 'red', 需人工: 'blue' }

/** 资格自检页：选择企业档案 → 运行 → 每包可投性矩阵。 */
export default function QualifyPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const [profile, setProfile] = useState<string>()
  const [llm, setLlm] = useState(true)
  const [report, setReport] = useState<FeasibilityReport | null>(null)
  const [running, setRunning] = useState(false)

  const run = async () => {
    if (!profile) return message.warning('请选择企业档案')
    setRunning(true)
    try { setReport((await api.qualify(id, profile, llm)).report) } catch (e) { message.error(String(e)) } finally { setRunning(false) }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <Select placeholder="选择企业档案" style={{ width: 280 }} value={profile} onChange={setProfile}
            options={profiles.map((p) => ({ value: p.name, label: `${p.name}（${p.credit_code || '无信用代码'}）` }))} />
          <span>LLM 业绩语义匹配 <Switch checked={llm} onChange={setLlm} /></span>
          <Button type="primary" loading={running} onClick={run}>运行资格自检</Button>
          {profile && <Button onClick={() => nav(`/kb/${encodeURIComponent(profile)}?tab=performances`)}>补全档案</Button>}
          <Button onClick={() => nav(`/projects/${id}`)}>返回</Button>
        </Space>
        {profiles.length === 0 && <Alert style={{ marginTop: 8 }} type="info" message="暂无企业档案：到左侧「企业知识库」新建，或运行 scripts/import_profiles.py 从历史投标文件导入" />}
      </Card>
      {report && report.packages.map((p) => (
        <Card key={p.pkg_no + p.sub_no} size="small"
          title={<Space><span>{p.sub_no} {p.sub_name} {p.pkg_no}</span><Tag color={VERDICT[p.verdict]}>{p.verdict}</Tag></Space>}
          extra={<Typography.Text type="secondary">{p.project_name}</Typography.Text>}>
          <Table<Check> size="small" rowKey="item" pagination={false} dataSource={p.checks}
            columns={[
              { title: '检查项', dataIndex: 'item', width: 200 },
              { title: '结论', dataIndex: 'status', width: 90, render: (s: string, r) => <><Tag color={STATUS[s]}>{s}</Tag>{r.by_llm && <Tag color="purple">LLM</Tag>}</> },
              { title: '说明', dataIndex: 'reason' },
              { title: '证据', dataIndex: 'evidence', width: 360, render: (e: string[]) => e.map((x, i) => <div key={i}>{x}</div>) },
              { title: '要求原文', dataIndex: 'requirement', width: 220, render: (v: string) => <Typography.Text type="secondary">{v}</Typography.Text> },
            ]} />
        </Card>
      ))}
    </Space>
  )
}
