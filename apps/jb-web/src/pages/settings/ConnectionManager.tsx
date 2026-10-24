import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Collapse, Form, Input, InputNumber, Drawer, Select, Space, Switch, Table, Tag, Typography, Descriptions, message } from 'antd'
import { api, fmtUtc, LlmConnection } from '../../api'

export default function ConnectionManager() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['llm-connections'], queryFn: api.llmConnections })
  const { data: providers = [] } = useQuery({ queryKey: ['llm-providers'], queryFn: api.llmProviders })
  const [legacyOpen, setLegacyOpen] = useState(false)
  const [legacyForm] = Form.useForm()
  const [provider, setProvider] = useState<string>()
  const [models, setModels] = useState<string[]>([])
  const [manualModel, setManualModel] = useState(false)
  const [loadingModels, setLoadingModels] = useState(false)
  const [modelNote, setModelNote] = useState('点击“验证并获取模型”读取服务商列表')
  const modelRequest = useRef(0)
  const [editing, setEditing] = useState<LlmConnection | null | undefined>()
  const [form] = Form.useForm()
  const [busy, setBusy] = useState(false)
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['llm-usage'] }); void qc.invalidateQueries({ queryKey: ['llm-connections'] }); void qc.invalidateQueries({ queryKey: ['llm-config'] }) }
  const edit = (row: LlmConnection | null) => {
    modelRequest.current += 1
    setLoadingModels(false)
    setModels(row ? [row.model] : [])
    setManualModel(false)
    setModelNote(row ? '当前值为已保存模型，可点击获取模型刷新列表' : '点击“验证并获取模型”读取服务商列表')
    setProvider(row ? (providers.find(p => p.base_url && p.base_url === row.base_url)?.id ?? 'custom') : undefined)
    form.resetFields()
    form.setFieldsValue(row ?? { name: '', base_url: '', model: '', temperature: 0.3, timeout: 300, max_tokens: 12000 })
    setEditing(row)
  }
  const invalidateModels = () => {
    modelRequest.current += 1
    setLoadingModels(false)
    setModels([])
    setModelNote('连接信息已变更，请重新获取模型列表')
  }
  const fetchModels = async () => {
    const requestId = ++modelRequest.current
    setLoadingModels(true)
    setModelNote('正在获取服务商模型列表…')
    try {
      const result = await api.discoverModels({ base_url: form.getFieldValue('base_url'), api_key: form.getFieldValue('api_key') || '', connection_id: editing?.id })
      if (requestId !== modelRequest.current) return
      setModels(result.models)
      setModelNote(`已获取 ${result.models.length} 个模型。${result.message}`)
      setManualModel(false)
    } catch (e) {
      if (requestId !== modelRequest.current) return
      setModels([])
      setModelNote(String(e))
      setManualModel(true)
    } finally { if (requestId === modelRequest.current) setLoadingModels(false) }
  }
  const chooseProvider = (id: string) => {
    const selected = providers.find(p => p.id === id)
    setProvider(id)
    invalidateModels()
    form.setFieldsValue({ name: selected?.id === 'custom' ? '' : selected?.name, base_url: selected?.base_url ?? '', model: undefined, api_key: '' })
  }
  const close = () => { modelRequest.current += 1; setLoadingModels(false); setEditing(undefined); form.resetFields() }
  const act = async (fn: () => Promise<unknown>, success: string) => {
    setBusy(true)
    try { await fn(); message.success(success); refresh() } catch (e) { message.error(String(e)) } finally { setBusy(false) }
  }
  const current = data?.connections.find(r => r.id === data.default_id)
  const validation = (row: LlmConnection) => {
    const status = row.validation
    const labels: Record<string, string> = { passed: '调用测试通过', failed: '调用测试失败', stale: '配置已变更，待重新验证', untested: '尚未验证调用', unavailable: '配置不可用' }
    return <Space direction="vertical" size={0}><Tag color={status?.state === 'passed' ? 'green' : status?.state === 'failed' ? 'red' : 'default'}>{labels[status?.state ?? 'untested']}</Tag>
      {status?.tested_at && <Typography.Text type="secondary">{fmtUtc(status.tested_at)}</Typography.Text>}</Space>
  }
  const test = (row: LlmConnection) => act(async () => {
    const result = await api.testConnection(row.id)
    refresh()
    if (!result.ok) throw new Error(result.error)
  }, '短对话测试通过；标书长文本质量仍需验收')
  const manage = async (row: LlmConnection) => {
    if (row.id !== 'legacy') { edit(row); return }
    try { const config = await api.llmConfig(); legacyForm.setFieldsValue(config.saved); setLegacyOpen(true) }
    catch (e) { message.error(String(e)) }
  }
  const save = async (verify: boolean, makeDefault: boolean) => {
    let v: Record<string, unknown>
    try { v = await form.validateFields() } catch { return }
    setBusy(true)
    try {
      const saved = await api.saveConnection(editing?.id, v)
      setEditing(saved)
      form.setFieldValue('api_key', '')
      refresh()
      if (verify || makeDefault) {
        const checked = await api.testConnection(saved.id)
        refresh()
        if (!checked.ok) throw new Error('配置已保存，但调用测试失败：' + checked.error)
      }
      if (makeDefault) await api.defaultConnection(saved.id)
      refresh(); close(); message.success(makeDefault ? '已验证并设为默认模型' : verify ? '已保存并通过调用测试' : '已保存，尚未验证调用')
    } catch (e) { message.error(String(e)) } finally { setBusy(false) }
  }
  return <Space direction="vertical" style={{ width: '100%' }}>
        <Card title="当前默认模型">
          {current && <><Typography.Title level={4} style={{ marginTop: 0 }}>{current.name} / {current.model}</Typography.Title>
          {validation(current)}
          <div style={{ marginTop: 16 }}><Space><Button loading={busy} onClick={() => void test(current)}>测试调用</Button></Space></div></>}
          <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>解析辅助、资格自检、方案起草和模拟评分共用默认模型。切换仅影响之后开始的任务。</Typography.Paragraph>
        </Card>
