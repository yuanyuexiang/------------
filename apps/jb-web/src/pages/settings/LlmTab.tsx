import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Form, Input, InputNumber, Row, Select, Space, Statistic, Table, Tag, Typography, message } from 'antd'
import { api, fmtUtc, LlmConfig } from '../../api'

const PURPOSE_CN: Record<string, string> = { parse: '解析兜底', qualify: '资格自检', draft: '起草', score: '模拟评分', test: '连接测试' }

/** LLM 设置：端点/模型/温度/超时可在此覆盖（落 settings 表）；密钥只能在 .env，这里只显示是否已配置。用量按用途/按天汇总。 */
export default function LlmTab() {
  const qc = useQueryClient()
  const [days, setDays] = useState(30)
  const { data, isLoading } = useQuery({ queryKey: ['llm-config', days], queryFn: () => api.llmConfig(days) })
  const [form] = Form.useForm()
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; latency_ms: number; model: string; reply?: string; error?: string } | null>(null)
  useEffect(() => { if (data) form.setFieldsValue({ ...data.saved }) }, [data, form])

  const save = useMutation({
    mutationFn: (v: Record<string, unknown>) => api.saveLlm(v),
    onSuccess: () => { message.success('已保存并生效'); qc.invalidateQueries({ queryKey: ['llm-config'] }) },
    onError: (e) => message.error(String(e)),
  })
  const test = async () => {
    setTesting(true)
    try { const v = form.getFieldsValue(); setTestResult(await api.testLlm(v.base_url || undefined, v.model || undefined)) } catch (e) { message.error(String(e)) } finally { setTesting(false); qc.invalidateQueries({ queryKey: ['llm-config'] }) }
  }
  if (isLoading || !data) return null
  const u = data.usage

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {!data.effective.key_configured && <Alert type="error" showIcon message="未配置 LLM_API_KEY：LLM 兜底/起草/评分均不可用。密钥只能写在仓库根 .env（或容器环境变量），不经页面、不入库。" />}
      <Row gutter={16}>
        <Col span={12}>
          <Card size="small" title="连接设置">
            <Descriptions size="small" column={1} bordered labelStyle={{ width: 110 }} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="密钥">{data.effective.key_configured ? <Tag color="green">已配置（环境变量）</Tag> : <Tag color="red">未配置</Tag>}</Descriptions.Item>
              <Descriptions.Item label="生效端点">{data.effective.base_url || <Typography.Text type="secondary">未设置</Typography.Text>}</Descriptions.Item>
              <Descriptions.Item label="生效模型">{data.effective.model}</Descriptions.Item>
              <Descriptions.Item label="环境变量">{data.env.base_url || '—'} / {data.env.model || '（默认）'}</Descriptions.Item>
            </Descriptions>
            <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
              <Form.Item name="base_url" label="端点覆盖（OpenAI 兼容 base_url）" extra="留空=用环境变量 LLM_BASE_URL"><Input placeholder="https://api.example.com/v1" allowClear /></Form.Item>
              <Form.Item name="model" label="模型覆盖" extra="留空=用环境变量 LLM_MODEL"><Input placeholder="mimo-v2.5-pro" allowClear /></Form.Item>
              <Space size="large" align="start">
                <Form.Item name="temperature" label="温度（0~2）"><InputNumber min={0} max={2} step={0.1} placeholder="0" /></Form.Item>
                <Form.Item name="timeout" label="超时（秒）"><InputNumber min={5} max={600} placeholder="60" /></Form.Item>
              </Space>
              <br />
              <Space>
                <Button type="primary" htmlType="submit" loading={save.isPending}>保存并生效</Button>
                <Button onClick={test} loading={testing}>测试连接（按表单值）</Button>
              </Space>
            </Form>
            {testResult && (
              <Alert style={{ marginTop: 12 }} type={testResult.ok ? 'success' : 'error'} showIcon
                message={testResult.ok ? `连接正常 · ${testResult.model} · ${testResult.latency_ms} ms · 回复「${testResult.reply}」` : `连接失败 · ${testResult.model} · ${testResult.error}`} />
            )}
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="用量" extra={<Select size="small" value={days} onChange={setDays} options={[7, 30, 90].map((d) => ({ value: d, label: `近 ${d} 天` }))} />}>
            <Row gutter={16} style={{ marginBottom: 12 }}>
              <Col span={6}><Statistic title="调用" value={u.calls} /></Col>
              <Col span={6}><Statistic title="失败" value={u.failed} valueStyle={{ color: u.failed ? '#cf1322' : undefined }} /></Col>
              <Col span={6}><Statistic title="输入 tokens" value={u.prompt_tokens} /></Col>
              <Col span={6}><Statistic title="输出 tokens" value={u.completion_tokens} /></Col>
            </Row>
            <Table size="small" rowKey="purpose" pagination={false} dataSource={u.by_purpose} style={{ marginBottom: 12 }}
              columns={[
                { title: '用途', dataIndex: 'purpose', render: (p: string) => PURPOSE_CN[p] ?? p },
                { title: '调用', dataIndex: 'calls', width: 80 },
                { title: '输入', dataIndex: 'prompt_tokens', width: 100 },
                { title: '输出', dataIndex: 'completion_tokens', width: 100 },
              ]} />
            <Typography.Text type="secondary">平均延迟 {u.avg_latency_ms} ms · 按天：{u.by_day.map((d) => `${d.day.slice(5)} ${d.calls}次`).join('，') || '—'}</Typography.Text>
          </Card>
        </Col>
      </Row>
      <Card size="small" title="最近调用">
        <Table<LlmConfig['usage']['recent'][number]> size="small" rowKey={(r) => r.created_at + r.purpose} pagination={false} dataSource={u.recent}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 150, render: fmtUtc },
            { title: '用途', dataIndex: 'purpose', width: 100, render: (p: string) => PURPOSE_CN[p] ?? p },
            { title: '模型', dataIndex: 'model', width: 160 },
            { title: '结果', dataIndex: 'ok', width: 80, render: (ok: boolean) => ok ? <Tag color="green">成功</Tag> : <Tag color="red">失败</Tag> },
            { title: '延迟', dataIndex: 'latency_ms', width: 90, render: (v: number) => `${v} ms` },
            { title: 'tokens', width: 120, render: (_, r) => r.prompt_tokens === null ? '—' : `${r.prompt_tokens} / ${r.completion_tokens}` },
            { title: '错误', dataIndex: 'error', ellipsis: true },
          ]} />
      </Card>
    </Space>
  )
}
