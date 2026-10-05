import { useState } from 'react'
import { Drawer, Menu, Tabs } from 'antd'
import { QuestionCircleOutlined } from '@ant-design/icons'

const steps = [
  ['导入招标文件', '在「投标项目」上传 ECP 下载的 ZIP 文件，等待解析完成后打开项目详情。'],
  ['核对招标要求', '进入「招标要求确认」，对照原件检查关键条款和分包要求，补齐可编辑字段并保存确认版。'],
  ['准备企业资料', '在「企业知识库」维护企业信息、证照、人员、业绩与产品参数，挂载对应证明材料。'],
  ['自检与生成', '运行资格自检，再到工作台选择企业档案与分包，生成商务、技术文件。'],
  ['整改与正式导出', '补齐待补充项，重新生成并审查当前版本，通过导出检查后下载正式文件。签章与递交仍需在投标工具中完成。'],
]

const materials = [
  ['企业信息', '营业执照、统一社会信用代码、法定代表人、授权代表、联系方式及账户资料。'],
  ['资质与证照', '招标要求的资质、体系认证与检测报告，录入有效期并上传清晰扫描件。'],
  ['人员材料', '拟投入人员信息、资格证书、社保证明与缴纳月份，以及招标要求的其他材料。'],
  ['业绩证明', '项目名称、买方、金额、签约或投运日期，以及对应合同、发票等证明。'],
  ['产品与方案', '产品型号、参数、功能事实，以及经审核的服务与质量保证材料。'],
]

export default function SidebarHelp({ collapsed }: { collapsed: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Menu theme="dark" mode="inline" inlineCollapsed={collapsed} selectable={false}
        aria-label="使用帮助" onClick={() => setOpen(true)}
        items={[{ key: 'help', icon: <QuestionCircleOutlined />, label: '使用帮助' }]} />
      <Drawer title="使用帮助" open={open} onClose={() => setOpen(false)} width={440} className="help-drawer">
        <p className="help-intro">从资料准备到文件导出，按步骤完成本次投标。</p>
        <Tabs items={[
          { key: 'guide', label: '操作指南', children: <ol className="help-steps">{steps.map(([title, text]) => (
            <li key={title}><h3>{title}</h3><p>{text}</p></li>
          ))}</ol> },
          { key: 'materials', label: '材料清单', children: <div className="help-materials">
            <p className="help-note">以下为常见材料，具体范围以本次招标文件为准。</p>
            {materials.map(([title, text]) => <section key={title}><h3>{title}</h3><p>{text}</p></section>)}
          </div> },
          { key: 'feedback', label: '问题反馈', children: <div className="help-feedback">
            <h3>联系企业管理员</h3>
            <p>遇到账号、资料或操作问题，请联系企业管理员；系统问题由管理员联系维护人员处理。</p>
            <h3>反馈时请提供</h3>
            <ul><li>项目名称、分标与包号</li><li>出问题的页面与操作步骤</li><li>页面提示、发生时间及必要截图</li></ul>
            <p className="help-note">请勿在反馈中包含密码、密钥或无关的个人证件信息。</p>
          </div> },
        ]} />
      </Drawer>
    </>
  )
}
