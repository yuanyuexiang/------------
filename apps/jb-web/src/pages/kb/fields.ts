import type { KbKind } from '../../api'

/**
 * 知识库各类条目的字段规格：驱动通用表格列 + 新增/编辑表单（KbItemsTab）。
 * 与 packages/jb_kb/models.py 对齐；新增后端字段时在这里加一行即可出现在页面。
 *
 * type：text | textarea | number | date | bool3（是/否/未录入）| tags（字符串列表）| kv（键值对，产品参数）| select
 */
export type FieldType = 'text' | 'textarea' | 'number' | 'date' | 'bool3' | 'tags' | 'kv' | 'select'
export interface FieldSpec {
  key: string
  label: string
  type?: FieldType
  options?: string[]        // select / tags 的候选
  required?: boolean
  width?: number            // 表格列宽；不设则不在表格显示（只在表单）
  hint?: string
}
export interface KindSpec {
  kind: KbKind
  title: string
  attachmentKind: string    // 上传附件时的分类
  fields: FieldSpec[]
  note?: string             // 页面顶部的业务提示（国网口径）
}

const STATUS: FieldSpec = { key: 'status', label: '审核', type: 'select', options: ['approved', 'draft'], width: 84 }
const SOURCE: FieldSpec = { key: 'source', label: '出处', type: 'text', hint: '建档依据（文件名/页码），便于人工核对' }

