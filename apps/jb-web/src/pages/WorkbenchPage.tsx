import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Progress, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import { api, Finding, GenResult, ItemScore, Task } from '../api'

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
  const [task, setTask] = useState<Task | null>(null)
  const [gen, setGen] = useState<GenResult | null>(null)
  const [review, setReview] = useState<{ blocked: boolean; counts: Record<string, number>; findings: Finding[] } | null>(null)
  const [score, setScore] = useState<{ items: ItemScore[]; tech_total: number | null; tech_max: number; biz_total: number | null; biz_max: number; weighted: number | null } | null>(null)
  const [matrix, setMatrix] = useState<{ section: string; seq: string; item: string; channels: string[]; port: string; status: string }[]>([])
  const timer = useRef<number | null>(null)
  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current) }, [])

  const run = async () => {
    if (!profile) return message.warning('请选择企业档案')
    try {
      const { task_id } = await api.generate(id, profile, pkgIndex, withDraft)
      setGen(null)
      timer.current = window.setInterval(async () => {
        const t = await api.task(task_id)
        setTask(t)
        if (t.status === 'done' || t.status === 'failed') {
          if (timer.current) window.clearInterval(timer.current)
          if (t.status === 'done') { setGen(t.result as unknown as GenResult); message.success('生成完成') } else message.error(t.message)
        }
      }, 2000)
    } catch (e) { message.error(String(e)) }
  }
  const doReview = async () => { if (profile) setReview(await api.review(id, profile, pkgIndex)) }
  const doScore = async () => { if (profile) setScore((await api.score(id, profile, pkgIndex, withDraft, task?.id)).report) }
  const doMatrix = async () => setMatrix((await api.submissionMatrix(id, pkgIndex)).rows)
  const doExport = async (fn: string) => {
    const r = await api.exportFile(id, fn)
    r.ok ? message.success(`已导出：${r.notes.join('；')}`) : message.error(`阻断：${r.blocked_count} 处待补充，如「${r.blocked_by[0]}」`)
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card size="small">
        <Space wrap>
          <Select placeholder="企业档案" style={{ width: 260 }} value={profile} onChange={setProfile} options={profiles.map((p) => ({ value: p.name, label: p.name }))} />
          <Select style={{ width: 320 }} value={pkgIndex} onChange={setPkgIndex}
            options={(trm?.packages ?? []).map((p, i) => ({ value: i, label: `${p.sub_no} ${p.sub_name} ${p.pkg_no}`.trim() }))} />
          <span>LLM 起草技术方案 <Switch checked={withDraft} onChange={setWithDraft} /></span>
          <Button type="primary" onClick={run} disabled={task?.status === 'running'}>生成商务/技术文件</Button>
          <Button onClick={doReview} disabled={!gen}>合规审查</Button>
          <Button onClick={doScore} disabled={!gen}>模拟评分</Button>
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

      {gen && (
        <Tabs items={[
          { key: 'f', label: '文件与待补充', children: (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert type={gen.summary.export_blocked ? 'warning' : 'success'}
                message={gen.summary.export_blocked ? `共 ${gen.summary.todo_count} 处【待补充】，补齐前禁止导出` : '无待补充，可导出'} />
              {gen.files.map((f) => (
                <Space key={f}>
                  <a href={api.fileUrl(id, f)} target="_blank" rel="noreferrer">{f}</a>
                  <Button size="small" onClick={() => doExport(f)}>导出（清元数据+PDF）</Button>
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
        <Card size="small" title={<Space><span>合规审查</span><Tag color={review.blocked ? 'red' : 'green'}>{review.blocked ? '存在否决项' : '无否决项'}</Tag>{Object.entries(review.counts).map(([k, v]) => <Tag key={k} color={LEVEL[k]}>{k} {v}</Tag>)}</Space>}>
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
