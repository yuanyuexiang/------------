import { useSearchParams } from 'react-router-dom'
import { Card, Tabs } from 'antd'
import ScoringTemplatesTab from './ScoringTemplatesTab'
import RulesTab from './RulesTab'
import LlmTab from './LlmTab'

/** 配置中心：评分模板库 / 否决规则库 / LLM 设置。Tab 记在 URL（?tab=）。 */
export default function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'templates'
  return (
    <Card size="small" title="配置中心">
      <Tabs activeKey={tab} onChange={(k) => setParams({ tab: k })} destroyInactiveTabPane
        items={[
          { key: 'templates', label: '评分模板库', children: <ScoringTemplatesTab /> },
          { key: 'rules', label: '否决规则库', children: <RulesTab /> },
          { key: 'llm', label: 'LLM 设置', children: <LlmTab /> },
        ]} />
    </Card>
  )
}
