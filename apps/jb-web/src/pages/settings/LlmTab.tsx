import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Col, Descriptions, Drawer, Row, Select, Space, Statistic, Table, Typography } from 'antd'
import { api, fmtUtc, LlmUsagePage } from '../../api'

const PURPOSE_CN: Record<string, string> = { parse: '解析辅助', qualify: '资格自检', draft: '方案起草', score: '模拟评分', test: '连接测试' }
const duration = (ms: number) => ms < 60000 ? `${(ms / 1000).toFixed(1)}秒` : `${Math.floor(ms / 60000)}分${Math.round(ms % 60000 / 1000)}秒`
function errorSummary(error: string) {
  if (!error) return '调用失败'
  if (/401|403|密钥|鉴权/.test(error)) return '认证或权限异常'
  if (/429/.test(error)) return '调用频率或额度受限'
  if (/timeout|超时/i.test(error)) return '请求超时'
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
    {error && <Alert type="error" message={String(error)} />}
    <Card title="用量与运行情况">
      <Space wrap style={{ marginBottom: 20 }}>
        <Select aria-label="时间范围" value={filters.days} onChange={v => change('days', v)} options={[7, 30, 90].map(v => ({ value: v, label: `近 ${v} 天` }))} />
        <Select aria-label="服务商连接" style={{ width: 220 }} value={filters.connection_id} onChange={v => change('connection_id', v)} options={[{ value: '', label: '所有连接' }, ...(connections?.connections ?? []).map(r => ({ value: r.id, label: r.name }))]} />
        <Select aria-label="模型" showSearch style={{ width: 220 }} value={filters.model} onChange={v => change('model', v)} options={[{ value: '', label: '所有模型' }, ...(data?.models ?? []).map(v => ({ value: v, label: v }))]} />
        <Select aria-label="调用用途" style={{ width: 180 }} value={filters.purpose} onChange={v => change('purpose', v)} options={[{ value: 'business', label: '业务调用（不含测试）' }, { value: '', label: '全部调用' }, ...Object.entries(PURPOSE_CN).map(([value, label]) => ({ value, label }))]} />
        <Select aria-label="调用结果" value={filters.result} onChange={v => change('result', v)} options={[{ value: '', label: '所有结果' }, { value: 'success', label: '成功' }, { value: 'failed', label: '失败' }]} />
      </Space>
      <Row gutter={[16, 16]}>
        <Col xs={12} md={4}><Statistic title="调用次数" value={data?.total ?? 0} /></Col>
        <Col xs={12} md={4}><Statistic title="失败次数" value={data?.failed ?? 0} /></Col>
        <Col xs={12} md={5}><Statistic title="输入 tokens" value={data?.prompt_tokens ?? 0} /></Col>
        <Col xs={12} md={5}><Statistic title="输出 tokens" value={data?.completion_tokens ?? 0} /></Col>
        <Col xs={24} md={6}><Statistic title="平均调用耗时" value={duration(data?.avg_latency_ms ?? 0)} /></Col>
      </Row>
      <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>统计与下方记录使用相同筛选条件。调用耗时不是整份标书的生成耗时。</Typography.Paragraph>
    </Card>
    <Card title="调用记录">
      <Table<LlmUsagePage['rows'][number]> rowKey="id" loading={isFetching} dataSource={data?.rows ?? []} scroll={{ x: 900 }} pagination={{ current: filters.page, pageSize: 10, total: data?.total ?? 0, showSizeChanger: false, onChange: page => setFilters(f => ({ ...f, page })) }} columns={[
        { title: '时间', dataIndex: 'created_at', render: fmtUtc },
        { title: '用途', dataIndex: 'purpose', render: v => PURPOSE_CN[v] ?? v },
        { title: '连接 / 模型', render: (_, r) => <>{r.connection_name || '历史记录'}<br /><Typography.Text type="secondary">{r.model}</Typography.Text></> },
        { title: '结果', render: (_, r) => <Typography.Text type={r.ok ? 'success' : 'danger'}>{r.ok ? '成功' : errorSummary(r.error)}</Typography.Text> },
        { title: '耗时', dataIndex: 'latency_ms', render: duration },
        { title: '输入 / 输出 tokens', render: (_, r) => `${r.prompt_tokens ?? '—'} / ${r.completion_tokens ?? '—'}` },
        { title: '操作', render: (_, r) => <Button type="link" onClick={() => setDetail(r)}>详情</Button> },
      ]} />
    </Card>
    <Drawer title="调用详情" open={!!detail} width={560} onClose={() => setDetail(undefined)}>
      {detail && <Descriptions column={1} bordered items={[
        { key: 'time', label: '时间', children: fmtUtc(detail.created_at) },
        { key: 'model', label: '模型', children: detail.model },
        { key: 'project', label: '关联项目', children: detail.project_id ? <a href={`/projects/${detail.project_id}/workbench`}>打开项目工作台</a> : '未记录项目关联' },
        { key: 'task', label: '任务编号', children: detail.task_id || '—' },
        { key: 'error', label: '技术详情', children: <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>{detail.error || '调用成功'}</Typography.Paragraph> },
      ]} />}
    </Drawer>
  </Space>
}
