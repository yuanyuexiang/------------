/** Display labels only. API values and procurement source text remain unchanged. */
const label = (labels: Record<string, string>, value: string) => labels[value] ?? value

export const reviewLevelLabel = (value: string) => label({
  否决: '否决风险', 扣分: '扣分风险', 建议: '修改建议', 需人工: '需要核实',
}, value)
export const checkStatusLabel = (value: string) => label({ 需人工: '需要核实' }, value)
export const taskKindLabel = (value: string) => label({
  parse: '读取采购文件', generate: '生成标书', qualify: '检查投标资格', review: '检查投标文件',
  score: '预估评分', suggest: '查找已有资料', preparation: '更新投标准备资料',
  materials: '选择投标资料', relationship: '核对人员关系', reparsed: '重新读取采购文件',
}, value)
export const projectStageLabel = (value: string) => label({
  parsed: '已读取采购文件', confirmed: '已核对采购信息', qualified: '已检查资格',
  generated: '已生成标书', reviewed: '已检查标书', submitted: '已提交',
}, value)
export const scoreKindLabel = (value: string) => label({ tech: '技术', biz: '商务' }, value)
export const scoreMethodLabel = (value: string) => label({
  hard: '按规则计算', llm: 'AI 估分', range: '仅提供分数范围',
}, value)
export const attachmentKindLabel = (value: string) => label({
  certificate: '证照', person: '人员证明', performance: '业绩证明', financial: '财务报告',
  product: '产品资料', test_report: '检测报告', other: '其他材料',
}, value)
export const kbOptionLabel = (value: string) => label({
  approved: '已审核', draft: '待审核', independent: '该年度独立审计报告',
  comparative: '其他年度报告中的对比数据', dated: '有固定到期日', permanent: '长期有效',
  point_in_time: '查询当天的记录',
}, value)

/** Older task records can still contain internal terms; translate their status text for display. */
export function taskMessageLabel(value: string): string {
  return value.replace(/\bTRM\b/g, '采购信息').replace(/\bLLM\b/g, 'AI')
    .replace(/前附表条款/g, '采购重要事项').replace(/提交方式表/g, '文件提交要求')
    .replace(/术语体系/g, '采购文件用语').replace(/标包/g, '采购包')
    .replace(/合规审查/g, '检查投标文件').replace(/资格自检/g, '检查投标资格')
    .replace(/模拟评分/g, '预估评分').replace(/母版版式/g, '采购规定格式')
    .replace(/入库/g, '保存').replace(/被阻断/g, '未能完成')
    .replace(/知识库/g, '企业资料').replace(/已审核候选/g, '已审核人员可供选择')
    .replace(/已确认可投入/g, '已确认参加项目')
}

export function purchaseWarningLabel(value: string): string {
  if (value.includes('排除与需求清单项目名称不一致的规范文件')) {
    const pkg = value.match(/^([^：:]{1,40})[：:]/)?.[1]
    return `${pkg ? pkg + '：' : ''}已忽略项目名称不符的技术规范书。请核对采购包和对应的技术规范书是否正确。`
  }
  return taskMessageLabel(value)
}

export function errorMessage(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error ?? '')
  if (/^(Failed to fetch|NetworkError|Load failed|Network request failed)/i.test(text)) {
    return '无法连接系统，请检查网络后重试。'
  }
  if (text === 'Forbidden') return '您没有执行此操作的权限，请联系管理员。'
  if (text === 'Unauthorized') return '登录已失效，请重新登录。'
  if (text === 'Not Found') return '没有找到对应的资料，请刷新页面后重试。'
  if (text === 'Internal Server Error') return '系统处理失败，请稍后重试；若仍失败，请联系管理员。'
  if (/^(Bad Gateway|Service Unavailable|Gateway Timeout)$/.test(text)) {
    return '系统暂时无法响应，请稍后重试。'
  }
  return taskMessageLabel(text.replace(/^Error:\s*/, '')) || '操作未完成，请重试。'
}

/** FastAPI validation details are objects; do not expose [object Object] to users. */
export function requestErrorText(detail: unknown): string {
  if (typeof detail === 'string') return errorMessage(detail)
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {
      name: '名称', username: '登录账号', password: '密码', old_password: '原密码',
      new_password: '新密码', credit_code: '统一社会信用代码', profile: '企业档案',
      pkg_index: '采购包', base_url: '服务接口地址', api_key: '服务密钥', model: 'AI 模型',
      timeout: '最长等待时间', max_tokens: '回复长度上限', temperature: '回答变化程度',
    }
    const messages = detail.map(item => {
      const field = Array.isArray(item?.loc) ? fields[String(item.loc.at(-1))] : undefined
      return `${field ?? '填写的信息'}${item?.type === 'missing' ? '不能为空' : '格式或取值不符合要求，请检查后重试'}`
    })
    return [...new Set(messages)].join('；') || '填写的信息不符合要求，请检查后重试。'
  }
  return '操作未完成，请刷新页面后重试。'
}

const RULE_COPY: Record<string, [string, string]> = {
  'SG-16': ['参数答复是否缺少具体数值', '检查参数答复是否只写了“完全响应”等笼统表述，而没有提供具体数值或说明。'],
  'SG-16b': ['参数答复是否漏填', '检查采购方要求的参数是否已逐项填写，带星号的重点要求也需要答复。'],
  'SG-15': ['产品参数是否符合要求', '比较我方提供的参数与采购要求，提示不符合要求的项目。'],
  'SG-15b': ['重点功能是否需要核实', '无法直接比较数值的重点功能，需要对照产品说明和证明材料逐项核实。'],
  'SG-17': ['技术规范附件是否逐项答复', '部分技术规范书需要在投标工具中以附件逐项答复，请核对采购文件要求。'],
  'DOC-01': ['标书是否还有待补充内容', '检查生成文件中的待补充提示。存在待补充内容时，不能导出正式文件。'],
  'DOC-02~04': ['项目名称和编号是否一致', '核对标书中的项目名称、采购编号和企业名称，避免沿用其他项目的信息。'],
  'SG-13': ['证书是否已过期', '对照开标日期检查证书有效期；没有填写到期日时，会提示进一步核实。'],
  'Q-02': ['所选资料是否符合本包资格要求', '按照本包要求检查实际选用的人员和证明材料，取消选择不能代替补齐必需材料。'],
  'SG-05/06': ['历史业绩证明是否符合要求', '检查合同、发票和项目实际使用单位等信息，核对是否满足本包的业绩要求。'],
  'SG-22': ['人员社保记录是否符合要求', '检查拟安排人员的社保缴纳单位和连续缴纳月份。'],
  'Q-01': ['是否允许多家企业联合投标', '当采购文件不接受联合投标时，需要核对本次投标主体。'],
  'SG-21': ['企业信用记录是否需要更新', '按照本包要求核对企业信用查询材料及查询日期。'],
  'PRICE': ['报价是否存在错误', '检查零单价、超出限价、计算错误及缺少税率等问题。'],
  'SIM-01': ['不同采购包的方案是否过于相似', '比较同一批次不同采购包的技术文件，提示专用方案文字过于相似的风险。'],
  'SUB-01': ['投标材料是否已逐项准备', '核对需要提交的材料，以及在投标工具中的上传位置；工具内操作仍需人工完成。'],
}
export const ruleTitleLabel = (id: string, fallback: string) => RULE_COPY[id]?.[0] ?? fallback
export const ruleDescriptionLabel = (id: string, fallback: string) => RULE_COPY[id]?.[1] ?? fallback
