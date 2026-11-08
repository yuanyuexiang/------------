import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Empty, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { api, Check } from '../api'
import { useProjectWorkspace } from '../components/ProjectWorkspace'
import { errorMessage, checkStatusLabel } from '../uiLabels'

const VERDICT: Record<string, string> = { 可投: 'green', 有风险: 'orange', 不可投: 'red' }
const STATUS: Record<string, string> = { 满足: 'green', 风险: 'orange', 不满足: 'red', 需人工: 'blue' }

/** 检查投标资格页：选择企业档案 → 运行 → 每包可投性矩阵。 */
export default function QualifyPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { project, profile, pkgIndex, href, setSelectionLocked } = useProjectWorkspace()
  const [llm, setLlm] = useState(true)
  const [running, setRunning] = useState(false)
  const { data: result, error, isFetching } = useQuery({ queryKey: ['qualification', id, profile],
    queryFn: () => api.qualification(id, profile!), enabled: !!profile, staleTime: 0 })
  const report = result?.report
  const selected = report?.packages[pkgIndex]

  const run = async () => {
    if (!profile) return message.warning('请选择企业档案')
    setRunning(true)
    setSelectionLocked(true)
    try {
      await api.qualify(id, profile, llm)
      await Promise.all([qc.invalidateQueries({ queryKey: ['qualification', id] }), qc.invalidateQueries({ queryKey: ['project-detail', id] }), qc.invalidateQueries({ queryKey: ['projects'] })])
      message.success('资格检查已完成，请查看本包结论与风险')
    } catch (e) { message.error(errorMessage(e)) } finally { setRunning(false); setSelectionLocked(false) }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small" title="选择检查资料" className="business-toolbar">
        <div className="qualification-inputs">
          <div className="workbench-draft"><span>AI 辅助判断业绩是否相关<small>比较历史项目与采购要求是否相符</small></span><Switch aria-label="AI 辅助判断业绩是否相关" checked={llm} onChange={setLlm} /></div>
        </div>
        <div className="workbench-action-bar">
          <Space wrap><Button type="primary" disabled={!profile || isFetching} loading={running} onClick={run}>{report ? '重新检查投标资格' : '开始检查投标资格'}</Button>
          {profile && <Button onClick={() => nav(`/kb/${encodeURIComponent(profile)}?tab=performances&returnTo=${encodeURIComponent(href('qualify'))}`)}>补全企业档案</Button>}
          <Button disabled={!profile || running} onClick={() => nav(href('workbench', pkgIndex, 'prepare'))}>{selected?.verdict === '可投' && !result?.stale ? '下一步：准备本包文件' : '准备本包资料与处理风险'}</Button></Space>
        </div>
        {!profile && <Alert style={{ marginTop: 8 }} type="info" message="请在项目顶部选择投标企业；尚无档案时，请先到企业资料中新建。" />}
        {!project.confirmed && <Alert style={{ marginTop: 8 }} type="warning" message="当前为未确认采购信息下的初筛，确认或修改采购信息后需要重新检查。" action={<Button onClick={() => nav(href('trm'))}>核对采购信息</Button>} />}
      </Card>
      {error && <Alert type="error" message="无法恢复资格报告" description={errorMessage(error)} />}
      {result?.stale && <Alert type="warning" showIcon message="采购信息或投标资料已变化，请重新检查资格" description="已有报告仅作历史参考，不代表本包当前资格结论。" />}
      {!report && <Card className="business-empty"><Empty description={isFetching ? '正在恢复资格报告…' : <span>选择企业档案并开始检查<br /><small>检查覆盖各采购包，下方展示顶部所选采购包的结果</small></span>} /></Card>}
      {report && <div className="result-summary" aria-label="资格检查结果"><span>本次资格检查 · {report.packages.length} 个分包</span>{Object.entries(VERDICT).map(([verdict, color]) => <Tag key={verdict} color={color}>{verdict} {report.packages.filter((p) => p.verdict === verdict).length}</Tag>)}</div>}
      {selected && [selected].map((p) => (
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
