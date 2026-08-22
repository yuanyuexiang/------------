import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Popconfirm, Progress, Segmented, Space, Table, Tag, Typography, Upload, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import { api, Project } from '../api'

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

/** 投标项目列表：按截止日排序；导入招标文件包（上传后轮询解析任务）。 */
export default function ProjectsPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [scope, setScope] = useState<'active' | 'closed' | 'all'>('active')
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
      message.error(String(e))
    }
    return false
  }
  const ready = (r: Project) => ['parsed', 'confirmed'].includes(r.status)

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card size="small" title="导入招标文件包">
        <Upload.Dragger accept=".zip" beforeUpload={upload} showUploadList={false} style={{ padding: 0 }}>
          <p className="ant-upload-drag-icon" style={{ marginBottom: 4 }}><InboxOutlined /></p>
          <p style={{ margin: 0 }}>拖入 ECP 下载的招标文件包（.zip，支持批次级/包级），自动解析为 TRM 并抽取投标截止时间</p>
        </Upload.Dragger>
        {task && (
          <div style={{ marginTop: 12 }}>
            <Progress percent={Math.round(task.progress * 100)} status={task.status === 'failed' ? 'exception' : task.status === 'done' ? 'success' : 'active'} />
            <Typography.Paragraph type="secondary" style={{ whiteSpace: 'pre-wrap', marginTop: 8, marginBottom: 0 }}>{task.message}</Typography.Paragraph>
          </div>
        )}
      </Card>
      <Card size="small" title="投标项目"
        extra={<Segmented value={scope} onChange={(v) => setScope(v as typeof scope)} options={[{ value: 'active', label: '在投' }, { value: 'closed', label: '已结束' }, { value: 'all', label: '全部' }]} />}>
        <Table<Project> rowKey="id" size="small" loading={isLoading} dataSource={projects} pagination={projects.length > 20 ? { pageSize: 20 } : false}
          columns={[
            { title: '批次 / 分包', dataIndex: 'batch_name', render: (v, r) => (
              <div style={{ minWidth: 0 }}>
                <a onClick={() => nav(`/projects/${r.id}`)}>{v || r.filename}</a>
                <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {[r.batch_no, r.pkg_nos.length ? r.pkg_nos.slice(0, 6).join('、') + (r.pkg_nos.length > 6 ? `…共 ${r.pkg_nos.length} 包` : '') : ''].filter(Boolean).join(' · ') || '—'}
                </Typography.Text></div>
              </div>
            ) },
            { title: '投标截止', dataIndex: 'deadline', width: 240, render: (v, r) => <DaysLeft days={r.days_left} deadline={v} /> },
            { title: '阶段', dataIndex: 'stage', width: 96, render: (s: string, r) => r.status === 'failed' ? <Tag color="red">解析失败</Tag> : r.status === 'parsing' || r.status === 'pending' ? <Tag color="processing">解析中</Tag> : <Tag color={STAGE_COLOR[s]}>{r.stage_cn}</Tag> },
            { title: '结果', dataIndex: 'outcome', width: 80, render: (o: string, r) => <Tag color={OUTCOME_COLOR[o]}>{r.outcome_cn}</Tag> },
            { title: '操作', width: 320, render: (_, r) => (
              <Space size="small">
                <Button size="small" type="primary" onClick={() => nav(`/projects/${r.id}`)}>详情</Button>
                <Button size="small" disabled={!ready(r)} onClick={() => nav(`/projects/${r.id}/trm`)}>{r.confirmed ? '确认版' : '确认 TRM'}</Button>
                <Button size="small" disabled={!ready(r)} onClick={() => nav(`/projects/${r.id}/qualify`)}>自检</Button>
                <Button size="small" disabled={!ready(r)} onClick={() => nav(`/projects/${r.id}/workbench`)}>工作台</Button>
                <Popconfirm title="删除项目及其产出文件？" onConfirm={async () => { await api.deleteProject(r.id); qc.invalidateQueries({ queryKey: ['projects'] }) }}>
                  <Button size="small" danger type="link">删除</Button>
                </Popconfirm>
              </Space>
            ) },
          ]} />
      </Card>
    </Space>
  )
}
