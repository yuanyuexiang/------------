import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Select, Space, Typography, message } from 'antd'
import { api, KbItem, MaterialSelection } from '../api'

const KINDS = [
  ['certificates', '本包证照与查询材料'], ['personnel', '拟投入人员'],
  ['performances', '本包业绩'], ['financials', '财务年度'],
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
      message.success('本包选材已保存，请重新生成并审查')
    } catch (e) { message.error(String(e)) } finally { setSaving(false) }
  }
  return <Card size="small" title="本包选材">
    {error && <Alert type="error" message={String(error)} />}
    {data?.profile.is_demo === true && <Alert type="warning" showIcon message="演示档案：文件使用模拟数据并带演示标识，不可用于正式投标" style={{ marginBottom: 12 }} />}
    <Typography.Paragraph type="secondary">只使用已审核材料。空白表示自动使用已审核资料（财务取最近三年）；手动清空全部选项表示本包不使用该类资料。请依据本包资格要求选材，保存后旧产出失效。</Typography.Paragraph>
    <Space direction="vertical" style={{ width: '100%' }}>
      {data && KINDS.map(([kind, label]) => {
        const items = (data.profile[kind] as KbItem[]).filter(x => x.status === 'approved')
        const automatic = selection[kind] == null
        const defaultIds = kind === 'financials'
          ? items.filter(x => x.report_kind !== 'comparative').sort((a, b) => String(b.year).localeCompare(String(a.year))).slice(0, 3).map(x => x.id)
          : items.filter(x => kind !== 'personnel' || x.available !== false).map(x => x.id)
        return <div key={kind}>
          <Typography.Text>{label}{automatic ? '（自动）' : '（已指定）'}</Typography.Text>
          <Select mode="multiple" aria-label={label} style={{ width: '100%' }} disabled={disabled || saving}
            value={automatic ? defaultIds : selection[kind] ?? []}
            onChange={value => setSelection(old => ({ ...old, [kind]: value }))}
            options={items.map(x => ({ value: x.id, label: String(x.project ?? x.name ?? x.year ?? x.model ?? x.id) }))} />
        </div>
      })}
      <Space>
        <Button type="primary" onClick={save} disabled={disabled || !data} loading={saving}>保存本包选材</Button>
        <Button onClick={() => setSelection({})} disabled={disabled || saving}>恢复自动选择</Button>
      </Space>
    </Space>
  </Card>
}
