import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Empty, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { api, Check, FeasibilityReport } from '../api'
import { errorMessage, checkStatusLabel } from '../uiLabels'

const VERDICT: Record<string, string> = { 可投: 'green', 有风险: 'orange', 不可投: 'red' }
const STATUS: Record<string, string> = { 满足: 'green', 风险: 'orange', 不满足: 'red', 需人工: 'blue' }

/** 检查投标资格页：选择企业档案 → 运行 → 每包可投性矩阵。 */
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
    try { setReport((await api.qualify(id, profile, llm)).report) } catch (e) { message.error(errorMessage(e)) } finally { setRunning(false) }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small" title="选择检查资料" className="business-toolbar">
        <div className="qualification-inputs">
          <div><label htmlFor="qualify-profile">本次投标企业</label><Select id="qualify-profile" placeholder="选择企业档案" value={profile} onChange={setProfile}
            options={profiles.map((p) => ({ value: p.name, label: `${p.name}（${p.credit_code || '无信用代码'}）` }))} /></div>
          <div className="workbench-draft"><span>AI 辅助判断业绩是否相关<small>比较历史项目与采购要求是否相符</small></span><Switch aria-label="AI 辅助判断业绩是否相关" checked={llm} onChange={setLlm} /></div>
        </div>
        <div className="workbench-action-bar">
          <Space wrap><Button type="primary" loading={running} onClick={run}>开始检查投标资格</Button>
          {profile && <Button onClick={() => nav(`/kb/${encodeURIComponent(profile)}?tab=performances`)}>补全企业档案</Button>}</Space>
          <Button onClick={() => nav(`/projects/${id}`)}>返回项目</Button>
        </div>
        {profiles.length === 0 && <Alert style={{ marginTop: 8 }} type="info" message="暂无企业档案：请先到左侧「企业资料」新建企业并补齐资料，再检查投标资格。" />}
      </Card>
      {!report && <Card className="business-empty"><Empty description={<span>选择企业档案并开始检查<br /><small>检查结果将按分包展示，并列出依据与待补充材料</small></span>} /></Card>}
      {report && <div className="result-summary" aria-label="资格检查结果"><span>本次资格检查 · {report.packages.length} 个分包</span>{Object.entries(VERDICT).map(([verdict, color]) => <Tag key={verdict} color={color}>{verdict} {report.packages.filter((p) => p.verdict === verdict).length}</Tag>)}</div>}
      {report && report.packages.map((p) => (
        <Card key={p.pkg_no + p.sub_no} size="small"
          title={<Space><span>{p.sub_no} {p.sub_name} {p.pkg_no}</span><Tag color={VERDICT[p.verdict]}>{p.verdict}</Tag></Space>}
          extra={<Typography.Text type="secondary">{p.project_name}</Typography.Text>}>
          <Table<Check> scroll={{ x: 1050 }} size="small" rowKey="item" pagination={false} dataSource={p.checks}
            columns={[
              { title: '检查项', dataIndex: 'item', width: 200 },
              { title: '结论', dataIndex: 'status', width: 90, render: (s: string, r) => <><Tag color={STATUS[s]}>{checkStatusLabel(s)}</Tag>{r.by_llm && <Tag color="purple">AI 辅助判断</Tag>}</> },
              { title: '说明', dataIndex: 'reason' },
              { title: '证据', dataIndex: 'evidence', width: 360, render: (e: string[]) => e.map((x, i) => <div key={i}>{x}</div>) },
              { title: '要求原文', dataIndex: 'requirement', width: 220, render: (v: string) => <Typography.Text type="secondary">{v}</Typography.Text> },
            ]} />
        </Card>
      ))}
    </Space>
  )
}
