import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Breadcrumb, Button, Card, Col, Descriptions, Input, Popconfirm, Row, Select, Space, Spin, Steps, Table, Tag, Timeline, Typography, message } from 'antd'
import { api, fmtUtc, ProjectEvent } from '../api'
import { DaysLeft, OUTCOME_COLOR } from './ProjectsPage'

const STAGE_TITLE = ['解析', '确认 TRM', '资格自检', '生成文件', '合规审查', '递交']
const VERDICT_COLOR: Record<string, string> = { 可投: 'green', 有风险: 'orange', 不可投: 'red' }
const EVENT_COLOR: Record<string, string> = {
  parsed: 'blue', confirmed: 'cyan', qualified: 'geekblue', generated: 'purple', reviewed: 'gold', scored: 'purple',
  exported: 'green', outcome: 'green', deadline: 'orange',
}
const EVENT_CN: Record<string, string> = {
  parsed: '解析', confirmed: '确认', qualified: '自检', generated: '生成', reviewed: '审查', scored: '评分', exported: '导出', outcome: '结果', deadline: '时间',
}
const OUTCOMES = [{ value: '', label: '在投' }, { value: 'submitted', label: '已递交' }, { value: 'won', label: '中标' }, { value: 'lost', label: '未中标' }, { value: 'abandoned', label: '放弃' }]
const fmt = fmtUtc

