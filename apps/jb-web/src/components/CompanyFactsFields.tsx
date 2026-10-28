import { Button, Form, Input, InputNumber, Space, Switch, Typography } from 'antd'
import type { FormInstance } from 'antd'

export const STAT_FIELDS = [
  ['staff_total', '员工总数'], ['staff_technical', '技术人员数'], ['senior_engineers', '高级工程师人数'],
  ['engineers', '工程师人数'], ['assistant_engineers', '助理工程师人数'], ['technicians', '技术员人数'],
] as const
export const REGISTRATION_FIELDS = ['主管部门', '批准部门', '批准文号']

function RegistrationRow({ name, form }: { name: string; form: FormInstance }) {
  const na = Form.useWatch(['registration', name, 'not_applicable'], form)
  return <div style={{ padding: 12, border: '1px solid #eee', borderRadius: 8, marginBottom: 12 }}>
    <Typography.Text strong>{name}</Typography.Text>
    <Form.Item name={['registration', name, 'not_applicable']} label="本企业不适用" valuePropName="checked">
      <Switch onChange={v => { if (v) form.setFieldValue(['registration', name, 'value'], '') }} />
    </Form.Item>
    {na ? <Form.Item name={['registration', name, 'reason']} label="不适用理由" rules={[{ required: true }]}><Input.TextArea rows={2} placeholder="结合企业性质和采购表格说明填写，不默认不适用" /></Form.Item>
      : <Form.Item name={['registration', name, 'value']} label="已核实的值"><Input /></Form.Item>}
    <Form.Item name={['registration', name, 'source']} label="依据 / 原件页码"><Input placeholder="例如营业执照第1页；无法确认可先留空" /></Form.Item>
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
    <Typography.Paragraph type="secondary">先检索已有营业执照、信用报告和补充说明。没有证据不自动填值；确实不适用的请说明理由。</Typography.Paragraph>
    {REGISTRATION_FIELDS.map(name => <RegistrationRow key={name} name={name} form={form} />)}
    <Typography.Title level={5}>股东或上级管理单位及出资</Typography.Title>
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
      <Button onClick={() => add({})}>添加股东 / 上级管理单位</Button>
    </>}</Form.List>
  </>
}
