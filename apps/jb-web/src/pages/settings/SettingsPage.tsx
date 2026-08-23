import { useSearchParams } from 'react-router-dom'
import { Alert, Card, Tabs } from 'antd'
import { useAuth } from '../../auth'
import ScoringTemplatesTab from './ScoringTemplatesTab'
import RulesTab from './RulesTab'
import LlmTab from './LlmTab'

/** 配置中心：评分模板库 / 否决规则库 / LLM 设置。Tab 记在 URL（?tab=）。 */
export default function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'templates'
  const user = useAuth((s) => s.user)
  return (
    <Card size="small" title="配置中心">
      {user?.role !== 'admin' && <Alert type="info" showIcon style={{ marginBottom: 12 }} message="只读：配置中心的修改需要管理员权限" />}
      <Tabs activeKey={tab} onChange={(k) => setParams({ tab: k })} destroyInactiveTabPane
        items={[
          { key: 'templates', label: '评分模板库', children: <ScoringTemplatesTab /> },
          { key: 'rules', label: '否决规则库', children: <RulesTab /> },
          { key: 'llm', label: 'LLM 设置', children: <LlmTab /> },
        ]} />
    </Card>
  )
}
