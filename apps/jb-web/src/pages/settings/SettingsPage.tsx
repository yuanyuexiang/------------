import { useSearchParams } from 'react-router-dom'
import { Alert, Menu, Typography } from 'antd'
import { FileTextOutlined, SafetyCertificateOutlined, RobotOutlined, HistoryOutlined } from '@ant-design/icons'
import { useAuth } from '../../auth'
import ScoringTemplatesTab from './ScoringTemplatesTab'
import RulesTab from './RulesTab'
import Usage from './LlmTab'
import ConnectionManager from './ConnectionManager'
import './SettingsPage.css'

const sections = {
  templates: { title: '评分模板', description: '维护评分项目和得分标准，用于预估本项目的商务分和技术分。', content: <ScoringTemplatesTab /> },
  rules: { title: '文件检查规则', description: '选择需要检查的问题，并设置风险级别和检查标准。', content: <RulesTab /> },
  llm: { title: 'AI 模型', description: '添加 AI 服务，测试能否使用，并选择默认模型。', content: <ConnectionManager /> },
  usage: { title: 'AI 使用记录', description: '查看 AI 的使用次数、用量、失败原因和对应任务。', content: <Usage /> },
}

export default function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab') ?? 'templates'
  const tab = requested in sections ? requested as keyof typeof sections : 'templates'
  const user = useAuth(s => s.user)
  return <div className="settings-workspace">
    <nav className="settings-navigation" aria-label="设置分类">
      <div className="settings-navigation-title">系统设置</div>
      <Menu selectedKeys={[tab]} mode="inline" onClick={({ key }) => setParams({ tab: key })} items={[
        { type: 'group', label: '投标标准', children: [
          { key: 'templates', icon: <FileTextOutlined />, label: '评分模板' },
          { key: 'rules', icon: <SafetyCertificateOutlined />, label: '文件检查规则' },
        ] },
        { type: 'group', label: 'AI 服务', children: [
          { key: 'llm', icon: <RobotOutlined />, label: 'AI 模型' },
          { key: 'usage', icon: <HistoryOutlined />, label: 'AI 使用记录' },
        ] },
      ]} />
    </nav>
    <section className="settings-detail" aria-label={sections[tab].title}>
      <header className="settings-detail-heading">
        <Typography.Title level={4}>{sections[tab].title}</Typography.Title>
        <Typography.Text type="secondary">{sections[tab].description}</Typography.Text>
      </header>
      {user?.role !== 'admin' && <Alert type="info" showIcon message="您可以查看设置；修改设置需要管理员权限" style={{ marginBottom: 16 }} />}
      <div key={tab}>{sections[tab].content}</div>
    </section>
  </div>
}
