"""生成前检查：解析缺失与业务确认分开，不能以企业材料代替采购要求。"""
from jb_parser.trm import TRM, PackageTRM


def generation_issues(trm: TRM, pkg: PackageTRM) -> list[dict]:
    issues = []
    for label, value in [('采购编号', trm.batch_no), ('批次名称', trm.batch_name),
                         ('包号', pkg.pkg_no), ('分标名称', pkg.sub_name)]:
        if not value:
            issues.append({'category': '招标解析待处理', 'message': f'{label}未提取',
                           'action': '重新解析采购原件并核对需求清单', 'blocking': True})
    if not pkg.spec_docs or all(s.n_paragraphs <= 10 and not s.param_rows for s in pkg.spec_docs):
        issues.append({'category': '原文件待核对', 'message': '未识别到可响应的技术规范正文',
                       'action': '检查原包是否包含正文；只有封面时补交完整规范书', 'blocking': True})
    for warning in trm.warnings:
        issues.append({'category': '招标原件提示', 'message': warning,
                       'action': '以当前包号、需求清单及匹配的正文为依据，核对冲突附件', 'blocking': False})
    return issues
