import { errorMessage } from '../uiLabels'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Select, Space, Typography, message } from 'antd'
import { api, KbItem, MaterialSelection } from '../api'

const KINDS = [
  ['certificates', '本包证照与查询材料'],
  ['performances', '本包业绩'], ['financials', '财务报告年度'],
  ['products', '产品'], ['test_reports', '检测报告'],
] as const

export default function MaterialPicker({ id, profile, pkgIndex, disabled, onSaved }: {
  id: string; profile: string; pkgIndex: number; disabled: boolean; onSaved: () => void
}) {
  const { data, error, refetch } = useQuery({
    queryKey: ['materials', id, profile, pkgIndex],
    queryFn: () => api.materials(id, profile, pkgIndex),
  })
  const [selection, setSelection] = useState<MaterialSelection>({})
  const [saving, setSaving] = useState(false)
  useEffect(() => { if (data) setSelection(data.selection) }, [data])
  const save = async () => {
    setSaving(true)
    try {
      await api.saveMaterials(id, profile, pkgIndex, selection)
      await refetch(); onSaved()
      message.success('本包使用的资料已保存，请更新标书并检查')
    } catch (e) { message.error(errorMessage(e)) } finally { setSaving(false) }
  }
  return <Card size="small" title="选择本包使用的资料">
    {error && <Alert type="error" message={errorMessage(error)} />}
    {data?.profile.is_demo === true && <Alert type="warning" showIcon message="演示档案：文件使用模拟数据并带演示标识，不可用于正式投标" style={{ marginBottom: 12 }} />}
    <Typography.Paragraph type="secondary">人员和岗位请在上方“本次项目团队”中填写。这里选择本包使用的证照、业绩等已审核资料。默认使用列表中显示的资料，财务报告取最近三年；清空某一类的选择，表示本包不使用该类资料。保存后需重新生成并检查标书。</Typography.Paragraph>
    <Space direction="vertical" style={{ width: '100%' }}>
      {data && KINDS.map(([kind, label]) => {
        const items = (data.profile[kind] as KbItem[]).filter(x => x.status === 'approved')
        const automatic = selection[kind] == null
        const defaultIds = kind === 'financials'
          ? items.filter(x => x.report_kind !== 'comparative').sort((a, b) => String(b.year).localeCompare(String(a.year))).slice(0, 3).map(x => x.id)
          : items.map(x => x.id)
        return <div key={kind}>
          <Typography.Text>{label}{automatic ? '（自动选择）' : '（手动选择）'}</Typography.Text>
          <Select mode="multiple" aria-label={label} style={{ width: '100%' }} disabled={disabled || saving}
            value={automatic ? defaultIds : selection[kind] ?? []}
            onChange={value => setSelection(old => ({ ...old, [kind]: value }))}
            options={items.map(x => ({ value: x.id, label: String(x.project ?? x.name ?? x.year ?? x.model ?? x.id) }))} />
        </div>
      })}
      <Space>
        <Button type="primary" onClick={save} disabled={disabled || !data} loading={saving}>保存资料选择</Button>
        <Button onClick={() => setSelection(old => ({ personnel: old.personnel }))} disabled={disabled || saving}>恢复自动选择</Button>
      </Space>
    </Space>
  </Card>
}
