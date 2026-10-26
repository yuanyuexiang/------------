import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Collapse, Input, Radio, Space, Typography, message } from 'antd'
import { api } from '../api'

export default function RelationshipConfirmation({ id, profile, pkgIndex, disabled, onSaved }: {
  id: string; profile: string; pkgIndex: number; disabled: boolean; onSaved: () => void
}) {
  const { data, error, refetch } = useQuery({
    queryKey: ['relationship', id, profile, pkgIndex],
    queryFn: () => api.relationship(id, profile, pkgIndex),
  })
  const [status, setStatus] = useState<'none' | 'exists'>()
  const [people, setPeople] = useState<string[][]>([])
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (data) {
      setStatus(data.stale ? undefined : data.confirmation?.status)
      setPeople(data.confirmation?.people ?? [])
    }
  }, [data])
  const save = async () => {
    if (!data || !status) return
    setSaving(true)
    try {
      await api.saveRelationship(id, profile, pkgIndex, { source: data.source, status, people: status === 'none' ? [] : people })
      await refetch(); onSaved()
      message.success('本包关系情况已确认，请重新生成文件并审查')
    } catch (e) { message.error(String(e)) } finally { setSaving(false) }
  }
  const locked = disabled || saving || !data
  return <Card size="small" title="本次投标事实确认 · 国网系统人员关系">
    <Space direction="vertical" style={{ width: '100%' }}>
      {error && <Alert type="error" message={String(error)} />}
      <Typography.Text>无需另行上传承诺书模板。请核实本企业法定代表人、出资人、高管等是否存在招标文件规定的关系，系统将按确认结果选用本次招标原条款并排版。</Typography.Text>
      {data?.stale && <Alert type="warning" showIcon message="招标要求已变化，原确认已失效，请重新核实并确认。" />}
      {!data?.confirmation && <Typography.Text type="secondary">尚未确认：可生成带待补充提示的草稿，正式导出前须完成确认。</Typography.Text>}
      {data && <Collapse size="small" items={[{ key: 'source', label: '查看招标原条款', children: data.options.length
        ? data.options.map((text, i) => <Typography.Paragraph key={i}>{text}</Typography.Paragraph>)
        : <Alert type="warning" message="当前解析结果未提取到两项原条款。生成时将再次识别招标母版；若格式无法识别，会保留待核对提示，无需另交模板。" /> }]} />}
      <Radio.Group value={status} disabled={locked} onChange={e => setStatus(e.target.value)}>
        <Radio value="none">不存在相关情形</Radio><Radio value="exists">存在相关情形</Radio>
      </Radio.Group>
      {status === 'exists' && <>
        <Typography.Text type="secondary">每行填写一组关系双方信息。缺项会在生成文件中标记待补充；非在职人员请填写离职或退休时间。</Typography.Text>
        {people.map((row, i) => <Card key={i} size="small" title={`关系 ${i + 1}`} extra={<Button disabled={locked} onClick={() => setPeople(old => old.filter((_, n) => n !== i))}>删除</Button>}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            {data?.labels.map((label, j) => <label key={j}>{j < 6 ? '本企业 · ' : '国网人员 · '}{label}
              <Input value={row[j]} aria-label={`关系${i + 1}-${j}-${label}`} maxLength={300} disabled={locked}
                onChange={e => setPeople(old => old.map((r, n) => n === i ? r.map((v, k) => k === j ? e.target.value : v) : r))} />
            </label>)}
          </div>
        </Card>)}
        <Button disabled={locked || people.length >= 100} onClick={() => setPeople(old => [...old, Array(13).fill('')])}>添加关系人员</Button>
      </>}
      <Button type="primary" disabled={locked || !status} loading={saving} onClick={save}>确认本包情况并保存</Button>
      {data?.confirmation && <Typography.Text type="secondary">上次确认：{data.confirmation.confirmed_by} · {new Date(data.confirmation.confirmed_at).toLocaleString()}。本确认仅适用于当前企业及标包；更改后需重新生成，签章仍按招标要求办理。</Typography.Text>}
    </Space>
  </Card>
}
