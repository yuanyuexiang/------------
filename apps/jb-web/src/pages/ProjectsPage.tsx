import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Dropdown, Input, Popconfirm, Progress, Segmented, Space, Table, Tag, Typography, Upload, message } from 'antd'
import { ClockCircleOutlined, FileSearchOutlined, InboxOutlined, MoreOutlined, SearchOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { api, Project } from '../api'
import { errorMessage, projectStageLabel, taskMessageLabel } from '../uiLabels'

export const STAGE_COLOR: Record<string, string> = {
  '': 'default', parsed: 'blue', confirmed: 'cyan', qualified: 'geekblue', generated: 'purple', reviewed: 'gold', submitted: 'green',
}
export const OUTCOME_COLOR: Record<string, string> = { '': 'processing', submitted: 'green', won: 'success', lost: 'error', abandoned: 'default' }

/** 剩余天数标签：<0 已过、≤3 红、≤7 橙、否则默认。 */
export function DaysLeft({ days, deadline }: { days: number | null; deadline: string }) {
  if (!deadline) return <Typography.Text type="secondary">未录入</Typography.Text>
  if (days === null) return <span>{deadline}</span>
  const d = Math.floor(days)
  const color = d < 0 ? 'default' : d <= 3 ? 'red' : d <= 7 ? 'orange' : 'blue'
  return <Space size={4}><span>{deadline}</span><Tag color={color}>{d < 0 ? `已过 ${-d} 天` : d === 0 ? '今天' : `剩 ${d} 天`}</Tag></Space>
}

/** 投标项目列表：按截止日排序；上传采购文件（上传后轮询解析任务）。 */
export default function ProjectsPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [scope, setScope] = useState<'active' | 'closed' | 'all'>('active')
  const [search, setSearch] = useState('')
  const active = scope === 'all' ? undefined : scope === 'active'
  const { data: projects = [], isLoading } = useQuery({ queryKey: ['projects', scope], queryFn: () => api.projects(active), refetchInterval: 5000 })
  const [task, setTask] = useState<{ id: string; progress: number; message: string; status: string } | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current) }, [])

  const upload = async (file: File) => {
    try {
      const { task_id } = await api.upload(file)
      setTask({ id: task_id, progress: 0, message: '已提交', status: 'queued' })
      timer.current = window.setInterval(async () => {
        const t = await api.task(task_id)
        setTask({ id: t.id, progress: t.progress, message: t.message, status: t.status })
        if (t.status === 'done' || t.status === 'failed') {
          if (timer.current) window.clearInterval(timer.current)
          qc.invalidateQueries({ queryKey: ['projects'] })
          t.status === 'done' ? message.success('解析完成') : message.error(t.message)
        }
      }, 1500)
    } catch (e) {
      message.error(errorMessage(e))
    }
    return false
  }
  const visibleProjects = projects.filter((p) =>
    [p.batch_name, p.batch_no, p.filename, ...p.pkg_nos].join(' ').toLowerCase().includes(search.trim().toLowerCase()))
  const ready = (r: Project) => ['parsed', 'confirmed'].includes(r.status)

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div className="project-overview">
        <div><span className="project-stat-icon"><FileSearchOutlined /></span><div><span>当前列表项目</span><strong>{isLoading ? '—' : projects.length}<small>个</small></strong></div></div>
        <div><span className="project-stat-icon amber"><ClockCircleOutlined /></span><div><span>七天内截止 · 当前列表</span><strong>{isLoading ? '—' : projects.filter((p) => p.days_left !== null && p.days_left >= 0 && p.days_left <= 7).length}<small>个</small></strong></div></div>
        <div><span className="project-stat-icon teal"><SafetyCertificateOutlined /></span><div><span>已核对采购信息 · 当前列表</span><strong>{isLoading ? '—' : projects.filter((p) => p.confirmed).length}<small>个</small></strong></div></div>
      </div>
      <Card size="small" title="上传采购文件" className="project-import">
        <Upload.Dragger accept=".zip" beforeUpload={upload} showUploadList={false} style={{ padding: 0 }}>
          <p className="ant-upload-drag-icon" style={{ marginBottom: 4 }}><InboxOutlined /></p>
          <p className="project-import-title">拖入采购文件压缩包，或点击上传</p>
          <p className="project-import-description">上传从采购平台下载的 ZIP 压缩包，支持整批项目或单个采购包，自动识别采购要求和关键日期</p>
        </Upload.Dragger>
        {task && (
          <div style={{ marginTop: 12 }}>
            <Progress percent={Math.round(task.progress * 100)} status={task.status === 'failed' ? 'exception' : task.status === 'done' ? 'success' : 'active'} />
            <Typography.Paragraph type="secondary" style={{ whiteSpace: 'pre-wrap', marginTop: 8, marginBottom: 0 }}>{taskMessageLabel(task.message)}</Typography.Paragraph>
          </div>
        )}
      </Card>
      <Card size="small" title={<Space>项目列表<Tag>{projects.length}</Tag></Space>} className="project-list-card">
        <div className="project-list-toolbar">
          <Segmented value={scope} onChange={(v) => setScope(v as typeof scope)} options={[{ value: 'active', label: '在投项目' }, { value: 'closed', label: '已结束' }, { value: 'all', label: '全部' }]} />
          <Input aria-label="搜索投标项目" prefix={<SearchOutlined />} placeholder="搜索项目名称、批次号或包号" allowClear value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Table<Project> scroll={{ x: 1050 }} rowKey="id" size="small" loading={isLoading} dataSource={visibleProjects} pagination={visibleProjects.length > 20 ? { pageSize: 20 } : false}
          columns={[
            { title: '采购项目 / 包号', dataIndex: 'batch_name', render: (v, r) => (
              <div style={{ minWidth: 0 }}>
                <a onClick={() => nav(`/projects/${r.id}`)}>{v || r.filename}</a>
                <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {[r.batch_no, r.pkg_nos.length ? r.pkg_nos.slice(0, 6).join('、') + (r.pkg_nos.length > 6 ? `…共 ${r.pkg_nos.length} 包` : '') : ''].filter(Boolean).join(' · ') || '—'}
                </Typography.Text></div>
              </div>
            ) },
            { title: '投标截止', dataIndex: 'deadline', width: 240, render: (v, r) => <DaysLeft days={r.days_left} deadline={v} /> },
            { title: '阶段', dataIndex: 'stage', width: 150, render: (s: string, r) => r.status === 'failed' ? <Tag color="red">解析失败</Tag> : r.status === 'parsing' || r.status === 'pending' ? <Tag color="processing">解析中</Tag> : <Tag color={STAGE_COLOR[s]}>{projectStageLabel(s) || r.stage_cn}</Tag> },
            { title: '结果', dataIndex: 'outcome', width: 80, render: (o: string, r) => <Tag color={OUTCOME_COLOR[o]}>{r.outcome_cn}</Tag> },
            { title: '操作', width: 220, render: (_, r) => (
              <Space size="small">
                <Button size="small" type="primary" onClick={() => nav(`/projects/${r.id}`)}>详情</Button>
                <Button size="small" type="link" disabled={!ready(r)} onClick={() => nav(`/projects/${r.id}/workbench`)}>准备标书</Button>
                <Dropdown trigger={['click']} menu={{ items: [
                  { key: 'trm', label: r.confirmed ? '查看采购信息' : '核对采购信息', disabled: !ready(r), onClick: () => nav(`/projects/${r.id}/trm`) },
                  { key: 'qualify', label: '检查投标资格', disabled: !ready(r), onClick: () => nav(`/projects/${r.id}/qualify`) },
                ] }}><Button size="small" type="text" aria-label="更多项目操作" icon={<MoreOutlined />} /></Dropdown>
                <Popconfirm title="删除项目及其生成的文件？" onConfirm={async () => { await api.deleteProject(r.id); qc.invalidateQueries({ queryKey: ['projects'] }) }}>
                  <Button size="small" danger type="link">删除</Button>
                </Popconfirm>
              </Space>
            ) },
          ]} />
      </Card>
    </Space>
  )
}
