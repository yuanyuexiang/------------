import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Progress, Space, Table, Tag, Typography, Upload, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import { api, Project } from '../api'

const STATUS_COLOR: Record<string, string> = {
  pending: 'default', parsing: 'processing', parsed: 'blue', confirmed: 'green', failed: 'red',
}

/** 投标项目列表 + 导入招标文件包（上传后轮询解析任务）。 */
export default function ProjectsPage() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: projects = [], isLoading } = useQuery({ queryKey: ['projects'], queryFn: api.projects, refetchInterval: 5000 })
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

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Card title="导入招标文件包">
        <Upload.Dragger accept=".zip" beforeUpload={upload} showUploadList={false}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p>拖入 ECP 下载的招标文件包（.zip，支持批次级/包级），自动解析为 TRM</p>
        </Upload.Dragger>
        {task && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={Math.round(task.progress * 100)} status={task.status === 'failed' ? 'exception' : task.status === 'done' ? 'success' : 'active'} />
            <Typography.Paragraph type="secondary" style={{ whiteSpace: 'pre-wrap', marginTop: 8 }}>{task.message}</Typography.Paragraph>
          </div>
        )}
      </Card>
      <Card title="投标项目">
        <Table<Project> rowKey="id" loading={isLoading} dataSource={projects} pagination={false}
          columns={[
            { title: '批次', dataIndex: 'batch_name', render: (v, r) => v || r.filename },
            { title: '批次号', dataIndex: 'batch_no', width: 160 },
            { title: '状态', dataIndex: 'status', width: 110, render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag> },
            { title: '创建', dataIndex: 'created_at', width: 170, render: (v: string) => v.replace('T', ' ').slice(0, 16) },
            { title: '操作', width: 220, render: (_, r) => (
              <Space>
                <Button size="small" type="primary" disabled={!['parsed', 'confirmed'].includes(r.status)} onClick={() => nav(`/projects/${r.id}/trm`)}>
                  {r.confirmed ? '查看确认版' : '确认 TRM'}
                </Button>
                <Button size="small" disabled={!['parsed', 'confirmed'].includes(r.status)} onClick={() => nav(`/projects/${r.id}/qualify`)}>资格自检</Button>
              </Space>
            ) },
          ]} />
      </Card>
    </Space>
  )
}