export const KIND_SPECS: KindSpec[] = [
  {
    kind: 'certificates', title: '证照', attachmentKind: 'certificate',
    note: '填写证照到期日后，可查看未来 30、60、90 天内的到期提醒。未填写日期的证照会提示补录。',
    fields: [
      { key: 'name', label: '证书名称', required: true, width: 200 },
      { key: 'cert_type', label: '类型', type: 'select', options: ['体系认证', '资质等级', '许可证', '信用等级', '高新/专精特新', '其他'], width: 110 },
      { key: 'number', label: '证书编号', width: 150 },
      { key: 'level', label: '等级', width: 80 },
      { key: 'issuer', label: '发证机关', width: 130 },
      { key: 'validity_kind', label: '有效期类型', type: 'select', options: ['dated', 'permanent', 'point_in_time'], width: 110 },
      { key: 'includes_tax_registration', label: '包含税务登记信息（多证合一）', type: 'bool3' },
      { key: 'valid_from', label: '起始日', type: 'date' },
      { key: 'valid_until', label: '有效期至', type: 'date', width: 100 },
      STATUS, SOURCE,
    ],
  },
  {
    kind: 'personnel', title: '人员', attachmentKind: 'person',
    note: '请按本包要求准备身份证、学历证、职称证书、资格证书、社保证明、劳动合同和服务项目证明等材料，并核对社保缴纳单位是否符合要求。',
    fields: [
      { key: 'name', label: '姓名', required: true, width: 100 },
      { key: 'title', label: '职务/职称', width: 140 },
      { key: 'major', label: '专业' },
      { key: 'graduation_date', label: '毕业日期（证书载明）', type: 'date' },
      { key: 'relevant_experience_years', label: '相关工作年限', type: 'number', hint: '依有效经历证明录入，不按年龄推算' },
      { key: 'experience_source', label: '相关经历证明及年限计算依据', type: 'textarea' },
      { key: 'education', label: '学历', width: 90 },
      { key: 'social_insurance_unit', label: '社保缴纳单位', width: 160 },
      { key: 'available', label: '能否参加项目', type: 'bool3', width: 90 },
      { key: 'credentials', label: '证件', type: 'tags', options: ['身份证', '学历证', '职称证书', '资格证书', '社保证明', '劳动合同', '服务项目证明'], width: 240 },
      { key: 'social_insurance_months', label: '社保缴纳月份（如 2026-10）', type: 'tags', width: 220 },
      STATUS, SOURCE,
    ],
  },
  {
    kind: 'performances', title: '业绩', attachmentKind: 'performance',
    note: '请对照采购要求，核对合同买方是否为项目实际使用单位、合同和发票是否齐全、签约日期是否符合年限要求。未填写的信息会提示进一步核实。',
    fields: [
      { key: 'project', label: '项目名称', required: true, width: 220 },
      { key: 'buyer', label: '买方', width: 150 },
      { key: 'buyer_type', label: '买方类型', type: 'select', options: ['国网单位', '南网单位', '其他电力', '非电力'] },
      { key: 'buyer_is_end_user', label: '买方是否为项目实际使用单位', type: 'bool3', width: 90 },
      { key: 'in_sgcc', label: '是否为国家电网项目', type: 'bool3' },
      { key: 'amount_wan', label: '合同金额（万元）', type: 'number', width: 100 },
      { key: 'signed_date', label: '签约日期', type: 'date', width: 110 },
      { key: 'commissioned_date', label: '投运日期', type: 'date' },
      { key: 'material_category', label: '物料类别' },
      { key: 'voltage_level', label: '电压等级' },
      { key: 'evidence', label: '证据', type: 'tags', options: ['合同', '发票', '中标通知书', '验收报告', '用户证明'], width: 130 },
      STATUS, SOURCE,
    ],
  },
  {
    kind: 'financials', title: '财务', attachmentKind: 'financial',
    fields: [
      { key: 'year', label: '年度', required: true, width: 90 },
      { key: 'report_kind', label: '财务数据来源', type: 'select', options: ['independent', 'comparative'], hint: '选择该年度独立审计报告，或其他年度审计报告中列出的该年度对比数据' },
      { key: 'revenue_wan', label: '营业收入（万元）', type: 'number', width: 120 },
      { key: 'net_profit_wan', label: '净利润（万元）', type: 'number', width: 120 },
      { key: 'asset_wan', label: '总资产（万元）', type: 'number', width: 120 },
      { key: 'liability_ratio', label: '资产负债率', width: 110 },
      STATUS, SOURCE,
    ],
  },
  {
    kind: 'products', title: '产品', attachmentKind: 'product',
    note: '填写产品的参数名称和具体数值，系统将与采购要求逐项比较。功能特性用于说明产品具备哪些能力。',
    fields: [
      { key: 'model', label: '型号', required: true, width: 160 },
      { key: 'name', label: '名称', width: 200 },
      { key: 'category', label: '物料类别', width: 140 },
      { key: 'params', label: '参数表', type: 'kv', width: 320, hint: '每行一个：参数名=值' },
      { key: 'features', label: '功能特性', type: 'tags' },
      { key: 'test_reports', label: '关联检测报告', type: 'tags' },
      { key: 'spec_ids', label: '适用的技术规范书编号', type: 'tags' },
      STATUS, SOURCE,
    ],
  },
  {
    kind: 'test_reports', title: '检测报告', attachmentKind: 'test_report',
    note: '型式试验/检测/鉴定报告，资格条件常要求"在有效期内"，证照到期提醒按开标日推算。',
    fields: [
      { key: 'name', label: '报告名称', required: true, width: 240 },
      { key: 'report_type', label: '类型', type: 'select', options: ['型式试验', '检测', '鉴定'], width: 100 },
      { key: 'agency', label: '出具机构', width: 160 },
      { key: 'number', label: '编号' },
      { key: 'issued_date', label: '出具日期', type: 'date' },
      { key: 'valid_until', label: '有效期至', type: 'date', width: 100 },
      { key: 'covered_models', label: '覆盖型号', type: 'tags', width: 200 },
      STATUS, SOURCE,
    ],
  },
  {
    kind: 'boilerplates', title: '常用段落', attachmentKind: 'other',
    note: '保存售后服务、质量保证、培训等常用段落。AI 起草方案时只使用已审核的段落，具体承诺仍需按本项目核对。',
    fields: [
      { key: 'topic', label: '主题', type: 'select', options: ['售后服务', '质量保证', '培训', '保密', '应急', '实施方案', '其他'], required: true, width: 110 },
      { key: 'title', label: '标题', required: true, width: 200 },
      { key: 'text', label: '正文', type: 'textarea', width: 330 },
      { key: 'applicable_types', label: '适用类型', type: 'tags', options: ['物资', '服务'], width: 120 },
      { key: 'approved', label: '已审核', type: 'bool3', width: 90 },
      SOURCE,
    ],
  },
]

export const KIND_BY_KEY = Object.fromEntries(KIND_SPECS.map((k) => [k.kind, k])) as Record<KbKind, KindSpec>

export const KIND_TITLES: Record<KbKind, string> = Object.fromEntries(KIND_SPECS.map((k) => [k.kind, k.title])) as Record<KbKind, string>
