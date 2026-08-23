import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { api, RuleEntry } from '../../api'

const LEVEL_COLOR: Record<string, string> = { 否决: 'red', 扣分: 'orange', 建议: 'blue', 需人工: 'purple' }

function LevelTags({ level }: { level: string }) {
  return <>{level.split('/').map((l) => <Tag key={l} color={LEVEL_COLOR[l]}>{l}</Tag>)}</>
}

/** 否决规则库：规则本体在代码（jb_rules.RULES），这里维护启停 / 级别覆盖 / 参数 / 备注。 */
export default function RulesTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['rules'], queryFn: api.rules })
  const [editing, setEditing] = useState<RuleEntry | null>(null)
  const [form] = Form.useForm()
  const refresh = () => qc.invalidateQueries({ queryKey: ['rules'] })

  const toggle = async (r: RuleEntry, enabled: boolean) => {
    try { await api.updateRule(r.rule_id, { enabled, level_override: r.level_override, params: r.params, note: r.note }); refresh() } catch (e) { message.error(String(e)) }
  }
  const open = (r: RuleEntry) => {
    setEditing(r)
    const p = { ...r.default_params, ...r.params } as Record<string, unknown>
    form.setFieldsValue({
      level_override: r.level_override || '', note: r.note,
      phrases: Array.isArray(p.phrases) ? (p.phrases as string[]).join('\n') : undefined,
      threshold: typeof p.threshold === 'number' ? p.threshold : undefined,
    })
  }
  const save = async () => {
    if (!editing) return
    const v = await form.validateFields()
    const params: Record<string, unknown> = {}
    if ('phrases' in editing.default_params) params.phrases = String(v.phrases ?? '').split('\n').map((x: string) => x.trim()).filter(Boolean)
    if ('threshold' in editing.default_params && v.threshold !== undefined && v.threshold !== null) params.threshold = v.threshold
    try {
      await api.updateRule(editing.rule_id, { enabled: editing.enabled, level_override: v.level_override || '', params, note: v.note || '' })
      message.success('已保存'); setEditing(null); refresh()
    } catch (e) { message.error(String(e)) }
  }
  const reset = async (r: RuleEntry) => { await api.resetRule(r.rule_id); message.success('已恢复默认'); refresh() }
  const customized = (r: RuleEntry) => !r.enabled || !!r.level_override || Object.keys(r.params).length > 0 || !!r.note

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="warning" showIcon message="停用或降级一条否决规则，意味着该类问题不再阻断导出——只在确认本批次招标文件确实没有该要求时才调整，并在备注里写明依据（条款号）。规则本体来自否决情形表与国网典型案例库（docs/国网物资与服务投标-场景细化方案 §8.2）。" />
      <Table<RuleEntry> size="small" rowKey="rule_id" loading={isLoading} dataSource={data?.rules ?? []} pagination={false}
        rowClassName={(r) => r.enabled ? '' : 'ant-table-row-disabled'}
        columns={[
          { title: '启用', dataIndex: 'enabled', width: 70, render: (v: boolean, r) => <Switch size="small" checked={v} onChange={(c) => toggle(r, c)} /> },
          { title: '规则', dataIndex: 'rule_id', width: 110, render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
          { title: '名称', dataIndex: 'title', width: 150 },
          { title: '默认级别', dataIndex: 'level', width: 120, render: (l: string) => <LevelTags level={l} /> },
          { title: '生效级别', dataIndex: 'level_override', width: 100, render: (l: string, r) => l ? <Tag color={LEVEL_COLOR[l]}>{l}（覆盖）</Tag> : <LevelTags level={r.level} /> },
          { title: '说明', dataIndex: 'doc', ellipsis: true, render: (d: string, r) => d || r.title },
          { title: '依据', dataIndex: 'source', width: 120, ellipsis: true },
          { title: '参数', width: 120, render: (_, r) => {
            const keys = Object.keys(r.default_params)
            if (!keys.length) return <Typography.Text type="secondary">—</Typography.Text>
            return keys.map((k) => <Tag key={k} color={k in r.params ? 'geekblue' : 'default'}>{k}{k in r.params ? '*' : ''}</Tag>)
          } },
          { title: '备注', dataIndex: 'note', width: 140, ellipsis: true },
          { title: '操作', width: 130, render: (_, r) => (
            <Space size="small">
              <Button size="small" type="link" onClick={() => open(r)}>设置</Button>
              {customized(r) && <Button size="small" type="link" onClick={() => reset(r)}>恢复默认</Button>}
            </Space>
          ) },
        ]} />

      <Modal open={!!editing} title={editing ? `${editing.rule_id} ${editing.title}` : ''} onCancel={() => setEditing(null)} onOk={save} destroyOnClose>
        {editing && (
          <Form form={form} layout="vertical">
            <Typography.Paragraph type="secondary">{editing.doc || editing.title}　依据：{editing.source}</Typography.Paragraph>
            <Form.Item name="level_override" label="级别覆盖" extra={`默认 ${editing.level}；覆盖后该规则的所有发现统一为所选级别`}>
              <Select options={[{ value: '', label: '（用默认级别）' }, ...(data?.levels ?? []).map((l) => ({ value: l, label: l }))]} />
            </Form.Item>
            {'phrases' in editing.default_params && (
              <Form.Item name="phrases" label="禁用套话（每行一个）" extra="技术参数响应等于或以这些词结尾即判为套话">
                <Input.TextArea rows={5} />
              </Form.Item>
            )}
            {'threshold' in editing.default_params && (
              <Form.Item name="threshold" label="雷同判定阈值（Jaccard 相似度，0~1）"><InputNumber min={0} max={1} step={0.05} style={{ width: 160 }} /></Form.Item>
            )}
            <Form.Item name="note" label="备注（调整依据）"><Input.TextArea rows={2} placeholder="如：本批次前附表 1.11.2 未作套话禁止要求" /></Form.Item>
          </Form>
        )}
      </Modal>
    </Space>
  )
}
