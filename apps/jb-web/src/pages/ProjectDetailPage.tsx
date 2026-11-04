import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Input, Popconfirm, Row, Select, Space, Spin, Steps, Table, Tag, Timeline, Typography, message } from 'antd'
import { api, fmtUtc, ProjectEvent } from '../api'
import { errorMessage, reviewLevelLabel, taskKindLabel, taskMessageLabel } from '../uiLabels'
import { DaysLeft, OUTCOME_COLOR } from './ProjectsPage'

const STAGE_TITLE = ['读取采购文件', '核对采购信息', '检查投标资格', '生成标书', '检查投标文件', '提交投标文件']
const VERDICT_COLOR: Record<string, string> = { 可投: 'green', 有风险: 'orange', 不可投: 'red' }
const EVENT_COLOR: Record<string, string> = {
  parsed: 'blue', confirmed: 'cyan', qualified: 'geekblue', generated: 'purple', reviewed: 'gold', scored: 'purple',
  exported: 'green', outcome: 'green', deadline: 'orange',
}
const EVENT_CN: Record<string, string> = {
  parsed: '读取采购文件', confirmed: '确认', qualified: '自检', generated: '生成', reviewed: '审查', scored: '评分', exported: '导出', outcome: '结果', deadline: '时间',
}
const OUTCOMES = [{ value: '', label: '在投' }, { value: 'submitted', label: '已递交' }, { value: 'won', label: '中标' }, { value: 'lost', label: '未中标' }, { value: 'abandoned', label: '放弃' }]
const fmt = fmtUtc

