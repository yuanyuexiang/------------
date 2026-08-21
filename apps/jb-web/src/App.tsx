import { useState } from 'react'
import { Button, Card, Layout, Typography, Upload, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'

const { Header, Content } = Layout

/** S1 骨架页：上传招标文件包 → 展示解析摘要。S2 扩展为 TRM 确认页。 */
export default function App() {
  const [summary, setSummary] = useState<string>('')
  const [loading, setLoading] = useState(false)

  const upload = async (file: File) => {
    setLoading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch('/api/projects', { method: 'POST', body: form })
      if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText)
      const data = await res.json()
      setSummary(data.summary)
      message.success('解析完成')
    } catch (e) {
      message.error(String(e))
    } finally {
      setLoading(false)
    }
    return false
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ color: '#fff', fontSize: 18 }}>Jinbang 金榜 · 智能投标工作台</Header>
      <Content style={{ padding: 24, maxWidth: 960, margin: '0 auto', width: '100%' }}>
        <Card title="导入招标文件包">
          <Upload.Dragger accept=".zip" beforeUpload={upload} showUploadList={false} disabled={loading}>
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p>拖入 ECP 下载的招标文件包（.zip），自动解析为 TRM</p>
            <Button loading={loading}>选择文件</Button>
          </Upload.Dragger>
        </Card>
        {summary && (
          <Card title="解析摘要" style={{ marginTop: 16 }}>
            <Typography.Paragraph><pre>{summary}</pre></Typography.Paragraph>
          </Card>
        )}
      </Content>
    </Layout>
  )
}