<Card title="服务商连接" extra={<Button type="primary" onClick={() => edit(null)}>接入服务商</Button>}>
        <Table rowKey="id" dataSource={data?.connections ?? []} pagination={false} columns={[
          { title: '名称', dataIndex: 'name', render: (name, row) => <>{name} {row.id === data?.default_id && <Tag color="blue">默认</Tag>}</> },
          { title: '凭据', render: (_, row) => <>{row.id === 'legacy' ? '部署配置' : '加密保存'} · {row.key_configured ? '已保存' : '未配置'}</> },
          { title: '模型', dataIndex: 'model' }, { title: '最近验证', render: (_, row) => validation(row) },
          { title: '操作', render: (_, row) => <Space wrap>
            <Button size="small" onClick={() => void manage(row)}>管理</Button>
            <Button size="small" disabled={busy} onClick={() => void test(row)}>测试调用</Button>
            {row.id !== data?.default_id && <Button size="small" disabled={busy || row.validation?.state !== 'passed'} onClick={() => void act(() => api.defaultConnection(row.id), '默认模型已切换')}>设为默认</Button>}
          </Space> },
        ]} />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>已保存凭据不代表调用成功。请先测试所选模型，再设为默认。</Typography.Paragraph>
      </Card>
    <Drawer title="部署连接详情" width={560} open={legacyOpen} onClose={() => setLegacyOpen(false)}>
      <Alert type="info" message="密钥由部署环境提供。下列设置只修改此部署连接，不影响其他服务商。" />
      <Descriptions column={1} style={{ marginTop: 16 }} items={[{ key: 'model', label: '当前模型', children: data?.connections.find(r => r.id === 'legacy')?.model }]} />
      <Form form={legacyForm} layout="vertical" onFinish={v => void act(async () => { await api.saveLlm(v); setLegacyOpen(false) }, '部署连接已保存')}>
        <Form.Item name="base_url" label="接口地址覆盖" extra="留空使用部署环境中的地址"><Input /></Form.Item>
        <Form.Item name="model" label="模型覆盖" extra="留空使用部署环境中的模型"><Input /></Form.Item>
        <Form.Item name="temperature" label="温度"><InputNumber min={0} max={2} step={0.1} /></Form.Item>
        <Form.Item name="timeout" label="超时（秒）"><InputNumber min={5} max={600} /></Form.Item>
        <Button type="primary" htmlType="submit" loading={busy}>保存此连接</Button>
      </Form>
    </Drawer>
    <Drawer title={editing ? '管理服务商连接' : '接入服务商'} open={editing !== undefined} width={600}
      onClose={busy ? undefined : close} closable={!busy} maskClosable={!busy} destroyOnClose
      footer={<Space wrap><Button disabled={busy} onClick={() => void save(false, false)}>仅保存</Button><Button loading={busy} onClick={() => void save(true, false)}>保存并验证调用</Button><Button type="primary" disabled={busy} onClick={() => void save(true, true)}>保存并设为默认</Button></Space>}>
      <Alert type="info" showIcon message="选择服务商 → 验证凭据并获取模型 → 选择模型并测试" style={{ marginBottom: 20 }} />
      <Form form={form} layout="vertical" disabled={busy}>
        <Form.Item label="模型服务商"><Select showSearch virtual={false} listHeight={400} placeholder="请选择模型服务商" optionFilterProp="label" value={provider} onChange={chooseProvider} options={providers.map(p => ({ value: p.id, label: p.name }))} /></Form.Item>
        <Form.Item name="name" label="连接名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="base_url" label="接口地址（base_url）" rules={[{ required: true }]}><Input placeholder="选择服务商自动填入，其他区域可修改" onChange={() => { setProvider('custom'); invalidateModels() }} /></Form.Item>
        <Form.Item name="api_key" label="API Key" rules={[{ required: !editing }]} extra={editing ? '留空保留原密钥；切换接口地址时须填写对应密钥。' : '密钥加密保存，不回显；点击下方按钮验证并获取模型。'}><Input.Password autoComplete="new-password" onChange={invalidateModels} /></Form.Item>
        <Space style={{ marginBottom: 12 }}>
          <Button onClick={() => void fetchModels()} loading={loadingModels}>验证并获取模型</Button>
          <Switch checked={manualModel} onChange={setManualModel} checkedChildren="手动填写" unCheckedChildren="下拉选择" />
        </Space>
        <Form.Item name="model" label="模型" rules={[{ required: true, message: '请选择或手动填写模型' }]} extra={modelNote}>
          {manualModel ? <Input placeholder="填写模型 ID 或服务商推理接入点 ID" /> : <Select showSearch allowClear loading={loadingModels} placeholder="获取后搜索并选择模型" options={models.map(m => ({ value: m, label: m }))} />}
        </Form.Item>
        <Collapse ghost items={[{ key: 'advanced', forceRender: true, label: '高级参数（通常无需修改）', children: (
        <Space align="start">
          <Form.Item name="temperature" label="温度"><InputNumber min={0} max={2} step={0.1} /></Form.Item>
          <Form.Item name="timeout" label="超时（秒）"><InputNumber min={5} max={600} /></Form.Item>
          <Form.Item name="max_tokens" label="最大输出 tokens"><InputNumber min={1} max={131072} /></Form.Item>
        </Space>
        ) }]} />
      </Form>
    </Drawer>
  </Space>
}