/** 项目详情：概览（截止/开标可改、结果、备注）、阶段、各包进度与结果、生成的文件、时间线。 */
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
    onError: (e) => message.error(errorMessage(e)),
  })
  if (isLoading || !p) return <Spin />

  const ready = ['parsed', 'confirmed'].includes(p.status)
  const r = p.results
  // 各环节按实际结果逐项点亮（可以直接进入后续操作：未核对采购信息也能自检），而不是"到达最远阶段前全部算完成"
  const done = [ready, p.confirmed, !!r.qualify, !!r.generate && Object.keys(r.generate).length > 0,
    !!r.review && Object.keys(r.review).length > 0, ['submitted', 'won', 'lost'].includes(p.outcome)]
  const current = Math.max(0, done.lastIndexOf(true))
  const timeDirty = deadline !== p.deadline || openTime !== p.open_time

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {p.status === 'failed' && <Alert type="error" showIcon message="解析失败" description={p.error} />}

      <Card className="project-detail-overview" size="small" title={<Space wrap>{p.batch_name || p.filename}<Typography.Text type="secondary" style={{ fontWeight: 400 }}>{p.batch_no}</Typography.Text><Tag color={OUTCOME_COLOR[p.outcome]}>{p.outcome_cn}</Tag></Space>}
        extra={<Space wrap>
          <Button type="primary" disabled={!ready} onClick={() => nav(`/projects/${id}/trm`)}>{p.confirmed ? '查看采购信息' : '核对采购信息'}</Button>
          <Button disabled={!ready} onClick={() => nav(`/projects/${id}/qualify`)}>检查投标资格</Button>
          <Button disabled={!ready} onClick={() => nav(`/projects/${id}/workbench`)}>准备标书</Button>
          <Popconfirm title="删除项目及其生成的文件？" onConfirm={async () => { await api.deleteProject(id); nav('/') }}><Button danger>删除</Button></Popconfirm>
        </Space>}>
        <div className="project-stage-panel"><div className="section-caption">投标准备进度<span>按各环节实际结果展示</span></div>
        <Steps size="small" current={current} status={p.status === 'failed' ? 'error' : 'finish'}
          items={STAGE_TITLE.map((t, i) => ({ title: t, status: p.status === 'failed' && i === 0 ? 'error' : done[i] ? 'finish' : 'wait' }))}  /></div>
        <Row gutter={[24, 20]}>
          <Col xs={24} xl={16}>
            <Descriptions size="small" column={2} bordered labelStyle={{ width: 96, whiteSpace: 'nowrap' }}>
              <Descriptions.Item label="投标截止" span={2}>
                <Space wrap>
                  <Input size="small" style={{ width: 170 }} value={deadline} onChange={(e) => setDeadline(e.target.value)} placeholder="YYYY-MM-DD HH:MM" />
                  <DaysLeft days={p.days_left} deadline={p.deadline} />
                  {p.deadline_manual ? <Tag>人工录入</Tag> : p.deadline ? <Tag color="blue">来自招标公告</Tag> : null}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="开标时间" span={2}>
                <Space wrap>
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
          <Col xs={24} xl={8}>
            <div className="section-caption">项目备注<span>记录分工与本次投标注意事项</span></div>
            <Input.TextArea rows={6} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="备注：分工、联系人、注意事项…" />
            {notes !== p.notes && <Button size="small" style={{ marginTop: 8 }} loading={patch.isPending} onClick={() => patch.mutate({ notes })}>保存备注</Button>}
          </Col>
        </Row>
      </Card>

      <Card size="small" title={`各采购包进度（${p.package_list.length}）`}>
        <Table scroll={{ x: 1100 }} rowKey="result_key" size="small" pagination={false} dataSource={p.package_list}
          columns={[
            { title: '包', dataIndex: 'pkg_no', width: 80 },
            { title: '分标', dataIndex: 'sub_name', width: 160, ellipsis: true, render: (v, row) => [row.sub_no, v].filter(Boolean).join(' ') || '—' },
            { title: '项目', dataIndex: 'project_name', ellipsis: true },
            { title: '预算(元)', dataIndex: 'budget_yuan', width: 120, render: (v: number | null) => v ? v.toLocaleString() : '—' },
            { title: '资格检查', width: 90, render: (_, row) => { const v = r.qualify?.verdicts?.[row.result_key]; return v ? <Tag color={VERDICT_COLOR[v]}>{v}</Tag> : '—' } },
            { title: '生成', width: 150, render: (_, row) => { const g = r.generate?.[row.result_key]; return g ? <Tag color={g.export_blocked ? 'orange' : 'green'}>待补充 {g.todo_count}{g.with_draft ? ' · 含起草' : ''}</Tag> : '—' } },
            { title: '上次文件检查结果', width: 210, render: (_, row) => { const v = r.review?.[row.result_key]; return v ? <Tag>{v.blocked ? '有投标无效风险' : '未发现投标无效风险'} {Object.entries(v.counts).map(([k, n]) => `${reviewLevelLabel(k)}${n}`).join(' ')}</Tag> : '—' } },
            { title: '预估评分', width: 190, render: (_, row) => { const v = r.score?.[row.result_key]; return v ? <span>技术 {v.tech_total ?? '—'}/{v.tech_max} · 商务 {v.biz_total ?? '—'}/{v.biz_max}{v.weighted !== null ? ` · 按权重折算 ${v.weighted}` : ''}</span> : '—' } },
          ]} />
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card size="small" title={`生成的文件（${p.files.length}）`}>
            <Typography.Paragraph type="secondary">草稿用于核对和修改；正式文件需在“准备投标文件”页通过检查后导出。修改资料后，需重新生成或检查。</Typography.Paragraph>
            {p.files.length === 0 ? <Typography.Text type="secondary">尚未生成，请到“准备投标文件”页生成商务和技术文件</Typography.Text> : (
              <Table size="small" rowKey="name" pagination={false} dataSource={p.files}
                columns={[
                  { title: '文件', dataIndex: 'name', ellipsis: true, render: (v: string) => <a href={api.fileUrl(id, v)}>{v.startsWith('正式_') ? '正式件：' : '草稿：'}{v}</a> },
                  { title: '大小', dataIndex: 'size', width: 90, render: (n: number) => `${Math.ceil(n / 1024)} KB` },
                  { title: '修改', dataIndex: 'modified', width: 150, render: fmt },
                ]} />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={`操作记录（${p.events.length}）`} style={{ maxHeight: 480, overflowY: 'auto' }}>
            {p.tasks.filter((t) => t.status === 'running' || t.status === 'queued').map((t) => (
              <Alert key={t.id} type="info" showIcon style={{ marginBottom: 8 }} message={`${taskKindLabel(t.kind)} 进行中 ${Math.round(t.progress * 100)}%`} description={taskMessageLabel(t.message)} />
            ))}
            <Timeline items={p.events.map((e: ProjectEvent) => ({
              color: EVENT_COLOR[e.kind] ?? 'gray',
              children: <span><Typography.Text type="secondary">{fmt(e.created_at)} · {e.actor || 'system'}</Typography.Text> <Tag style={{ marginLeft: 6 }}>{EVENT_CN[e.kind] ?? taskKindLabel(e.kind)}</Tag>{taskMessageLabel(e.message)}</span>,
            }))} />
            {p.events.length === 0 && <Typography.Text type="secondary">暂无操作记录</Typography.Text>}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
