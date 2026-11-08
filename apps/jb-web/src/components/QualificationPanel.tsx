import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Collapse, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { api, Check } from '../api'
import { useProjectWorkspace } from './ProjectWorkspace'
import { errorMessage, checkStatusLabel } from '../uiLabels'

const VERDICT: Record<string, string> = { 可投: 'green', 有风险: 'orange', 不可投: 'red' }
const STATUS: Record<string, string> = { 满足: 'green', 风险: 'orange', 不满足: 'red', 需人工: 'blue' }

/** 资料准备中的本包资格摘要；完整依据按需展开。 */
export default function QualificationPanel({ disabled = false }: { disabled?: boolean }) {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { profile, pkgIndex, href, setSelectionLocked } = useProjectWorkspace()
  const [llm, setLlm] = useState(true)
  const [running, setRunning] = useState(false)
  const { data: result, error, isFetching } = useQuery({ queryKey: ['qualification', id, profile, pkgIndex],
    queryFn: () => api.qualification(id, profile!, pkgIndex), enabled: !!profile, staleTime: 0 })
  const report = result?.report
  const selected = result?.package_report === undefined ? report?.packages[pkgIndex] : result.package_report

  const run = async () => {
    if (disabled || running) return
    if (!profile) return message.warning('请选择企业档案')
    setRunning(true)
    setSelectionLocked(true)
    try {
      await api.qualify(id, profile, llm)
      await Promise.all([qc.invalidateQueries({ queryKey: ['qualification', id] }), qc.invalidateQueries({ queryKey: ['project-detail', id] }), qc.invalidateQueries({ queryKey: ['projects'] })])
      message.success('资格检查已完成，请查看本包结论与风险')
    } catch (e) { message.error(errorMessage(e)) } finally { setRunning(false); setSelectionLocked(false) }
  }

  const details = selected && <Table<Check> size="small" rowKey="item" pagination={false} scroll={{ x: 800 }} dataSource={selected.checks}
    columns={[
      { title: '检查项', dataIndex: 'item', width: 180 },
      { title: '结论', dataIndex: 'status', width: 90, render: s => <Tag color={STATUS[s]}>{checkStatusLabel(s)}</Tag> },
      { title: '说明', dataIndex: 'reason' },
      { title: '证据与依据', render: (_, r) => <>{r.evidence.join('；')}<Typography.Paragraph type="secondary">{r.requirement}</Typography.Paragraph></> },
    ]} />
  const risks = selected?.checks.filter(c => c.status !== '满足') ?? []
  return <Card size="small" title="投标资格" extra={<Button disabled={!profile || disabled || isFetching} loading={running} onClick={run}>{report ? '重新检查' : '检查资格'}</Button>}>
    {error && <Alert type="error" message={errorMessage(error)} />}
    {!report ? <Typography.Text type="secondary">使用已选企业资料检查本包资格，发现缺项后补充。</Typography.Text>
      : result?.stale || !selected ? <Alert type="warning" message="资料已变化，请重新检查资格。旧结果仅作参考。" />
      : <><Tag color={VERDICT[selected.verdict]}>{selected.verdict}</Tag>{!risks.length && <Typography.Text type="secondary">已检查，仍需人工核对证明材料。</Typography.Text>}
        {risks.length > 0 && <ul>{risks.slice(0, 3).map((c, i) => <li key={i}><Typography.Paragraph ellipsis={{ rows: 1, tooltip: c.reason }} style={{ marginBottom: 4 }}>{c.item}：{c.reason}</Typography.Paragraph></li>)}</ul>}</>}
    <Space wrap style={{ marginTop: 12 }}>{profile && <Button type="link" disabled={disabled || running} onClick={() => nav(`/kb/${encodeURIComponent(profile)}?returnTo=${encodeURIComponent(href('workbench', pkgIndex, 'prepare'))}`)}>补充企业资料</Button>}</Space>
    <Collapse ghost size="small" items={[{ key: 'details', label: risks.length ? `检查详情（${risks.length} 项需核对）与设置` : '检查详情与设置', children: <><Space style={{ marginBottom: 12 }}>AI 辅助判断业绩相关性<Switch checked={llm} disabled={disabled || running} onChange={setLlm} /></Space>{details || '尚无检查结果'}</> }]} />
  </Card>
}
