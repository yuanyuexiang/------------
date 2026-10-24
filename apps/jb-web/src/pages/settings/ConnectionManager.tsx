import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Collapse, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, message } from 'antd'
import { api, LlmConnection } from '../../api'

export default function ConnectionManager() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['llm-connections'], queryFn: api.llmConnections })
  const { data: providers = [] } = useQuery({ queryKey: ['llm-providers'], queryFn: api.llmProviders })
  const [provider, setProvider] = useState('custom')
  const [models, setModels] = useState<string[]>([])
  const [manualModel, setManualModel] = useState(false)
  const [loadingModels, setLoadingModels] = useState(false)
  const [modelNote, setModelNote] = useState('填写密钥后获取模型列表')
  const modelRequest = useRef(0)
  const [editing, setEditing] = useState<LlmConnection | null | undefined>()
  const [form] = Form.useForm()
  const [busy, setBusy] = useState(false)
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['llm-connections'] }); void qc.invalidateQueries({ queryKey: ['llm-config'] }) }
  const edit = (row: LlmConnection | null) => {
    modelRequest.current += 1
    setLoadingModels(false)
    setModels(row ? [row.model] : [])
    setManualModel(false)
    setModelNote(row ? '当前值为已保存模型，可点击获取模型刷新列表' : '填写密钥后获取模型列表')
    setProvider(providers.find(p => p.base_url && p.base_url === row?.base_url)?.id ?? 'custom')
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
  return <Card title="模型连接" extra={<Space>
    <Button type="primary" onClick={() => edit(null)}>新增连接</Button>
  </Space>}>
    <Alert type="info" showIcon message="保存连接后先测试，再设为默认。切换默认仅影响之后开始的生成任务；正在生成的文件继续使用原连接。" style={{ marginBottom: 12 }} />
    <Table rowKey="id" dataSource={data?.connections ?? []} pagination={false} columns={[
      { title: '名称', dataIndex: 'name', render: (v, r) => <>{v} {r.id === data?.default_id && <Tag color="green">默认</Tag>}</> },
      { title: '接口地址', dataIndex: 'base_url' },
      { title: '模型', dataIndex: 'model' },
      { title: '密钥', dataIndex: 'key_configured', render: (v) => v ? '已配置' : '未配置' },
      { title: '操作', render: (_, r) => <Space>
        {r.id !== 'legacy' && <Button size="small" onClick={() => edit(r)}>编辑</Button>}
        <Button size="small" disabled={busy} onClick={() => void act(async () => {
          const result = await api.testConnection(r.id)
          if (!result.ok) throw new Error(result.error)
        }, '连接测试通过')}>测试连接</Button>
        <Button size="small" disabled={busy || r.id === data?.default_id || !r.key_configured} onClick={() => void act(() => api.defaultConnection(r.id), '默认连接已切换')}>设为默认</Button>
      </Space> },
    ]} />
    <Modal title={editing ? '编辑连接' : '新增连接'} open={editing !== undefined} confirmLoading={busy}
      onCancel={close} onOk={() => form.submit()} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={async v => {
        setBusy(true)
        try { await api.saveConnection(editing?.id, v); close(); refresh(); message.success('已保存，请测试连接') }
        catch (e) { message.error(String(e)) } finally { setBusy(false) }
      }}>
        <Form.Item label="模型服务商"><Select showSearch optionFilterProp="label" value={provider} onChange={chooseProvider} options={providers.map(p => ({ value: p.id, label: p.name }))} /></Form.Item>
        <Form.Item name="name" label="连接名称" rules={[{ required: true }]}><Input /></Form.Item>
        <Form.Item name="base_url" label="接口地址（base_url）" rules={[{ required: true }]}><Input placeholder="选择服务商自动填入，其他区域可修改" onChange={() => { setProvider('custom'); invalidateModels() }} /></Form.Item>
        <Form.Item name="api_key" label="API Key" rules={[{ required: !editing }]} extra={editing ? '留空保留原密钥；切换接口地址时须填写对应密钥。' : '密钥加密保存，不回显；填完后自动获取模型列表。'}><Input.Password autoComplete="new-password" onChange={invalidateModels} onBlur={() => { if (form.getFieldValue('api_key')?.trim()) void fetchModels() }} /></Form.Item>
        <Space style={{ marginBottom: 12 }}>
          <Button onClick={() => void fetchModels()} loading={loadingModels}>获取模型列表</Button>
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
    </Modal>
  </Card>
}