/** 项目详情：概览（截止/开标可改、结果、备注）、阶段、各包进度与结果、产出文件、时间线。 */
export default function ProjectDetailPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: p, isLoading } = useQuery({ queryKey: ['project-detail', id], queryFn: () => api.projectDetail(id), refetchInterval: (q) => (q.state.data?.tasks ?? []).some((t) => t.status === 'running' || t.status === 'queued') ? 3000 : false })
  const [deadline, setDeadline] = useState('')
  const [openTime, setOpenTime] = useState('')
  const [notes, setNotes] = useState('')
  useEffect(() => { if (p) { setDeadline(p.deadline); setOpenTime(p.open_time); setNotes(p.notes) } }, [p])
  const patch = useMutation({
    mutationFn: (fields: Parameters<typeof api.patchProject>[1]) => api.patchProject(id, fields),
    onSuccess: () => { message.success('已保存'); qc.invalidateQueries({ queryKey: ['project-detail', id] }); qc.invalidateQueries({ queryKey: ['projects'] }) },
    onError: (e) => message.error(String(e)),
  })
  if (isLoading || !p) return <Spin />

  const ready = ['parsed', 'confirmed'].includes(p.status)
  const r = p.results
  // 各环节按实际结果逐项点亮（阶段可跳：未确认 TRM 也能自检），而不是"到达最远阶段前全部算完成"
  const done = [ready, p.confirmed, !!r.qualify, !!r.generate && Object.keys(r.generate).length > 0,
    !!r.review && Object.keys(r.review).length > 0, ['submitted', 'won', 'lost'].includes(p.outcome)]
  const current = Math.max(0, done.lastIndexOf(true))
  const timeDirty = deadline !== p.deadline || openTime !== p.open_time

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Breadcrumb items={[{ title: <Link to="/">投标项目</Link> }, { title: p.batch_name || p.filename }]} />
      {p.status === 'failed' && <Alert type="error" showIcon message="解析失败" description={p.error} />}

      <Card size="small" title={<Space>{p.batch_name || p.filename}<Typography.Text type="secondary" style={{ fontWeight: 400 }}>{p.batch_no}</Typography.Text><Tag color={OUTCOME_COLOR[p.outcome]}>{p.outcome_cn}</Tag></Space>}
        extra={<Space>
          <Button type="primary" disabled={!ready} onClick={() => nav(`/projects/${id}/trm`)}>{p.confirmed ? '查看确认版' : '确认 TRM'}</Button>
          <Button disabled={!ready} onClick={() => nav(`/projects/${id}/qualify`)}>资格自检</Button>
          <Button disabled={!ready} onClick={() => nav(`/projects/${id}/workbench`)}>生成与审查</Button>
          <Popconfirm title="删除项目及其产出文件？" onConfirm={async () => { await api.deleteProject(id); nav('/') }}><Button danger>删除</Button></Popconfirm>
        </Space>}>
        <Steps size="small" current={current} status={p.status === 'failed' ? 'error' : 'finish'}
          items={STAGE_TITLE.map((t, i) => ({ title: t, status: p.status === 'failed' && i === 0 ? 'error' : done[i] ? 'finish' : 'wait' }))} style={{ marginBottom: 16 }} />
        <Row gutter={24}>
          <Col span={14}>
            <Descriptions size="small" column={2} bordered labelStyle={{ width: 96, whiteSpace: 'nowrap' }}>
              <Descriptions.Item label="投标截止" span={2}>
                <Space>
                  <Input size="small" style={{ width: 170 }} value={deadline} onChange={(e) => setDeadline(e.target.value)} placeholder="YYYY-MM-DD HH:MM" />
                  <DaysLeft days={p.days_left} deadline={p.deadline} />
                  {p.deadline_manual ? <Tag>人工录入</Tag> : p.deadline ? <Tag color="blue">来自招标公告</Tag> : null}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="开标时间" span={2}>
                <Space>
                  <Input size="small" style={{ width: 170 }} value={openTime} onChange={(e) => setOpenTime(e.target.value)} placeholder="YYYY-MM-DD HH:MM" />
                  {p.key_terms.bid_open_note && <Typography.Text type="secondary">公告：{p.key_terms.bid_open_note}</Typography.Text>}
                  {timeDirty && <Button size="small" type="primary" loading={patch.isPending} onClick={() => patch.mutate({ deadline, open_time: openTime })}>保存时间</Button>}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="结果">
                <Select size="small" style={{ width: 120 }} value={p.outcome} options={OUTCOMES} onChange={(v) => patch.mutate({ outcome: v })} />
              </Descriptions.Item>
              <Descriptions.Item label="文件">{p.filename}</Descriptions.Item>
              <Descriptions.Item label="投标有效期">{p.key_terms.validity_days ? `${p.key_terms.validity_days} 天` : '—'}</Descriptions.Item>
              <Descriptions.Item label="保证金">{p.key_terms.deposit_mode ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="创建">{fmt(p.created_at)}</Descriptions.Item>
              <Descriptions.Item label="更新">{fmt(p.updated_at)}</Descriptions.Item>
            </Descriptions>
            {p.key_terms.bid_deadline_text && <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>公告原文：{p.key_terms.bid_deadline_text}</Typography.Paragraph>}
          </Col>
          <Col span={10}>
            <Input.TextArea rows={6} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="备注：分工、联系人、注意事项…" />
            {notes !== p.notes && <Button size="small" style={{ marginTop: 8 }} loading={patch.isPending} onClick={() => patch.mutate({ notes })}>保存备注</Button>}
          </Col>
        </Row>
      </Card>

      <Card size="small" title={`分包进度（${p.package_list.length}）`}>
        <Table rowKey="pkg_no" size="small" pagination={false} dataSource={p.package_list}
          columns={[
            { title: '包', dataIndex: 'pkg_no', width: 80 },
            { title: '分标', dataIndex: 'sub_name', width: 160, ellipsis: true, render: (v, row) => [row.sub_no, v].filter(Boolean).join(' ') || '—' },
            { title: '项目', dataIndex: 'project_name', ellipsis: true },
            { title: '预算(元)', dataIndex: 'budget_yuan', width: 120, render: (v: number | null) => v ? v.toLocaleString() : '—' },
            { title: '自检', width: 90, render: (_, row) => { const v = r.qualify?.verdicts?.[row.pkg_no]; return v ? <Tag color={VERDICT_COLOR[v]}>{v}</Tag> : '—' } },
            { title: '生成', width: 150, render: (_, row) => { const g = r.generate?.[row.pkg_no]; return g ? <Tag color={g.export_blocked ? 'orange' : 'green'}>待补充 {g.todo_count}{g.with_draft ? ' · 含起草' : ''}</Tag> : '—' } },
            { title: '上次审查（当前状态见工作台）', width: 210, render: (_, row) => { const v = r.review?.[row.pkg_no]; return v ? <Tag>{v.blocked ? '有否决项' : '无否决项'} {Object.entries(v.counts).map(([k, n]) => `${k}${n}`).join(' ')}</Tag> : '—' } },
            { title: '模拟评分', width: 190, render: (_, row) => { const v = r.score?.[row.pkg_no]; return v ? <span>技 {v.tech_total ?? '—'}/{v.tech_max} · 商 {v.biz_total ?? '—'}/{v.biz_max}{v.weighted !== null ? ` · 加权 ${v.weighted}` : ''}</span> : '—' } },
          ]} />
      </Card>

      <Row gutter={16}>
        <Col span={12}>
          <Card size="small" title={`产出文件（${p.files.length}）`}>
            <Typography.Paragraph type="secondary">草稿用于核对和整改；正式件需在工作台通过检查后导出，资料变化后需重新生成或复查。</Typography.Paragraph>
            {p.files.length === 0 ? <Typography.Text type="secondary">尚未生成，到"生成与审查"工作台生成商务/技术文件</Typography.Text> : (
              <Table size="small" rowKey="name" pagination={false} dataSource={p.files}
                columns={[
                  { title: '文件', dataIndex: 'name', ellipsis: true, render: (v: string) => <a href={api.fileUrl(id, v)}>{v.startsWith('正式_') ? '正式件：' : '草稿：'}{v}</a> },
                  { title: '大小', dataIndex: 'size', width: 90, render: (n: number) => `${Math.ceil(n / 1024)} KB` },
                  { title: '修改', dataIndex: 'modified', width: 150, render: fmt },
                ]} />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title={`时间线（${p.events.length}）`} style={{ maxHeight: 480, overflowY: 'auto' }}>
            {p.tasks.filter((t) => t.status === 'running' || t.status === 'queued').map((t) => (
              <Alert key={t.id} type="info" showIcon style={{ marginBottom: 8 }} message={`${t.kind} 进行中 ${Math.round(t.progress * 100)}%`} description={t.message} />
            ))}
            <Timeline items={p.events.map((e: ProjectEvent) => ({
              color: EVENT_COLOR[e.kind] ?? 'gray',
              children: <span><Typography.Text type="secondary">{fmt(e.created_at)} · {e.actor || 'system'}</Typography.Text> <Tag style={{ marginLeft: 6 }}>{EVENT_CN[e.kind] ?? e.kind}</Tag>{e.message}</span>,
            }))} />
            {p.events.length === 0 && <Typography.Text type="secondary">暂无事件</Typography.Text>}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
