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
  templates: { title: '评分模板', description: '维护评审要素和评分标准，供项目模拟评分使用。', content: <ScoringTemplatesTab /> },
  rules: { title: '否决规则', description: '管理合规检查规则及适用参数。', content: <RulesTab /> },
  llm: { title: 'AI 模型', description: '接入模型服务商，验证调用并选择默认模型。', content: <ConnectionManager /> },
  usage: { title: '调用日志', description: '查看模型用量、调用结果和关联任务。', content: <Usage /> },
}

export default function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const requested = params.get('tab') ?? 'templates'
  const tab = requested in sections ? requested as keyof typeof sections : 'templates'
  const user = useAuth(s => s.user)
  return <div className="settings-workspace">
    <nav className="settings-navigation" aria-label="配置分类">
      <div className="settings-navigation-title">工作空间设置</div>
      <Menu selectedKeys={[tab]} mode="inline" onClick={({ key }) => setParams({ tab: key })} items={[
        { type: 'group', label: '投标标准', children: [
          { key: 'templates', icon: <FileTextOutlined />, label: '评分模板' },
          { key: 'rules', icon: <SafetyCertificateOutlined />, label: '否决规则' },
        ] },
        { type: 'group', label: 'AI 服务', children: [
          { key: 'llm', icon: <RobotOutlined />, label: 'AI 模型' },
          { key: 'usage', icon: <HistoryOutlined />, label: '调用日志' },
        ] },
      ]} />
    </nav>
    <section className="settings-detail" aria-label={sections[tab].title}>
      <header className="settings-detail-heading">
        <Typography.Title level={4}>{sections[tab].title}</Typography.Title>
        <Typography.Text type="secondary">{sections[tab].description}</Typography.Text>
      </header>
      {user?.role !== 'admin' && <Alert type="info" showIcon message="只读：配置中心的修改需要管理员权限" style={{ marginBottom: 16 }} />}
      <div key={tab}>{sections[tab].content}</div>
    </section>
  </div>
}
