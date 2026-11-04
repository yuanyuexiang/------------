import { errorMessage } from '../../uiLabels'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Drawer, Row, Select, Space, Statistic, Table, Typography } from 'antd'
import { api, fmtUtc, LlmUsagePage } from '../../api'

const PURPOSE_CN: Record<string, string> = { parse: '解析辅助', qualify: '检查投标资格', draft: '方案起草', score: '预估评分', test: '连接测试' }
const duration = (ms: number) => ms < 60000 ? `${(ms / 1000).toFixed(1)}秒` : `${Math.floor(ms / 60000)}分${Math.round(ms % 60000 / 1000)}秒`
function errorSummary(error: string) {
  if (!error) return '调用失败'
  if (/401|403|密钥|鉴权/.test(error)) return '密钥无效或没有使用权限'
  if (/429/.test(error)) return '使用过于频繁或服务额度不足'
  if (/timeout|超时/i.test(error)) return '等待时间过长，未收到回复'
  if (/disconnect|closed|network|网络/i.test(error)) return '连接中断或网络异常'
  return '模型请求失败，查看详情'
}

export default function Usage() {
  const [filters, setFilters] = useState({ days: 30, connection_id: '', model: '', purpose: 'business', result: '', page: 1, page_size: 10 })
  const [detail, setDetail] = useState<LlmUsagePage['rows'][number]>()
  const { data, isFetching, error } = useQuery({ queryKey: ['llm-usage', filters], queryFn: () => api.llmUsage(filters) })
  const { data: connections } = useQuery({ queryKey: ['llm-connections'], queryFn: api.llmConnections })
  const change = (key: string, value: string | number) => setFilters(f => ({ ...f, [key]: value, page: 1 }))
  return <Space direction="vertical" size="middle" style={{ width: '100%' }}>
    {error && <Alert type="error" message={errorMessage(error)} />}
    <Card title="用量与运行情况">
      <Space wrap style={{ marginBottom: 20 }}>
        <Select aria-label="时间范围" value={filters.days} onChange={v => change('days', v)} options={[7, 30, 90].map(v => ({ value: v, label: `近 ${v} 天` }))} />
        <Select aria-label="服务商连接" style={{ width: 220 }} value={filters.connection_id} onChange={v => change('connection_id', v)} options={[{ value: '', label: '所有连接' }, ...(connections?.connections ?? []).map(r => ({ value: r.id, label: r.name }))]} />
        <Select aria-label="模型" showSearch style={{ width: 220 }} value={filters.model} onChange={v => change('model', v)} options={[{ value: '', label: '所有模型' }, ...(data?.models ?? []).map(v => ({ value: v, label: v }))]} />
        <Select aria-label="调用用途" style={{ width: 180 }} value={filters.purpose} onChange={v => change('purpose', v)} options={[{ value: 'business', label: '项目任务（不含测试）' }, { value: '', label: '全部调用' }, ...Object.entries(PURPOSE_CN).map(([value, label]) => ({ value, label }))]} />
        <Select aria-label="调用结果" value={filters.result} onChange={v => change('result', v)} options={[{ value: '', label: '所有结果' }, { value: 'success', label: '成功' }, { value: 'failed', label: '失败' }]} />
      </Space>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={4}><Statistic title="使用次数" value={data?.total ?? 0} /></Col>
        <Col xs={12} md={4}><Statistic title="失败次数" value={data?.failed ?? 0} /></Col>
        <Col xs={12} md={5}><Statistic title="发送内容用量（Token）" value={data?.prompt_tokens ?? 0} /></Col>
        <Col xs={12} md={5}><Statistic title="生成内容用量（Token）" value={data?.completion_tokens ?? 0} /></Col>
        <Col xs={24} md={6}><Statistic title="平均等待时间" value={duration(data?.avg_latency_ms ?? 0)} /></Col>
      </Row>
      <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>用量按 Token 计量，这是 AI 服务商使用的文本计量单位，不等同于字数。统计范围与下方记录一致；等待时间指单次 AI 请求，不是整份标书的生成时间。</Typography.Paragraph>
    </Card>
    <Card title="AI 使用记录">
      <Table<LlmUsagePage['rows'][number]> rowKey="id" loading={isFetching} dataSource={data?.rows ?? []} scroll={{ x: 900 }} pagination={{ current: filters.page, pageSize: 10, total: data?.total ?? 0, showSizeChanger: false, onChange: page => setFilters(f => ({ ...f, page })) }} columns={[
        { title: '时间', dataIndex: 'created_at', render: fmtUtc },
        { title: '用途', dataIndex: 'purpose', render: v => PURPOSE_CN[v] ?? v },
        { title: '连接 / 模型', render: (_, r) => <>{r.connection_name || '历史记录'}<br /><Typography.Text type="secondary">{r.model}</Typography.Text></> },
        { title: '结果', render: (_, r) => <Typography.Text type={r.ok ? 'success' : 'danger'}>{r.ok ? '成功' : errorSummary(r.error)}</Typography.Text> },
        { title: '耗时', dataIndex: 'latency_ms', render: duration },
        { title: '发送 / 生成用量（Token）', render: (_, r) => `${r.prompt_tokens ?? '—'} / ${r.completion_tokens ?? '—'}` },
        { title: '操作', render: (_, r) => <Button type="link" onClick={() => setDetail(r)}>详情</Button> },
      ]} />
    </Card>
    <Drawer title="AI 使用详情" open={!!detail} width={560} onClose={() => setDetail(undefined)}>
      {detail && <Descriptions column={1} bordered items={[
        { key: 'time', label: '时间', children: fmtUtc(detail.created_at) },
        { key: 'model', label: '模型', children: detail.model },
        { key: 'project', label: '关联项目', children: detail.project_id ? <a href={`/projects/${detail.project_id}/workbench`}>打开标书准备页</a> : '未记录项目关联' },
        { key: 'task', label: '任务编号', children: detail.task_id || '—' },
        { key: 'error', label: '详细原因', children: <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>{detail.error || '调用成功'}</Typography.Paragraph> },
      ]} />}
    </Drawer>
  </Space>
}
