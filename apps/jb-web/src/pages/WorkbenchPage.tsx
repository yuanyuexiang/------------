import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Collapse, Empty, Modal, Progress, Select, Space, Steps, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import { api, Finding, ItemScore } from '../api'
import MaterialPicker from '../components/MaterialPicker'
import PreparationPanel from '../components/PreparationPanel'

const LEVEL: Record<string, string> = { 否决: 'red', 扣分: 'orange', 建议: 'blue', 需人工: 'purple' }
const VERDICT: Record<string, string> = { satisfied: 'green', deviation: 'red', unknown: 'orange', missing: 'default' }
const VERDICT_CN: Record<string, string> = { satisfied: '满足', deviation: '偏差', unknown: '待确认', missing: '待补充' }

/** 生成与审查工作台：起草/生成 → 参数表/待补充 → 合规审查 → 模拟评分 → 递交矩阵 → 导出。 */
export default function WorkbenchPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: trm } = useQuery({ queryKey: ['trm', id], queryFn: () => api.trm(id, true) })
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles })
  const [profile, setProfile] = useState<string>()
  const [pkgIndex, setPkgIndex] = useState(0)
  const [withDraft, setWithDraft] = useState(true)
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
  const [step, setStep] = useState(0)
  const preparationAnchor = useRef<HTMLDivElement>(null)
  const { data: preparation, error: preparationError, isFetching: preparationLoading } = useQuery({
    queryKey: ['preparation', id, profile, pkgIndex],
    queryFn: () => api.preparation(id, profile!, pkgIndex), enabled: !!profile,
  })
  const readiness = preparation?.readiness
  const gen = flow?.generation
  const generationLabel = gen ? '更新标书' : '生成标书'
  const goToGeneration = () => {
    setStep(readiness?.ready ? 1 : 0)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  const [issueCategory, setIssueCategory] = useState<string>()
  const review = flow?.review
  const running = busy || (!!effectiveTaskId && !['done', 'failed'].includes(task?.status ?? ''))
  const [score, setScore] = useState<{ items: ItemScore[]; tech_total: number | null; tech_max: number; biz_total: number | null; biz_max: number; weighted: number | null } | null>(null)
  const [matrix, setMatrix] = useState<{ section: string; seq: string; item: string; channels: string[]; port: string; status: string }[]>([])
  useEffect(() => { if (!profile && flow?.profile) setProfile(flow.profile) }, [profile, flow?.profile])
  useEffect(() => { setTaskId(undefined); setScore(null); setMatrix([]); setStep(0) }, [id, profile, pkgIndex])
  useEffect(() => {
    if (task?.kind === 'generate' && ['queued', 'running'].includes(task.status)) setStep(1)
    if (task?.status === 'done' || task?.status === 'failed') {
      void refreshFlow()
      if (task?.status === 'done' && task.kind === 'generate') setStep(2)
      void qc.invalidateQueries({ queryKey: ['trm', id] })
      void qc.invalidateQueries({ queryKey: ['relationship', id] })
      void qc.invalidateQueries({ queryKey: ['preparation', id] })
    }
  }, [task?.status, task?.kind, refreshFlow, qc, id])

  const run = async (allowIncomplete = false) => {
    if (!profile) return message.warning('请选择企业档案')
    setBusy(true)
    setScore(null)
    try {
      const { task_id } = await api.generate(id, profile, pkgIndex, withDraft, allowIncomplete)
      setTaskId(task_id)
      setStep(1)
      await refreshFlow()
    } catch (e) { message.error(String(e)) } finally { setBusy(false) }
  }
  const draft = () => Modal.confirm({
    title: '生成待完善草稿',
    content: <><p>以下事项尚未完成，生成稿会保留缺项提示，不能直接正式导出。</p>
      <ul>{readiness?.confirmations.map(x => <li key={x.task}>{x.title}：{x.message}</li>)}
      {readiness?.warnings.map((x, i) => <li key={i}>{x}</li>)}</ul></>,
    okText: '仍生成草稿', cancelText: '继续准备', onOk: () => run(true),
  })
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
      <Card size="small" title="本次投标" className="workbench-controls">
        <div className="workbench-inputs">
          <div><label htmlFor="workbench-profile">企业档案</label><Select id="workbench-profile" placeholder="请选择企业档案" disabled={running} value={profile} onChange={setProfile} options={profiles.map((p) => ({ value: p.name, label: p.name }))} /></div>
          <div><label htmlFor="workbench-package">本次分包</label><Select id="workbench-package" placeholder="请选择分包" disabled={running} value={pkgIndex} onChange={setPkgIndex}
            options={(trm?.packages ?? []).map((p, i) => ({ value: i, label: `${p.pkg_no} ${p.project_name || p.sub_name || "分包信息待解析"}`.trim() }))} /></div>
          <div className="workbench-draft"><span>技术方案起草<small>AI 先写方案，人工核对事实与承诺</small></span><Switch aria-label="技术方案起草" disabled={running} checked={withDraft} onChange={setWithDraft} /></div>
        </div>
        <Space style={{ marginTop: 16 }}>
          <Button onClick={() => nav(`/projects/${id}/trm`)}>核对招标要求</Button>
          <Button disabled={running} onClick={async () => {
            setBusy(true)
            try { const result = await api.reparse(id); setTaskId(result.task_id); await refreshFlow() }
            catch (e) { message.error(String(e)) } finally { setBusy(false) }
          }}>重新解析原文件</Button>
          <Button onClick={() => nav(`/projects/${id}`)}>返回项目</Button>
        </Space>
      </Card>
      <Steps current={step} onChange={value => { if (value === 1) goToGeneration(); else setStep(value) }}
        items={[{ title: '准备资料' }, { title: '生成标书', disabled: running && step !== 1 },
          { title: '审阅与导出', disabled: !gen }]} />
      {flowError && <Alert type="error" message="无法读取当前审查状态" description={String(flowError)} />}
      {preparationError && <Alert type="error" message="无法读取准备状态，请刷新重试" description={String(preparationError)} />}
      {step === 0 && <>
      {!!flow?.preflight?.length && <Alert showIcon type={flow.preflight.some(x => x.blocking) ? 'error' : 'warning'}
        message="生成前检查" description={<ul>{flow.preflight.map((x, i) => <li key={i}>{x.message} — {x.action}</li>)}</ul>} />}
      {flow?.stale && <Alert showIcon type="warning" message={running ? "正在处理，请等待标书更新完成" : "资料已更新，标书尚未更新"}
        description={running ? "处理完成后将刷新文件状态；下方旧文件仅供追溯。" : "可继续处理其他资料，完成后进入“生成标书”步骤。下方旧文件及其问题仅供追溯，不代表当前资料缺口。"} />}
      <div ref={preparationAnchor}>
      {profile && <PreparationPanel key={`preparation:${id}:${profile}:${pkgIndex}`} id={id} profile={profile} pkgIndex={pkgIndex} disabled={running} onGoToGeneration={goToGeneration} onSaved={() => { setScore(null); void refreshFlow() }} />}
      </div>
      {profile && <MaterialPicker key={`${id}:${profile}:${pkgIndex}`} id={id} profile={profile} pkgIndex={pkgIndex} disabled={running} onSaved={() => { setScore(null); void refreshFlow(); void qc.invalidateQueries({ queryKey: ['preparation', id] }) }} />}

      <Card size="small" title="准备检查">
        {!profile ? <Empty description="请先选择企业档案与标包" /> : !readiness ? <Typography.Text>正在检查准备状态…</Typography.Text> : <Space direction="vertical" style={{ width: '100%' }}>
          <Alert showIcon type={readiness.blockers.length ? 'error' : readiness.confirmations.length ? 'warning' : 'success'}
            message={readiness.blockers.length ? '请先解决招标文件问题' : readiness.confirmations.length ? `还有 ${readiness.confirmations.length} 项本次安排需要确认` : '本次安排已确认，可以生成标书'}
            description={<><ul>{readiness.blockers.map((x, i) => <li key={i}>{x}</li>)}
              {readiness.confirmations.map(x => <li key={x.task}>{x.title}：{x.message}</li>)}</ul>
              <span>准备检查不等于资格通过；证明材料和生成内容仍需审阅。</span></>} />
          {!!readiness.warnings.length && <Collapse items={[{ key: 'warnings', label: '资料与原文提醒（不强制阻止生成草稿）', children: <ul>{readiness.warnings.map((x, i) => <li key={i}>{x}</li>)}</ul> }]} />}
        </Space>}
        <Space style={{ marginTop: 16 }}>
          <Button type="primary" disabled={running || !readiness || !!preparationError || preparationLoading} onClick={() => readiness?.ready ? setStep(1) : readiness?.blockers.length ? nav(`/projects/${id}/trm`) : preparationAnchor.current?.scrollIntoView({ behavior: 'smooth' })}>
            {readiness?.ready ? '下一步：生成标书' : readiness?.blockers.length ? '核对招标要求' : '继续完善资料'}
          </Button>
          <Button disabled={running || !readiness || !!readiness.blockers.length || !!preparationError || preparationLoading} onClick={draft}>生成待完善草稿</Button>
        </Space>
      </Card>
      </>}
      {step === 1 && <Card title="生成标书">
        <Typography.Paragraph>使用本包已保存的资料生成商务、技术文件。已有版本会保留，生成后进入审阅。</Typography.Paragraph>
        {task && task.status !== 'done' && <><Progress percent={Math.round(task.progress * 100)} status={task.status === 'failed' ? 'exception' : 'active'} /><Typography.Paragraph>{task.message}</Typography.Paragraph></>}
        {!running && !readiness?.ready && <Alert type="warning" message="准备状态已变化，请返回准备资料核对，或明确生成待完善草稿。" />}
        <Space>
          <Button disabled={running} onClick={() => setStep(0)}>返回准备资料</Button>
          <Button type="primary" onClick={() => void run()} disabled={running || !profile || !readiness?.ready || !!preparationError || preparationLoading}>{generationLabel}</Button>
          {gen && <Button disabled={running} onClick={() => setStep(2)}>审阅已有版本</Button>}
        </Space>
      </Card>}
      <div hidden={step !== 2}>
      {!gen && <Empty description="尚未生成标书，请先完成准备资料" />}
      {gen && <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => setStep(0)}>返回准备资料</Button>
        <Button type="primary" onClick={doReview} disabled={!profile || running || flow?.stale}>合规审查 / 复查</Button>
        <Button onClick={doScore} disabled={!profile || running || flow?.stale}>模拟评分</Button>
        <Button onClick={doMatrix}>递交矩阵</Button>
      </Space>}
      {flow?.stale && <Alert type="warning" showIcon message="资料已变化，以下旧版本仅供追溯" description="请返回准备资料处理受影响事项，再更新标书。" />}
      {gen?.generation_mode === 'incomplete_draft' && <Alert type="info" showIcon message="本版本为提前生成的待完善草稿" description="请核对准备事项和文件缺口，补齐后更新标书并重新审查。" />}
      {flow && <Card size="small" title="整改与正式导出">
        <Alert showIcon type={flow.blockers.length ? 'warning' : 'success'}
          message={flow.blockers.length ? '正式导出尚未就绪' : '本版本审查有效，可以正式导出'}
          description={flow.blockers.length ? <ul>{flow.blockers.map((reason) => <li key={reason}>{reason}</li>)}</ul> : '导出前仍会重新核对资料、规则和文件版本。'} />
        <Space wrap style={{ marginTop: 12 }}>
          <Button onClick={() => nav(`/projects/${id}/trm`)}>1. 核对招标要求</Button>
          <Button disabled={!profile} onClick={() => nav(`/kb/${encodeURIComponent(profile ?? '')}`)}>2. 补齐企业资料</Button>
          <Button disabled={running || !profile} onClick={goToGeneration}>3. 前往{generationLabel}</Button>
          <Button disabled={running || !gen || !profile} onClick={doReview}>4. 复查本版本</Button>
        </Space>
        {flow.exports.map((item) => <div key={item.docx} style={{ marginTop: 8 }}>
          <Space><a href={api.fileUrl(id, item.docx)}>下载正式 Word</a>
            {item.pdf && <a href={api.fileUrl(id, item.pdf)}>下载正式 PDF</a>}</Space>
        </div>)}
      </Card>}

      {gen?.llm_connection && <Typography.Text type="secondary">本次生成连接：{gen.llm_connection.name} · 模型：{gen.llm_connection.model}</Typography.Text>}
      {gen && (
        <Tabs items={[
          ...(gen.confirmations?.length ? [{ key: 'c', label: `${flow?.stale ? '历史版本核对' : '集中核对'}（${gen.confirmations.length}）`, children: (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert type="info" showIcon message={flow?.stale ? '历史文件问题，仅供追溯；当前待办请返回“准备资料”步骤' : '企业事实与系统修复分开处理'}
                description="引用及生成错误由系统先修复；团队资料集中核对一次。此清单不替代合规审查。" />
              <Select allowClear placeholder="全部问题类型" style={{ minWidth: 220 }} value={issueCategory} onChange={setIssueCategory}
                options={[...new Set(gen.confirmations.map(x => x.category))].map(category => ({ value: category, label: `${category}（${gen.confirmations!.filter(x => x.category === category).length}）` }))} />
              <Table size="small" rowKey={(_, i) => String(i)} dataSource={gen.confirmations.filter(x => !issueCategory || x.category === issueCategory)} pagination={{ pageSize: 15 }}
                columns={[
                  { title: '类型', dataIndex: 'category', width: 160 },
                  { title: '章节 / 文件', dataIndex: 'location', width: 220 },
                  { title: '核对事项', dataIndex: 'message' },
                  { title: '出现次数', dataIndex: 'occurrences', width: 85, render: (v) => v ?? 1 },
                  { title: '处理方式', dataIndex: 'action' },
                ]} />
            </Space>
          ) }] : []),
          { key: 'f', label: '文件与问题位置', children: (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert type={gen.summary.export_blocked ? 'warning' : 'success'}
                message={gen.summary.export_blocked ? `文件共 ${gen.summary.todo_count} 处标记，重复问题已在集中核对中合并；不等于缺少同等数量的企业材料` : '无待补充；正式导出还需通过本版本合规审查'} />
              {gen.summary.mode && (
                <Typography.Text type="secondary">
                  版式：{Object.values(gen.summary.mode).every((m) => m === 'master') ? '采购文件规定格式（原版式）' : Object.values(gen.summary.mode).every((m) => m === 'plain') ? '系统自建版式（未取到母版）' : `商务 ${gen.summary.mode.commercial === 'master' ? '母版' : '自建'} / 技术 ${gen.summary.mode.technical === 'master' ? '母版' : '自建'}`}
                  {(gen.summary.notes ?? []).length > 0 && <>；{gen.summary.notes!.join('；')}</>}
                </Typography.Text>
              )}
              {gen.files.map((f) => (
                <Space key={f}>
                  <a href={api.fileUrl(id, f)} target="_blank" rel="noreferrer">下载草稿：{f}</a>
                  <Button size="small" disabled={running || !!flowError || !flow || flow.blockers.length > 0} onClick={() => doExport(f)}>正式导出（Word / PDF）</Button>
                  <Typography.Text type="secondary">待补充 {(gen.todos[f] ?? []).length} 处</Typography.Text>
                </Space>
              ))}
              {Object.entries(gen.todos).map(([f, list]) => list.length > 0 && (
                <Card key={f} size="small" title={`${f} 待补充清单`}>
                  <ul style={{ margin: 0, paddingLeft: 20, columns: 2 }}>{[...new Set(list)].map((t, i) => <li key={i}>{t}{list.filter(x => x === t).length > 1 ? `（${list.filter(x => x === t).length}处）` : ""}</li>)}</ul>
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
          ...(Object.keys(gen.draft_sources ?? {}).length ? [{ key: 's', label: '起草引用依据', children: (
            <Space direction="vertical" style={{ width: '100%' }}>
            {!!gen.evidence_coverage?.length && <Collapse items={[{ key: 'coverage', label: '附件识别范围与未核验部分', children: <ul>{gen.evidence_coverage.map((value, i) => <li key={i}>{value}</li>)}</ul> }]} />}
            <Table size="small" rowKey="id" pagination={{ pageSize: 10 }}
              dataSource={Object.entries(gen.draft_sources ?? {}).map(([id, text]) => ({ id, text }))}
              columns={[{ title: '引用编号', dataIndex: 'id', width: 200 }, { title: '资料 / 招标要求原文', dataIndex: 'text' }]} />
            </Space>
          ) }] : []),
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
      </div>
    </Space>
  )
}
