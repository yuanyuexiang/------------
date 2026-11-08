import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Space, Spin, Tag, Typography } from 'antd'
import { api } from '../api'
import { errorMessage } from '../uiLabels'
import { useProjectWorkspace } from './ProjectWorkspace'
import './RequirementsPanel.css'

export default function ProjectTasks() {
  const { id = '' } = useParams()
  const { project, profile, pkgIndex, href } = useProjectWorkspace()
  const nav = useNavigate()
  const enabled = !!profile && ['parsed', 'confirmed'].includes(project.status) && project.package_list.length > 0
  const preparation = useQuery({ queryKey: ['preparation', id, profile, pkgIndex], queryFn: () => api.preparation(id, profile!, pkgIndex), enabled })
  const qualification = useQuery({ queryKey: ['qualification', id, profile, pkgIndex], queryFn: () => api.qualification(id, profile!, pkgIndex), enabled })
  const flow = useQuery({ queryKey: ['workflow', id, profile, pkgIndex], queryFn: () => api.workflow(id, profile!, pkgIndex), enabled })
  const error = preparation.error || qualification.error || flow.error
  const tasks = preparation.data?.tasks.filter(t => t.required && !t.complete && !['system', 'other'].includes(t.id)) ?? []
  const currentGeneration = flow.data && flow.data.profile === profile ? flow.data.generation : null
  const closed = ['won', 'lost', 'abandoned'].includes(project.outcome)
  const rows = [
    { title: '核对采购信息', status: project.confirmed ? '已确认' : '待核对', route: href('trm'), detail: '核对采购包、截止日期及重要条款', pending: !project.confirmed },
    { title: '检查本包投标资格', status: qualification.data?.stale ? '需重新检查' : qualification.data?.report ? '已检查，查看风险' : '尚未检查', route: href('qualify'), detail: '检查结论与资料准备状态分别记录', pending: !qualification.data?.report || !!qualification.data?.stale },
    ...tasks.map(t => ({ title: t.title, status: t.status, route: `${href('workbench', pkgIndex, 'prepare')}&task=${t.id}`, detail: t.current_notes?.[0] || '处理本包资料和本次安排', pending: true })),
    { title: '生成本包投标文件', status: flow.data?.stale ? '输入变化，待更新' : currentGeneration ? '已有生成版本' : '尚未生成', route: href('workbench', pkgIndex, currentGeneration && !flow.data?.stale ? 'review' : 'prepare'), detail: '生成商务、技术文件，并保留版本', pending: !currentGeneration || !!flow.data?.stale },
    { title: '审阅与提交前检查', status: !currentGeneration ? '等待生成' : flow.data?.blockers.length ? '仍有待处理事项' : '可正式导出', route: href('workbench', pkgIndex, 'review'), detail: flow.data?.blockers[0] || '核对文件、签章、附件及提交要求', pending: !currentGeneration || !!flow.data?.blockers.length },
  ]
  const next = rows.find(r => r.pending)
  return <Card size="small" title="本包待办与下一步" extra={<Typography.Text type="secondary">可并行处理资料，生成与导出按条件检查</Typography.Text>}>
    {!profile && <Alert type="info" message="请先选择本次投标企业，查看当前包的准备任务" />}
    {error && <Alert type="error" message="待办状态未能完整读取" description={errorMessage(error)} />}
    {enabled && (preparation.isLoading || flow.isLoading || qualification.isLoading) ? <Spin /> : <>
      {enabled && !error && next && !closed && <Space wrap style={{ marginBottom: 16 }}><Typography.Text strong>建议先处理：{next.title}</Typography.Text><Button type="primary" onClick={() => nav(next.route)}>前往处理</Button></Space>}
      <div className="task-hub-list">{rows.map((row, i) => <div className="task-hub-row" key={i}>
        <div><Typography.Text strong>{row.title}</Typography.Text><p>{row.detail}</p></div>
        <Space wrap><Tag color={row.pending ? 'orange' : 'default'}>{row.status}</Tag><Button disabled={!enabled && i !== 0} onClick={() => nav(row.route)}>查看 / 处理</Button></Space>
      </div>)}</div>
    </>}
  </Card>
}
