import { useState } from 'react'
import { Button, Form, Input, InputNumber, Space, Radio, Collapse, Tag, Typography } from 'antd'
import type { FormInstance } from 'antd'

export const STAT_FIELDS = [
  ['staff_total', '员工总数'], ['staff_technical', '技术人员数'], ['senior_engineers', '高级工程师人数'],
  ['engineers', '工程师人数'], ['assistant_engineers', '助理工程师人数'], ['technicians', '技术员人数'],
] as const
export const REGISTRATION_FIELDS = ['主管部门', '批准部门', '批准文号']

const HELP: Record<string, string> = {
  '主管部门': '按招标原表确认是否要求企业隶属或主管单位；不能直接将营业执照的登记机关填在这里。',
  '批准部门': '需核对本表指的是哪一项批准事项及出具批准文件的部门，不能默认等于市场监管部门。',
  '批准文号': '指相应批准文件的编号，不能用统一社会信用代码或营业执照号码替代。',
}
function RegistrationRow({ name, form }: { name: string; form: FormInstance }) {
  const [entering, setEntering] = useState(false)
  const record = Form.useWatch(['registration', name], form)
  const mode = record?.not_applicable ? 'na' : (record?.value || entering) ? 'value' : 'unknown'
  return <div style={{ padding: 12, border: '1px solid #eee', borderRadius: 8, marginBottom: 12 }}>
    <Space><Typography.Text strong>{name}</Typography.Text><Tag>{mode === 'na' ? '已记录不适用' : mode === 'value' ? '已有记录，待核对' : '尚待确认'}</Tag></Space>
    <Typography.Paragraph type="secondary">{HELP[name]}</Typography.Paragraph>
    <Form.Item name={['registration', name, 'not_applicable']} hidden><Input /></Form.Item>
    <Radio.Group value={mode} onChange={e => {
      const next = e.target.value
      setEntering(next === 'value')
      form.setFieldValue(['registration', name], { value: next === 'value' ? record?.value ?? '' : '', not_applicable: next === 'na', reason: '', source: record?.source ?? '' })
    }} options={[{ value: 'unknown', label: '暂不确定，保留待确认' }, { value: 'value', label: '有明确记录' }, { value: 'na', label: '确认本企业不适用' }]} />
    {mode === 'unknown' && <Typography.Paragraph style={{ marginTop: 12 }}>无需猜填。系统未找到不代表不适用，可先保存其他已核实内容，再向企业登记资料保管人员核实。</Typography.Paragraph>}
    {mode === 'value' && <Form.Item name={['registration', name, 'value']} label="标书填写内容" rules={[{ required: true, whitespace: true, message: '请填写已核实内容，或选择暂不确定' }]}><Input placeholder="优先采用上方带原文的记录，也可手动更正" /></Form.Item>}
    {mode === 'na' && <Form.Item name={['registration', name, 'reason']} label="确认依据" extra="这是一次企业事实确认，不会因为没检索到资料而自动选择。" rules={[{ required: true, whitespace: true }]}>
      <Input.TextArea rows={2} placeholder="说明本表所指事项为何不适用于企业；不清楚时选‘暂不确定’" />
    </Form.Item>}
    {record?.source && <Typography.Paragraph type="secondary">已有依据：{record.source}</Typography.Paragraph>}
    <Collapse size="small" items={[{ key: 'source', label: '查看或更正资料依据', children: <Form.Item name={['registration', name, 'source']} label="资料依据" rules={mode === 'value' ? [{ required: true, whitespace: true, message: '采用上方建议可自动带入依据；手动填写请注明来源' }] : []}><Input.TextArea rows={2} placeholder="采用系统记录时自动带入；手动更正时注明所依据的资料" /></Form.Item> }]} />
  </div>
}

export default function CompanyFactsFields({ kind, form }: { kind: string; form: FormInstance }) {
  if (kind === 'statistics') return <>
    <Typography.Paragraph type="secondary">填写企业整体统计，不能用知识库已录入人员条数代替。未知留空，0 表示已确认没有。保存后可供其他项目复用。</Typography.Paragraph>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
      {STAT_FIELDS.map(([name, label]) => <Form.Item key={name} name={name} label={label}><InputNumber min={0} precision={0} style={{ width: '100%' }} /></Form.Item>)}
    </div>
    <Form.Item name="staff_as_of" label="统计日期" rules={[{ required: true }, { pattern: /^\d{4}-\d{2}-\d{2}$/, message: '格式为 YYYY-MM-DD' }]}><Input type="date" /></Form.Item>
    <Form.Item name="staff_source" label="统计口径与依据" rules={[{ required: true }]}><Input.TextArea rows={3} placeholder="例如截至该日期的在职人员名册，技术人员及职称人数由人事核实" /></Form.Item>
  </>
  return <>
    <Typography.Paragraph type="secondary">上方建议采用后会带入以下内容及依据；已有记录可直接核对。暂不确定的项可留待确认，不必为了保存而选择“不适用”。</Typography.Paragraph>
    {REGISTRATION_FIELDS.map(name => <RegistrationRow key={name} name={name} form={form} />)}
    <Typography.Title level={5}>股东及出资信息</Typography.Title><Typography.Paragraph type="secondary">先查看上方从企业信用公示报告、章程等提取的股东记录。未记载的金额或比例保持空白，不按注册资本推算；不同日期的记录请核对后选用。</Typography.Paragraph>
    <Form.List name="shareholders">{(fields, { add, remove }) => <>
      {fields.map(({ key, name }) => <div key={key} style={{ padding: 12, border: '1px solid #eee', marginBottom: 12 }}>
        <Form.Item name={[name, 'name']} label="股东或上级管理单位名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Space align="start">
          <Form.Item name={[name, 'amount_wan']} label="出资金额（万元）"><InputNumber min={0} /></Form.Item>
          <Form.Item name={[name, 'ratio']} label="出资比例（%）"><InputNumber min={0} max={100} /></Form.Item>
        </Space>
        <Form.Item name={[name, 'source']} label="资料出处及页码" rules={[{ required: true }]}><Input /></Form.Item>
        <Button onClick={() => remove(name)}>移除此行</Button>
      </div>)}
      <Button onClick={() => add({})}>资料未覆盖？手动补充股东</Button>
    </>}</Form.List>
  </>
}
