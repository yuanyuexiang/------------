import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Checkbox, Collapse, Drawer, Form, Input, Select, Space, Table, Tag, Typography, message } from 'antd'
import { api, FactSuggestions, PreparationState, BidMember, Person } from '../api'
import CompanyFactsFields, { STAT_FIELDS } from './CompanyFactsFields'
import RelationshipConfirmation from './RelationshipConfirmation'

const LABELS: Record<string, string> = { ...Object.fromEntries(STAT_FIELDS), staff_as_of: '统计日期', staff_source: '统计依据', signed_date: '合同签约日期', shareholders: '股东出资明细' }
export default function PreparationPanel({ id, profile, pkgIndex, disabled, onSaved, onGenerate }: {
  id: string; profile: string; pkgIndex: number; disabled: boolean; onSaved: () => void; onGenerate: () => Promise<void>
}) {
  const qc = useQueryClient()
  const { data, error, refetch } = useQuery({ queryKey: ['preparation', id, profile, pkgIndex], queryFn: () => api.preparation(id, profile, pkgIndex), refetchInterval: 15000 })
  const [editor, setEditor] = useState<{ kind: string; snapshot: PreparationState }>()
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const [suggestionTask, setSuggestionTask] = useState<string>()
  const [suggesting, setSuggesting] = useState(false)
  const [itemId, setItemId] = useState<string>()
  const members: BidMember[] = Form.useWatch('members', form) ?? []
  const personId = Form.useWatch('person_id', form)
  const { data: task } = useQuery({ queryKey: ['task', suggestionTask], queryFn: () => api.task(suggestionTask!), enabled: !!suggestionTask,
    refetchInterval: q => ['done', 'failed'].includes(q.state.data?.status ?? '') ? false : 2000 })
  const suggestion = task?.status === 'done' ? task.result as unknown as FactSuggestions : undefined
  const suggestionRunning = suggesting || (!!suggestionTask && !['done', 'failed'].includes(task?.status ?? ''))
  const snapshot = editor?.snapshot
  const personLink = (person?: Person) => `/kb/${encodeURIComponent(profile)}?tab=personnel&item=${person?.id ?? 'new'}&returnTo=${encodeURIComponent(`/projects/${id}/workbench`)}`
  const refresh = async () => {
    for (const key of [['profile', profile], ['profiles'], ['materials', id], ['workflow', id], ['preparation', id], ['relationship', id]]) await qc.invalidateQueries({ queryKey: key })
    await refetch(); onSaved()
  }
  const open = (kind: string) => {
    if (!data) return
    setEditor({ kind, snapshot: data }); setSuggestionTask(undefined); setItemId(undefined)
    form.resetFields()
    if (kind === 'statistics') form.setFieldsValue(Object.fromEntries([...STAT_FIELDS.map(x => x[0]), 'staff_as_of', 'staff_source'].map(k => [k, data.profile[k]])))
    if (kind === 'registration') form.setFieldsValue({ registration: data.profile.registration ?? {}, shareholders: data.profile.shareholders ?? [] })
    if (kind === 'authorization' || kind === 'team') form.setFieldsValue(data.facts[kind]?.confirmation?.data ?? (kind === 'team' ? { members: [], arrival_commitment: false } : {}))
    if (kind === 'team' && !data.facts.team?.confirmation?.data.members?.length) form.setFieldValue('arrival_commitment', false)
  }
  const selectPerformance = (value: string) => {
    setItemId(value); setSuggestionTask(undefined)
    const item = snapshot?.profile.performances.find(x => x.id === value)
    form.setFieldsValue({ id: value, signed_date: item?.signed_date || '', source: '' })
  }
  const save = async (generate = false) => {
    if (!editor) return
    try {
      const values = await form.validateFields()
      setSaving(true)
      // 清空数字需要显式传null，不能被JSON省略后沿用旧值。
      if (editor.kind === 'statistics') for (const [key] of STAT_FIELDS) values[key] = values[key] ?? null
      if (editor.kind === 'team') values.arrival_commitment = values.arrival_commitment === true
      if (editor.kind === 'team' && !values.members?.length) throw new Error('请先选择团队成员，空名单不能确认为本包团队')
      await api.savePreparation(id, profile, pkgIndex, editor.kind, editor.snapshot.revision, values)
      setEditor(undefined); await refresh()
      message.success('已保存；关联文件需重新生成和复查')
      if (generate) await onGenerate()
    } catch (e) { message.error(e instanceof Error ? e.message : '请检查必填字段') }
    finally { setSaving(false) }
  }
  const suggest = async () => {
    if (!editor) return
    setSuggesting(true)
    try { const r = await api.suggestPreparation(id, profile, pkgIndex, editor.kind, itemId); setSuggestionTask(r.task_id) }
    catch (e) { message.error(String(e)) } finally { setSuggesting(false) }
  }
  const apply = (candidate: FactSuggestions['candidates'][number]) => {
    if (!editor || suggestion?.revision !== editor.snapshot.revision) return
    const source = `${candidate.source}；原文：${candidate.quote}`
    if (editor.kind === 'registration' && candidate.field !== 'shareholders') {
      form.setFieldValue(['registration', candidate.field], { value: String(candidate.value), not_applicable: false, reason: '', source })
    } else {
      form.setFieldValue(candidate.field, candidate.value)
      if (editor.kind === 'performance') form.setFieldValue('source', source)
      if (editor.kind === 'statistics') form.setFieldValue('staff_source', source)
      if (candidate.field === 'shareholders' && Array.isArray(candidate.value)) form.setFieldValue('shareholders', candidate.value.map(x => ({ ...x, source })))
    }
    message.info('建议已带入表单，尚未保存，请核对后保存')
  }
  const candidates = snapshot?.profile.personnel.filter(x => x.status === 'approved') ?? []
  const selectedPerformance = snapshot?.profile.performances.find(x => x.id === itemId)
  const attachmentsFor = (ids: string[] = []) => <Space wrap>{ids.map(key => {
    const attachment = snapshot?.attachments.find(x => x.id === key)
    return attachment ? <a key={key} href={api.attachmentUrl(key)} target="_blank" rel="noreferrer">{attachment.filename}</a> : null
  })}</Space>
  const requiredCount = snapshot?.roles.reduce((n, r) => n + r.count, 0) ?? 0
  return <Card size="small" title="投标准备任务" extra={<Button disabled={disabled} onClick={() => void refetch()}>刷新核对</Button>}>
    {error && <Alert type="error" message={String(error)} />}
    <Typography.Paragraph type="secondary">按业务事项处理，一次保存供关联章节复用。企业资料跨项目复用；授权、岗位和到岗承诺只对本标包生效。保存不会自动代表合规通过。</Typography.Paragraph>
    {data?.generation_stale && <Alert type="info" showIcon message="当前任务根据现有资料核对；旧文件标记仅保留在各任务的历史提示中，不计作新增资料。" style={{ marginBottom: 12 }} />}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12 }}>
      {data?.tasks.map(t => <Card key={t.id} size="small" title={t.title}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text type="secondary">{['authorization', 'team', 'relationship'].includes(t.id) ? '本次投标确认' : ['other', 'system'].includes(t.id) ? '原文 / 生成核查' : '企业长期资料'}</Typography.Text>
          <Typography.Text strong>{t.status ?? '待核对'}</Typography.Text>
          {t.current_notes?.map((note, i) => <Typography.Text key={i} type="secondary">{note}</Typography.Text>)}
          {!data.generation_stale && t.occurrences > 0 && <Typography.Text type="secondary">关联文件标记 {t.occurrences} 处，共同办理</Typography.Text>}
          {data.facts[t.id]?.confirmation && <Tag color={data.facts[t.id].stale ? 'orange' : 'blue'}>{data.facts[t.id].stale ? '确认已失效，需重新核实' : '已保存本包安排，资格仍需核实'}</Tag>}
          <Button disabled={disabled} onClick={() => open(t.id)}>{t.id === 'other' ? '查看问题与处理位置' : '去处理'}</Button>
        </Space>
      </Card>)}
    </div>
    <Drawer width="min(880px, 96vw)" open={!!editor} title={data?.tasks.find(x => x.id === editor?.kind)?.title ?? '处理任务'}
      onClose={() => { if (!saving) setEditor(undefined) }} destroyOnClose
      footer={editor && !['relationship', 'other', 'system'].includes(editor.kind) && <Space wrap>
        <Button type="primary" disabled={disabled || saving} loading={saving} onClick={() => void save()}>保存并重新核对</Button>
        <Button disabled={disabled || saving} onClick={() => void save(true)}>保存并重新生成关联文件</Button>
        <Typography.Text type="secondary">将生成本包完整的新版本，旧版保留追溯；之后需复查。</Typography.Text>
      </Space>}>
      {snapshot && editor && <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        {snapshot.tasks.find(t => t.id === editor.kind)?.items.length ? <Collapse items={[{ key: 'issues', label: snapshot.generation_stale ? '历史版本问题（不代表当前缺项）' : '查看关联文件中的原始提示', children: <ul>{snapshot.tasks.find(t => t.id === editor.kind)?.items.map((x, i) => <li key={i}>{x.message}<Typography.Text type="secondary">（{x.file}）</Typography.Text></li>)}</ul> }]} /> : null}
        {editor.kind === 'relationship' ? <RelationshipConfirmation id={id} profile={profile} pkgIndex={pkgIndex} disabled={disabled} onSaved={() => { setEditor(undefined); void refresh() }} /> :
          <Form form={form} layout="vertical" disabled={disabled || saving}>
            {['statistics', 'registration'].includes(editor.kind) && <CompanyFactsFields kind={editor.kind} form={form} />}
            {editor.kind === 'authorization' && <>
              <Alert type="info" showIcon message="项目名称与授权范围由采购文件自动填写。这里只确认本次授权人及职务，选择不会修改常用授权人。" />
              <Form.Item name="person_id" label="本次被授权人" rules={[{ required: true }]}><Select placeholder="从已审核人员中选择" options={candidates.map(x => ({ value: x.id, label: `${x.name} · ${x.title || '职务未录入'}` }))}
                onChange={value => { const person = candidates.find(x => x.id === value); form.setFieldValue('title', person?.title || ''); form.setFieldValue('identity_attachments', snapshot.attachments.filter(x => person?.attachments?.includes(x.id) && x.filename.includes('身份证')).map(x => x.id)) }} /></Form.Item>
              <Form.Item name="identity_attachments" label="本次授权书附用的身份证明" extra="请核对材料内容并选择身份证正反面或要求的身份证明，系统自动装入商务文件。"><Select mode="multiple" options={snapshot.attachments.filter(x => candidates.find(p => p.id === personId)?.attachments?.includes(x.id)).map(x => ({ value: x.id, label: x.filename }))} /></Form.Item>
              <Form.Item name="title" label="本次授权书所填职务" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
              {personId && <Card size="small" title="被授权人已有证明材料">{attachmentsFor(candidates.find(x => x.id === personId)?.attachments)}<br /><Link to={personLink(candidates.find(x => x.id === personId))}>补充或核对该人员的身份证及职务材料</Link></Card>}
              <Link to={personLink()}>知识库新增人员</Link>
            </>}
            {editor.kind === 'team' && <>
              <Alert type="info" showIcon message="选择人员和岗位只确认本次安排，不自动证明符合资格。工作经历、专业、社保等仍应对照原件核验。" />
              {snapshot.roles.length ? <Table size="small" rowKey="role" pagination={false} dataSource={snapshot.roles} columns={[
                { title: '原文岗位', dataIndex: 'role' }, { title: '人数', dataIndex: 'count', width: 65 },
                { title: '岗位要求及出处', render: (_, row) => <>{row.requirement}<br /><Typography.Text type="secondary">{row.source}</Typography.Text></> },
              ]} /> : <Alert type="warning" message="未识别到结构化岗位人数，请展开原文核对，系统不猜测人数。" />}
              <Collapse items={[{ key: 'req', label: '查看人员要求原文', children: snapshot.team_requirements.map(x => <Typography.Paragraph key={x.id}>{x.text}</Typography.Paragraph>) }]} />
              <Typography.Paragraph>当前选择 {members.length} 人{requiredCount ? `；原岗位表要求 ${requiredCount} 人` : ''}。请逐岗核对，下方证据摘要不等于资格审查通过。</Typography.Paragraph>
              <Form.List name="members">{(fields, { add, remove }) => <>
                {fields.map(({ key, name }) => <Space key={key} align="start" wrap>
                  <Form.Item name={[name, 'person_id']} label="人员" rules={[{ required: true }]}><Select style={{ width: 190 }} options={candidates.map(x => ({ value: x.id, label: x.name }))} /></Form.Item>
                  <Form.Item name={[name, 'role']} label="本次岗位" rules={[{ required: true, whitespace: true }]}>{snapshot.roles.length ? <Select style={{ width: 190 }} options={snapshot.roles.map(x => ({ value: x.role }))} /> : <Input style={{ width: 190 }} placeholder="按招标原文填写岗位" />}</Form.Item>
                  <Form.Item name={[name, 'available']} label="本包可投入" rules={[{ required: true }]}><Select style={{ width: 130 }} options={[{ value: true, label: '确认可投入' }, { value: false, label: '暂不可投入' }]} /></Form.Item>
                  <Button onClick={() => remove(name)}>移除</Button>
                </Space>)}
                <Button onClick={() => add({})}>选择团队成员</Button> <Link to={personLink()}>新增知识库人员</Link>
              </>}</Form.List>
              <Form.Item name="arrival_commitment" valuePropName="checked" style={{ marginTop: 16 }}><Checkbox disabled={!members.length || members.some(x => x.available !== true)}>确认所选可投入人员的本包到岗安排，允许系统据此起草到岗承诺（仍需按采购要求签章）</Checkbox></Form.Item>
              {members.map((m, i) => {
                const person = candidates.find(x => x.id === m.person_id)
                return person ? <Card size="small" key={`${person.id}-${i}`} title={`${person.name} · ${m.role || '岗位未选'}`} extra={<Link to={personLink(person)}>补充该人员证明</Link>}>
                  <Typography.Paragraph>{person.education || '学历未录入'} · {person.major || '专业未录入'} · {person.title || '职务/职称未录入'}</Typography.Paragraph>
                  <Typography.Paragraph>毕业日期：{String(person.graduation_date || '未录入')}；相关工作年限：{person.relevant_experience_years == null ? '未录入' : `${person.relevant_experience_years}年`}；经历依据：{String(person.experience_source || '未录入')}</Typography.Paragraph>
                  <Typography.Paragraph>证明类型：{person.credentials.join('、') || '未录入'}；社保单位：{person.social_insurance_unit || '未录入'}；月份：{person.social_insurance_months?.join('、') || '未录入'}</Typography.Paragraph>
                  {attachmentsFor(person.attachments)}
                </Card> : null
              })}
            </>}
            {editor.kind === 'performance' && <>
              <Alert type="info" showIcon message="这里填写历史业绩合同的签约日期，不是本次招标项目的日期。请以签署页或其他有效证明为依据，约略日期不要填成精确日期。" />
              <Form.Item name="id" label="具体历史业绩" rules={[{ required: true }]}><Select options={snapshot.profile.performances.map(x => ({ value: x.id, label: `${x.project}${x.signed_date ? `（${x.signed_date}）` : '（签约日期缺失）'}` }))} onChange={selectPerformance} /></Form.Item>
              {selectedPerformance && <Card size="small" title="现有材料与出处"><Typography.Paragraph>{selectedPerformance.source || '暂无文字出处'}</Typography.Paragraph>{attachmentsFor(selectedPerformance.attachments)}</Card>}
              <Form.Item name="signed_date" label="合同签约日期" rules={[{ required: true }]}><Input type="date" /></Form.Item>
              <Form.Item name="source" label="本次核对依据及页码" rules={[{ required: true }]}><Input.TextArea rows={3} placeholder="合同名称、第几页、签署日期记载；不得用发票开具日代替" /></Form.Item>
              {selectedPerformance && <Link to={`/kb/${encodeURIComponent(profile)}?tab=performances&item=${selectedPerformance.id}&returnTo=${encodeURIComponent(`/projects/${id}/workbench`)}`}>补充该业绩附件</Link>}
            </>}
            {editor.kind === 'other' && <Alert type="info" message="请按原始提示核对采购原文、模型调用或具体企业证据；此类问题不会通过填写企业基本信息自动消除。" />}
            {editor.kind === 'system' && <Space direction="vertical"><Alert type="info" message="系统会先规范引用、检索本包原文并修复正文；不需要为引用格式错误补交资料。剩余无法验证的内容仍保留核查提示。" /><Button disabled={disabled} onClick={() => { setEditor(undefined); void onGenerate() }}>重新生成并自动复核</Button></Space>}
          </Form>}
        {['statistics', 'registration', 'performance', 'team'].includes(editor.kind) && <Card size="small" title={editor.kind === 'team' ? 'AI 检索人员证据并推荐岗位' : '先让 AI 检索已有资料'} extra={<Button loading={suggestionRunning} disabled={disabled || saving || (editor.kind === 'performance' && !itemId)} onClick={() => void suggest()}>检索并提取建议</Button>}>
          <Typography.Paragraph type="secondary">仅检索本企业已有资料；建议带原文及出处，点击采用只带入表单。{editor.kind === 'team' ? '核实并保存后，仅作为本包人员安排，不自动认定资格通过。' : '核实并保存后才写入知识库。'}</Typography.Paragraph>
          {task && <Alert type={task.status === 'failed' ? 'error' : 'info'} message={task.message} />}
          {suggestion && <>
            <Typography.Paragraph>{suggestion.message}</Typography.Paragraph>
            {suggestion.recommendations?.map((r, i) => <Card key={`person-${i}`} size="small" title={`${r.name} · ${r.role}（待确认建议）`} extra={<Button disabled={saving || disabled || suggestion.revision !== snapshot.revision || members.some(x => x.person_id === r.person_id)} onClick={() => { form.setFieldValue('members', [...members, { person_id: r.person_id, role: r.role }]); form.setFieldValue('arrival_commitment', false) }}>带入待确认团队</Button>}>
              <Typography.Paragraph>{r.reason}</Typography.Paragraph>
              <Typography.Paragraph>原文：{r.quote}</Typography.Paragraph>
              <Typography.Text type="secondary">来源：{r.source}</Typography.Text>
              {r.attachment_id && <a href={api.attachmentUrl(r.attachment_id)} target="_blank" rel="noreferrer"> 查看原件</a>}
              <Typography.Paragraph>仍需核实：{r.missing.join('、') || '本包可投入情况及岗位资格原件'}。建议不代表资格通过。</Typography.Paragraph>
            </Card>)}
            {suggestion.revision !== snapshot.revision && <Alert type="warning" message="建议与当前表单版本不一致，请刷新任务并重新检索。" />}
            {suggestion.candidates.map((c, i) => <Card size="small" key={i} title={LABELS[c.field] ?? c.field} extra={<Button disabled={suggestion.revision !== snapshot.revision || saving || disabled} onClick={() => apply(c)}>采用到表单</Button>}>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{typeof c.value === 'object' ? JSON.stringify(c.value, null, 2) : String(c.value)}</pre>
              <Typography.Paragraph>原文：{c.quote}</Typography.Paragraph>
              {c.attachment_id ? <a href={api.attachmentUrl(c.attachment_id)} target="_blank" rel="noreferrer">{c.source}</a> : <Typography.Text>{c.source}</Typography.Text>}
              <Typography.Paragraph type="secondary">{c.note}</Typography.Paragraph>
            </Card>)}
            {!suggestion.candidates.length && !suggestion.recommendations?.length && <Typography.Paragraph>没有提取到可核实候选值，不能据此认定“不适用”。</Typography.Paragraph>}
            <Collapse items={[{ key: 'coverage', label: '查看检索范围与未读取原件', children: <><ul>{suggestion.checked.map((x, i) => <li key={i}>{x.title}</li>)}</ul><ul>{suggestion.unreadable.map((x, i) => <li key={i}>{x}</li>)}</ul></> }]} />
          </>}
        </Card>}
      </Space>}
    </Drawer>
  </Card>
}
