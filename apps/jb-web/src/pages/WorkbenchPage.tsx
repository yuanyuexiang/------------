import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Collapse, Empty, Modal, Progress, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import { api, Finding, ItemScore } from '../api'
import { errorMessage, purchaseWarningLabel, reviewLevelLabel, scoreKindLabel, scoreMethodLabel, taskMessageLabel } from '../uiLabels'
import MaterialPicker from '../components/MaterialPicker'
import PreparationPanel from '../components/PreparationPanel'
import { useProjectWorkspace } from '../components/ProjectWorkspace'
import RequirementsPanel from '../components/RequirementsPanel'
import QualificationPanel from '../components/QualificationPanel'
import OutputPreview from '../components/OutputPreview'

const LEVEL: Record<string, string> = { 否决: 'red', 扣分: 'orange', 建议: 'blue', 需人工: 'purple' }
const VERDICT: Record<string, string> = { satisfied: 'green', deviation: 'red', unknown: 'orange', missing: 'default' }
const VERDICT_CN: Record<string, string> = { satisfied: '满足', deviation: '偏差', unknown: '待确认', missing: '待补充' }

/** 准备投标文件：起草/生成 → 参数表/待补充 → 检查投标文件 → 预估评分 → 查看提交要求 → 导出。 */
export default function WorkbenchPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const { profile, pkgIndex, href, selectionLocked, setSelectionLocked } = useProjectWorkspace()
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const { data: trm } = useQuery({ queryKey: ['trm', id], queryFn: () => api.trm(id, true) })
  const [withDraft, setWithDraft] = useState(true)
  const [taskId, setTaskId] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [requirementsOpen, setRequirementsOpen] = useState(false)
  const [preview, setPreview] = useState<{ filename?: string; finding?: Finding }>()
  const { data: flow, refetch: refreshFlow, error: flowError } = useQuery({
    queryKey: ['workflow', id, profile, pkgIndex],
    queryFn: () => api.workflow(id, profile ?? '', pkgIndex), refetchInterval: 5000,
  })
  const effectiveTaskId = flow?.active_task_id ?? taskId
  const { data: task } = useQuery({
    queryKey: ['task', effectiveTaskId], queryFn: () => api.task(effectiveTaskId!), enabled: !!effectiveTaskId,
    refetchInterval: (q) => ['done', 'failed'].includes(q.state.data?.status ?? '') ? false : 2000,
  })
  const view = searchParams.get('view')
  const step = view === 'review' ? 2 : view === 'generate' ? 1 : 0
  const setStep = (value: number) => setSearchParams(current => {
    const next = new URLSearchParams(current)
    next.set('view', value === 2 ? 'review' : value === 1 ? 'generate' : 'prepare')
    return next
  }, { replace: true })
  const preparationAnchor = useRef<HTMLDivElement>(null)
  const requirementsAnchor = useRef<HTMLDivElement>(null)
  useEffect(() => { if (requirementsOpen) requirementsAnchor.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [requirementsOpen])
  const { data: preparation, error: preparationError, isFetching: preparationLoading } = useQuery({
    queryKey: ['preparation', id, profile, pkgIndex],
    queryFn: () => api.preparation(id, profile!, pkgIndex), enabled: !!profile,
  })
  const readiness = preparation?.readiness
  const gen = flow?.generation
  const generationLabel = gen ? '更新标书' : '生成标书'
  const goToGeneration = () => {
    setStep(0)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  const [issueCategory, setIssueCategory] = useState<string>()
  const review = flow?.review
  const running = busy || (!!effectiveTaskId && !['done', 'failed'].includes(task?.status ?? ''))
  const [score, setScore] = useState<{ items: ItemScore[]; tech_total: number | null; tech_max: number; biz_total: number | null; biz_max: number; weighted: number | null } | null>(null)
  const [matrix, setMatrix] = useState<{ section: string; seq: string; item: string; channels: string[]; port: string; status: string }[]>([])
  useEffect(() => { setTaskId(undefined); setScore(null); setMatrix([]); setPreview(undefined); setRequirementsOpen(false) }, [id, profile, pkgIndex])
  useEffect(() => { setSelectionLocked(running); return () => setSelectionLocked(false) }, [running, setSelectionLocked])
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

  const run = async (allowIncomplete = false, draftEnabled = withDraft) => {
    if (selectionLocked || running) return
    if (!profile) return message.warning('请选择企业档案')
    setBusy(true)
    setScore(null)
    try {
      const { task_id } = await api.generate(id, profile, pkgIndex, draftEnabled, allowIncomplete)
      setTaskId(task_id)
      setStep(1)
      await refreshFlow()
    } catch (e) { message.error(errorMessage(e)) } finally { setBusy(false) }
  }
  const draft = () => Modal.confirm({
    title: '生成待完善草稿',
    content: <><p>以下事项尚未完成，生成稿会保留待补充内容提示，不能直接正式导出。</p>
      <ul>{readiness?.confirmations.map(x => <li key={x.task}>{x.title}：{taskMessageLabel(x.message)}</li>)}
      {readiness?.warnings.map((x, i) => <li key={i}>{x}</li>)}</ul></>,
    okText: '仍生成草稿', cancelText: '继续准备', onOk: () => run(true),
  })
  const repair = () => {
    if (running || !readiness || preparationLoading || preparationError) return message.info('请等待准备状态刷新后重试')
    if (readiness.blockers.length) { setStep(0); return message.warning(`请先核对采购信息：${readiness.blockers.join('；')}`) }
    Modal.confirm({ title: 'AI 更新标书并检查', okText: readiness.ready ? '开始更新' : '生成待完善草稿', cancelText: '继续准备',
      content: <><p>系统将重新检索已选资料、起草并检查本包商务和技术文件，旧版本保留。</p>{!readiness.ready && <><p>以下安排未完成，新版仍为待完善草稿：</p><ul>{readiness.confirmations.map(x => <li key={x.task}>{taskMessageLabel(x.message)}</li>)}</ul></>}<p>完成后进入审阅步骤；正式导出仍需通过检查。</p></>,
      onOk: () => { setWithDraft(true); return run(!readiness.ready, true) },
    })
  }
  const doReview = async () => {
    if (!profile) return
    setBusy(true)
    try { await api.review(id, profile, pkgIndex); await refreshFlow() }
    catch (e) { message.error(errorMessage(e)) } finally { setBusy(false) }
  }
  const doScore = async () => {
    if (!profile) return
    try { setScore((await api.score(id, profile, pkgIndex, withDraft, flow?.generation_id ?? undefined)).report) }
    catch (e) { message.error(errorMessage(e)) }
  }
  const doMatrix = async () => {
    try { setMatrix((await api.submissionMatrix(id, pkgIndex)).rows) }
    catch (e) { message.error(errorMessage(e)) }
  }
  const doExport = async (fn: string) => {
    setBusy(true)
    try {
      const r = await api.exportFile(id, fn)
      if (r.ok) message.success(r.pdf ? '正式 Word 和 PDF 已生成，请使用下方链接下载' : `正式 Word 已生成；${r.notes.join('；')}`)
      else message.error(`暂时无法导出：${r.blocked_by.join('；')}`)
      await refreshFlow()
    } catch (e) { message.error(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Space className="workspace-page" direction="vertical" style={{ width: '100%' }} size="middle">
      {flowError && <Alert type="error" message="无法读取当前审查状态" description={errorMessage(flowError)} />}
      {preparationError && <Alert type="error" message="无法读取准备状态，请刷新重试" description={errorMessage(preparationError)} />}
      {step === 0 && <>
      {!profile && <Alert type="info" showIcon message="请先选择本次投标企业" />}
      <Card size="small" title="本包投标文件" extra={<Space wrap>
        {gen && <Button disabled={running} onClick={() => setStep(2)}>查看已有文件</Button>}
        <Button type="primary" loading={running} disabled={selectionLocked || running || !profile || !readiness || !!preparationError || preparationLoading}
          onClick={() => readiness?.ready ? void run() : readiness?.blockers.length ? nav(href('trm')) : preparationAnchor.current?.scrollIntoView({ behavior: 'smooth' })}>
          {readiness?.ready ? generationLabel : readiness?.blockers.length ? '核对采购信息' : '补充资料'}
        </Button></Space>}>
        <div className="bid-file-grid">{['商务文件', '技术文件'].map((name, i) => <div className="bid-file-summary" key={name}>
          <Typography.Text strong>{name}</Typography.Text>
          <Typography.Paragraph type="secondary">{i === 0 ? '企业信息、授权与证明材料' : '技术响应、实施方案与人员安排'}</Typography.Paragraph>
          <Tag>{gen?.files.some(f => f.includes(i === 0 ? '商务' : '技术')) ? '已有生成文件' : '待生成'}</Tag>
        </div>)}</div>
        {!!readiness?.blockers.length && <Alert style={{ marginTop: 12 }} type="error" message="请先核对采购信息" description={<ul>{readiness.blockers.map((x, i) => <li key={i}>{x}</li>)}</ul>} />}
        {!!readiness?.confirmations.length && <Typography.Paragraph style={{ marginTop: 12 }}>待确认：{readiness.confirmations.map(x => x.title).join('、')}。</Typography.Paragraph>}
        {!readiness?.ready && <Button type="link" disabled={running || !profile || !readiness || !!readiness.blockers.length || !!preparationError || preparationLoading} onClick={draft}>先生成待完善草稿</Button>}
      </Card>
      {profile && <QualificationPanel key={`qualification:${id}:${profile}:${pkgIndex}`} disabled={running} />}
      {!!flow?.preflight?.length && <Alert showIcon type={flow.preflight.some(x => x.blocking) ? 'error' : 'warning'} message="采购文件有事项需要核对"
        action={<Button onClick={() => nav(href('trm'))}>前往核对</Button>} description={<Collapse ghost size="small" items={[{ key: 'details', label: '查看原因', children: <ul>{flow.preflight.map((x, i) => <li key={i}>{purchaseWarningLabel(x.message)}</li>)}</ul> }]} />} />}
      {flow?.stale && <Alert showIcon type="warning" message={running ? "正在处理，请等待标书更新完成" : "资料已更新，标书尚未更新"}
        description={running ? "处理完成后将刷新文件状态。" : "补齐资料后，点击上方“更新标书”。"} />}
      <div ref={preparationAnchor}>
      {profile && <PreparationPanel key={`preparation:${id}:${profile}:${pkgIndex}`} id={id} profile={profile} pkgIndex={pkgIndex} disabled={running} onRepair={repair} onSaved={() => { setScore(null); void refreshFlow() }} />}
      </div>
      {profile && <Collapse items={[{ key: 'materials', label: '选择本包使用的证明材料', children: <MaterialPicker key={`${id}:${profile}:${pkgIndex}`} id={id} profile={profile} pkgIndex={pkgIndex} disabled={running} onSaved={() => { setScore(null); void refreshFlow(); void qc.invalidateQueries({ queryKey: ['preparation', id] }); void qc.invalidateQueries({ queryKey: ['qualification', id] }); void qc.invalidateQueries({ queryKey: ['requirements', id] }) }} /> }]} />}

      <Collapse items={[{ key: 'options', label: '生成设置与详细依据', children: <Space direction="vertical" style={{ width: '100%' }}>
        <Space>AI 起草技术方案<Switch aria-label="技术方案起草" disabled={running} checked={withDraft} onChange={setWithDraft} /></Space>
        {!!readiness?.warnings.length && <ul>{readiness.warnings.map((x, i) => <li key={i}>{x}</li>)}</ul>}
        <Button onClick={() => setRequirementsOpen(true)}>查看采购要求与证据</Button>
        <Button disabled={running} onClick={async () => { setBusy(true); try { const result = await api.reparse(id); setTaskId(result.task_id); await refreshFlow() } catch (e) { message.error(errorMessage(e)) } finally { setBusy(false) } }}>重新解析原文件</Button>
      </Space> }]} />
      </>}
      {step === 1 && <Card title="生成标书">
        <Typography.Paragraph>使用本包已保存的资料生成商务、技术文件。已有版本会保留，生成后进入审阅。</Typography.Paragraph>
        {task && task.status !== 'done' && <><Progress percent={Math.round(task.progress * 100)} status={task.status === 'failed' ? 'exception' : 'active'} /><Typography.Paragraph>{taskMessageLabel(task.message)}</Typography.Paragraph></>}
        {!running && !readiness?.ready && <Alert type="warning" message="准备状态已变化，请返回准备资料核对，或明确生成待完善草稿。" />}
        <Space>
          <Button disabled={running} onClick={() => setStep(0)}>返回准备资料</Button>
          <Button type="primary" onClick={() => void run()} disabled={running || !profile || !readiness?.ready || !!preparationError || preparationLoading}>{generationLabel}</Button>
          {gen && <Button disabled={running} onClick={() => setStep(2)}>审阅已有版本</Button>}
        </Space>
      </Card>}
      <div hidden={step !== 2}>
      {!gen && <Empty description="尚未生成标书，请先完成准备资料"><Button type="primary" onClick={() => setStep(0)}>前往准备资料</Button></Empty>}
      {gen && <>
        <Card size="small" title="本包投标文件" extra={<Button disabled={running} onClick={() => setStep(0)}>修改资料并更新</Button>}>
          <div className="bid-file-grid">{gen.files.map((f) => <div className="bid-file-summary" key={f}>
            <Typography.Text strong>{/商务/.test(f) ? '商务文件' : /技术/.test(f) ? '技术文件' : f}</Typography.Text>
            <Typography.Paragraph type="secondary" ellipsis={{ tooltip: f }}>{f}</Typography.Paragraph>
            <Space wrap><Button onClick={() => setPreview({ filename: f })}>查看文件</Button><a href={api.fileUrl(id, f)}>下载草稿</a>
              <Button disabled={running || !!flowError || !flow || flow.blockers.length > 0} onClick={() => doExport(f)}>导出正式文件</Button></Space>
          </div>)}</div>
          {!!flow?.exports.length && <Space direction="vertical" style={{ marginTop: 16 }}>{flow.exports.map(item => <Space wrap key={item.docx}><a href={api.fileUrl(id, item.docx)}>下载正式 Word：{item.docx}</a>{item.pdf && <a href={api.fileUrl(id, item.pdf)}>下载正式 PDF</a>}</Space>)}</Space>}
        </Card>
        <Card size="small" style={{ marginTop: 16 }} title="文件检查" extra={<Button type="primary" onClick={doReview} loading={running} disabled={!profile || running || flow?.stale}>检查文件{review ? ' / 复查' : ''}</Button>}>
          {flow?.stale ? <Alert type="warning" message="资料已变化，请先更新标书" action={<Button onClick={goToGeneration}>更新标书</Button>} />
            : !review ? <Typography.Text type="secondary">检查当前文件的缺项和投标风险，通过后可导出正式文件。</Typography.Text>
            : <Alert showIcon type={flow?.blockers.length ? 'warning' : 'success'} message={flow?.blockers.length ? '仍有问题需要处理' : '检查已完成，可以导出正式文件'} description={flow?.blockers.length ? <ul>{flow.blockers.map(reason => <li key={reason}>{reason}</li>)}</ul> : undefined} />}
          {gen.generation_mode === 'incomplete_draft' && <Typography.Paragraph type="secondary">本版本为待完善草稿，补齐资料后请更新。</Typography.Paragraph>}
        </Card>
      </>}
      <Collapse style={{ marginTop: 16 }} items={[{ key: 'details', label: '详细核对、评分与提交要求', children: <>
      <Space wrap style={{ marginBottom: 16 }}><Button onClick={() => setRequirementsOpen(true)}>采购要求与证据</Button><Button onClick={doScore} disabled={!profile || running || flow?.stale}>预估评分</Button><Button onClick={doMatrix}>查看提交要求</Button></Space>
      {gen?.llm_connection && <Typography.Text type="secondary">本次使用的 AI 服务：{gen.llm_connection.name} · 模型：{gen.llm_connection.model}</Typography.Text>}
      {gen && (
        <Tabs items={[
          ...(gen.confirmations?.length ? [{ key: 'c', label: `${flow?.stale ? '历史版本核对' : '待核对事项'}（${gen.confirmations.length}）`, children: (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Alert type="info" showIcon message={flow?.stale ? '历史文件问题，仅供查看历史记录；当前待办请返回“准备资料”步骤' : '请核对企业资料，系统会协助修复引用和起草问题'}
                description="系统先处理引用和起草错误；请核对团队资料。完成这些事项后，仍需检查整份投标文件。" />
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
                message={gen.summary.export_blocked ? `文件共 ${gen.summary.todo_count} 处标记，重复问题已在“待核对事项”中合并；不等于缺少同等数量的企业材料` : '无待补充；正式导出还需通过本版本检查投标文件'} />
              {gen.summary.mode && (
                <Typography.Text type="secondary">
                  版式：{Object.values(gen.summary.mode).every((m) => m === 'master') ? '采购文件规定格式（原版式）' : Object.values(gen.summary.mode).every((m) => m === 'plain') ? '系统默认格式（未识别到采购文件规定的格式）' : `商务 ${gen.summary.mode.commercial === 'master' ? '采购规定格式' : '系统默认格式'} / 技术 ${gen.summary.mode.technical === 'master' ? '采购规定格式' : '系统默认格式'}`}
                  {(gen.summary.notes ?? []).length > 0 && <>；{gen.summary.notes!.join('；')}</>}
                </Typography.Text>
              )}
              {gen.files.map((f) => (
                <Space key={f}>
                  <a href={api.fileUrl(id, f)} target="_blank" rel="noreferrer">下载草稿：{f}</a>
                  <Button size="small" onClick={() => setPreview({ filename: f })}>预览内容</Button>
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
          { key: 'p', label: '技术参数是否符合要求', children: (
            <Tabs items={gen.tech_params.map((tp) => ({
              key: tp.spec_id, label: `${tp.spec_id}（${tp.responses.length} 行）`,
              children: (
                <Table size="small" rowKey="row" pagination={{ pageSize: 20 }} dataSource={tp.responses}
                  columns={[
                    { title: '序号', dataIndex: 'row', width: 50 },
                    { title: '采购方要求的参数', dataIndex: 'required', render: (v: string, r) => <>{r.star && <Tag color="red">★</Tag>}{v}</> },
                    { title: '我方提供的参数', dataIndex: 'response', width: 320 },
                    { title: '判定', dataIndex: 'verdict', width: 90, render: (v: string) => <Tag color={VERDICT[v]}>{VERDICT_CN[v] ?? v}</Tag> },
                    { title: '说明', dataIndex: 'reason', width: 260 },
                  ]} />
              ),
            }))} />
          ) },
          ...(Object.keys(gen.draft_sources ?? {}).length ? [{ key: 's', label: '方案采用的资料', children: (
            <Space direction="vertical" style={{ width: '100%' }}>
            {!!gen.evidence_coverage?.length && <Collapse items={[{ key: 'coverage', label: '已识别的附件及尚未核实的内容', children: <ul>{gen.evidence_coverage.map((value, i) => <li key={i}>{value}</li>)}</ul> }]} />}
            <Table size="small" rowKey="id" pagination={{ pageSize: 10 }}
              dataSource={Object.entries(gen.draft_sources ?? {}).map(([id, text]) => ({ id, text }))}
              columns={[{ title: '引用编号', dataIndex: 'id', width: 200 }, { title: '资料 / 招标要求原文', dataIndex: 'text' }]} />
            </Space>
          ) }] : []),
          ...(gen.draft_markdown ? [{ key: 'd', label: '方案草稿（附资料来源）', children: <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{gen.draft_markdown}</pre> }] : []),
        ]} />
      )}

      {score && (
        <Card size="small" title={`预估评分：技术 ${score.tech_total ?? '?'}/${score.tech_max}　商务 ${score.biz_total ?? '?'}/${score.biz_max}　按权重折算（不含价格分）${score.weighted ?? '?'}`}>
          <Table<ItemScore> size="small" rowKey="element" pagination={false} dataSource={score.items}
            columns={[
              { title: '评分项目', dataIndex: 'element', width: 260 }, { title: '类别', dataIndex: 'kind', width: 70, render: scoreKindLabel },
              { title: '预估得分', dataIndex: 'predicted', width: 70, render: (v) => v ?? '—' },
              { title: '评分范围', width: 90, render: (_, r) => `${r.score_min}~${r.score_max}` },
              { title: '估分方式', dataIndex: 'method', width: 150, render: scoreMethodLabel }, { title: '依据', dataIndex: 'basis' },
              { title: '提高评分需补充的材料', dataIndex: 'missing', render: (m: string[]) => m.map((x, i) => <div key={i}>{x}</div>) },
            ]} />
        </Card>
      )}

      {matrix.length > 0 && (
        <Card size="small" title="本包投标文件怎么提交">
          <Table size="small" rowKey={(_, i) => String(i)} pagination={false} dataSource={matrix}
            columns={[
              { title: '文件类别', dataIndex: 'section', width: 150 }, { title: '序号', dataIndex: 'seq', width: 60 }, { title: '提交材料', dataIndex: 'item' },
              { title: '提交渠道', dataIndex: 'channels', width: 180, render: (c: string[]) => c.map((x) => <Tag key={x}>{x}</Tag>) },
              { title: '投标工具上传位置', dataIndex: 'port', width: 220 },
              { title: '状态', dataIndex: 'status', width: 150, render: (s: string) => <Tag color={s.startsWith('系统') ? 'green' : s.startsWith('工具') ? 'blue' : 'orange'}>{s}</Tag> },
            ]} />
        </Card>
      )}
      </> }]} />
      {review && review.findings.length > 0 && (
        <Card size="small" title={<Space><span>{flow?.stale ? '上次文件问题（历史参考）' : '需要核对的问题'}</span><Tag color={review.blocked ? 'red' : 'green'}>{review.blocked ? '有投标无效风险' : '未发现投标无效风险'}</Tag><Typography.Text type="secondary"></Typography.Text>{Object.entries(review.counts).map(([k, v]) => <Tag key={k} color={LEVEL[k]}>{reviewLevelLabel(k)} {v}</Tag>)}</Space>}>
          <Table<Finding> size="small" rowKey={(_, i) => String(i)} pagination={{ pageSize: 15 }} dataSource={review.findings}
            columns={[
              { title: '级别', dataIndex: 'level', width: 110, render: (v: string) => <Tag color={LEVEL[v]}>{reviewLevelLabel(v)}</Tag> },
              { title: '问题', dataIndex: 'title', width: 220 },
              { title: '说明', dataIndex: 'message' }, { title: '位置', dataIndex: 'location', width: 160 },
              { title: '核查', width: 100, render: (_, finding) => <Button size="small" onClick={() => setPreview({ finding, filename: gen?.files.find(file => finding.location.includes(file)) })}>对照文件</Button> },
            ]} />
        </Card>
      )}

      </div>
      {(requirementsOpen || searchParams.has('requirement')) && <div ref={requirementsAnchor}>
        <Button style={{ marginBottom: 8 }} onClick={() => { setRequirementsOpen(false); setSearchParams(current => { const next = new URLSearchParams(current); next.delete('requirement'); return next }, { replace: true }) }}>收起详细要求</Button>
        <RequirementsPanel key={`requirements:${id}:${profile}:${pkgIndex}`} />
      </div>}

      {preview && profile && gen && <OutputPreview key={`${flow?.generation_id}:${preview.filename}:${preview.finding?.rule_id}`} id={id} profile={profile} pkgIndex={pkgIndex} files={gen.files} filename={preview.filename} finding={preview.finding} onClose={() => setPreview(undefined)} />}
    </Space>
  )
}
