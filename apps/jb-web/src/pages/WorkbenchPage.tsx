import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Progress, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import { api, Finding, ItemScore } from '../api'

const LEVEL: Record<string, string> = { 否决: 'red', 扣分: 'orange', 建议: 'blue', 需人工: 'purple' }
const VERDICT: Record<string, string> = { satisfied: 'green', deviation: 'red', unknown: 'orange', missing: 'default' }
const VERDICT_CN: Record<string, string> = { satisfied: '满足', deviation: '偏差', unknown: '待确认', missing: '待补充' }

/** 生成与审查工作台：起草/生成 → 参数表/待补充 → 合规审查 → 模拟评分 → 递交矩阵 → 导出。 */
export default function WorkbenchPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const { data: trm } = useQuery({ queryKey: ['trm', id], queryFn: () => api.trm(id, true) })
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const [profile, setProfile] = useState<string>()
  const [pkgIndex, setPkgIndex] = useState(0)
  const [withDraft, setWithDraft] = useState(false)
  const [taskId, setTaskId] = useState<string>()
  const [busy, setBusy] = useState(false)
  const { data: flow, refetch: refreshFlow, error: flowError } = useQuery({
    queryKey: ['workflow', id, profile, pkgIndex],
    queryFn: () => api.workflow(id, profile ?? '', pkgIndex), refetchInterval: 5000,
  })
  const effectiveTaskId = flow?.active_task_id ?? taskId
  const { data: task } = useQuery({
    queryKey: ['task', effectiveTaskId], queryFn: () => api.task(effectiveTaskId!), enabled: !!effectiveTaskId,
    refetchInterval: (q) => ['done', 'failed'].includes(q.state.data?.status ?? '') ? false : 2000,
  })
  const gen = flow?.generation
  const review = flow?.review
  const running = busy || (!!effectiveTaskId && !['done', 'failed'].includes(task?.status ?? ''))
  const [score, setScore] = useState<{ items: ItemScore[]; tech_total: number | null; tech_max: number; biz_total: number | null; biz_max: number; weighted: number | null } | null>(null)
  const [matrix, setMatrix] = useState<{ section: string; seq: string; item: string; channels: string[]; port: string; status: string }[]>([])
  useEffect(() => { if (!profile && flow?.profile) setProfile(flow.profile) }, [profile, flow?.profile])
  useEffect(() => { setTaskId(undefined); setScore(null); setMatrix([]) }, [id, profile, pkgIndex])
  useEffect(() => {
    if (task?.status === 'done' || task?.status === 'failed') void refreshFlow()
  }, [task?.status, refreshFlow])

  const run = async () => {
    if (!profile) return message.warning('请选择企业档案')
    setBusy(true)
    setScore(null)
    try {
      const { task_id } = await api.generate(id, profile, pkgIndex, withDraft)
      setTaskId(task_id)
      await refreshFlow()
    } catch (e) { message.error(String(e)) } finally { setBusy(false) }
  }
  const doReview = async () => {
    if (!profile) return
    setBusy(true)
    try { await api.review(id, profile, pkgIndex); await refreshFlow() }
    catch (e) { message.error(String(e)) } finally { setBusy(false) }
  }
  const doScore = async () => {
    if (!profile) return
    try { setScore((await api.score(id, profile, pkgIndex, withDraft, flow?.generation_id ?? undefined)).report) }
    catch (e) { message.error(String(e)) }
  }
  const doMatrix = async () => {
    try { setMatrix((await api.submissionMatrix(id, pkgIndex)).rows) }
    catch (e) { message.error(String(e)) }
  }
  const doExport = async (fn: string) => {
    setBusy(true)
    try {
      const r = await api.exportFile(id, fn)
      if (r.ok) message.success(r.pdf ? '正式 Word 和 PDF 已生成，请使用下方链接下载' : `正式 Word 已生成；${r.notes.join('；')}`)
      else message.error(`导出被阻断：${r.blocked_by.join('；')}`)
      await refreshFlow()
    } catch (e) { message.error(String(e)) } finally { setBusy(false) }
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <Select placeholder="企业档案" style={{ width: 260 }} disabled={running} value={profile} onChange={setProfile} options={profiles.map((p) => ({ value: p.name, label: p.name }))} />
          <Select style={{ width: 320 }} disabled={running} value={pkgIndex} onChange={setPkgIndex}
            options={(trm?.packages ?? []).map((p, i) => ({ value: i, label: `${p.sub_no} ${p.sub_name} ${p.pkg_no}`.trim() }))} />
          <span>LLM 起草技术方案 <Switch checked={withDraft} onChange={setWithDraft} /></span>
          <Button type="primary" onClick={run} disabled={running || !profile}>生成商务/技术文件</Button>
          <Button onClick={doReview} disabled={!gen || !profile || running}>合规审查 / 复查</Button>
          <Button onClick={doScore} disabled={!gen || !profile || running}>模拟评分</Button>
          <Button onClick={doMatrix}>递交矩阵</Button>
          <Button onClick={() => nav(`/projects/${id}`)}>返回</Button>
        </Space>
        {task && task.status !== 'done' && (
          <div style={{ marginTop: 12 }}>
            <Progress percent={Math.round(task.progress * 100)} status={task.status === 'failed' ? 'exception' : 'active'} />
            <Typography.Text type="secondary">{task.message}</Typography.Text>
          </div>
        )}
      </Card>

      {flowError && <Alert type="error" message="无法读取当前审查状态" description={String(flowError)} />}
      {flow && <Card size="small" title="整改与正式导出">
        <Alert showIcon type={flow.blockers.length ? 'warning' : 'success'}
          message={flow.blockers.length ? '正式导出尚未就绪' : '本版本审查有效，可以正式导出'}
          description={flow.blockers.length ? <ul>{flow.blockers.map((reason) => <li key={reason}>{reason}</li>)}</ul> : '导出前仍会重新核对资料、规则和文件版本。'} />
        <Space wrap style={{ marginTop: 12 }}>
          <Button onClick={() => nav(`/projects/${id}/trm`)}>1. 核对招标要求</Button>
          <Button disabled={!profile} onClick={() => nav(`/kb/${encodeURIComponent(profile ?? '')}`)}>2. 补齐企业资料</Button>
          <Button disabled={running || !profile} onClick={run}>3. 重新生成</Button>
          <Button disabled={running || !gen || !profile} onClick={doReview}>4. 复查本版本</Button>
        </Space>
        {flow.exports.map((item) => <div key={item.docx} style={{ marginTop: 8 }}>
          <Space><a href={api.fileUrl(id, item.docx)}>下载正式 Word</a>
            {item.pdf && <a href={api.fileUrl(id, item.pdf)}>下载正式 PDF</a>}</Space>
        </div>)}
      </Card>}

      {gen && (
        <Tabs items={[
          { key: 'f', label: '文件与待补充', children: (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert type={gen.summary.export_blocked ? 'warning' : 'success'}
                message={gen.summary.export_blocked ? `共 ${gen.summary.todo_count} 处【待补充】，请补齐后重新生成` : '无待补充；正式导出还需通过本版本合规审查'} />
              {gen.files.map((f) => (
                <Space key={f}>
                  <a href={api.fileUrl(id, f)} target="_blank" rel="noreferrer">下载草稿：{f}</a>
                  <Button size="small" disabled={running || !!flowError || !flow || flow.blockers.length > 0} onClick={() => doExport(f)}>正式导出（Word / PDF）</Button>
                  <Typography.Text type="secondary">待补充 {(gen.todos[f] ?? []).length} 处</Typography.Text>
                </Space>
              ))}
              {Object.entries(gen.todos).map(([f, list]) => list.length > 0 && (
                <Card key={f} size="small" title={`${f} 待补充清单`}>
                  <ul style={{ margin: 0, paddingLeft: 20, columns: 2 }}>{list.slice(0, 60).map((t, i) => <li key={i}>{t}</li>)}</ul>
                  {list.length > 60 && <Typography.Text type="secondary">…共 {list.length} 处</Typography.Text>}
                </Card>
              ))}
            </Space>
          ) },
          { key: 'p', label: '技术参数响应', children: (
            <Tabs items={gen.tech_params.map((tp) => ({
              key: tp.spec_id, label: `${tp.spec_id}（${tp.responses.length} 行）`,
              children: (
                <Table size="small" rowKey="row" pagination={{ pageSize: 20 }} dataSource={tp.responses}
                  columns={[
                    { title: '#', dataIndex: 'row', width: 50 },
                    { title: '项目需求值', dataIndex: 'required', render: (v: string, r) => <>{r.star && <Tag color="red">★</Tag>}{v}</> },
                    { title: '投标人保证值', dataIndex: 'response', width: 320 },
                    { title: '判定', dataIndex: 'verdict', width: 90, render: (v: string) => <Tag color={VERDICT[v]}>{VERDICT_CN[v] ?? v}</Tag> },
                    { title: '说明', dataIndex: 'reason', width: 260 },
                  ]} />
              ),
            }))} />
          ) },
          ...(gen.draft_markdown ? [{ key: 'd', label: '起草稿（带溯源）', children: <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{gen.draft_markdown}</pre> }] : []),
        ]} />
      )}

      {review && (
        <Card size="small" title={<Space><span>合规审查</span><Tag color={review.blocked ? 'red' : 'green'}>{review.blocked ? '存在否决项' : '无否决项'}</Tag><Typography.Text type="secondary">生成版本 {review.generation_id}</Typography.Text>{Object.entries(review.counts).map(([k, v]) => <Tag key={k} color={LEVEL[k]}>{k} {v}</Tag>)}</Space>}>
          <Table<Finding> size="small" rowKey={(_, i) => String(i)} pagination={{ pageSize: 15 }} dataSource={review.findings}
            columns={[
              { title: '级别', dataIndex: 'level', width: 80, render: (v: string) => <Tag color={LEVEL[v]}>{v}</Tag> },
              { title: '规则', dataIndex: 'rule_id', width: 90 }, { title: '问题', dataIndex: 'title', width: 220 },
              { title: '说明', dataIndex: 'message' }, { title: '位置', dataIndex: 'location', width: 160 }, { title: '依据', dataIndex: 'source', width: 150 },
            ]} />
        </Card>
      )}

      {score && (
        <Card size="small" title={`模拟评分：技术 ${score.tech_total ?? '?'}/${score.tech_max}　商务 ${score.biz_total ?? '?'}/${score.biz_max}　加权（不含价格）${score.weighted ?? '?'}`}>
          <Table<ItemScore> size="small" rowKey="element" pagination={false} dataSource={score.items}
            columns={[
              { title: '要素', dataIndex: 'element', width: 260 }, { title: '类别', dataIndex: 'kind', width: 60 },
              { title: '预测', dataIndex: 'predicted', width: 70, render: (v) => v ?? '—' },
              { title: '区间', width: 90, render: (_, r) => `${r.score_min}~${r.score_max}` },
              { title: '方法', dataIndex: 'method', width: 70 }, { title: '依据', dataIndex: 'basis' },
              { title: '缺证据（提分路径）', dataIndex: 'missing', render: (m: string[]) => m.map((x, i) => <div key={i}>{x}</div>) },
            ]} />
        </Card>
      )}

      {matrix.length > 0 && (
        <Card size="small" title="递交矩阵（第六章提交方式表 × 本包）">
          <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={matrix}
            columns={[
              { title: '文件', dataIndex: 'section', width: 150 }, { title: '序号', dataIndex: 'seq', width: 60 }, { title: '内容', dataIndex: 'item' },
              { title: '渠道', dataIndex: 'channels', width: 180, render: (c: string[]) => c.map((x) => <Tag key={x}>{x}</Tag>) },
              { title: '端口', dataIndex: 'port', width: 220 },
              { title: '状态', dataIndex: 'status', width: 150, render: (s: string) => <Tag color={s.startsWith('系统') ? 'green' : s.startsWith('工具') ? 'blue' : 'orange'}>{s}</Tag> },
            ]} />
        </Card>
      )}
    </Space>
  )
}
