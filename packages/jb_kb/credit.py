"""按真实查询来源归类信用证据；材料已提供不等于资格自动通过。"""
from __future__ import annotations

import re

from .models import CompanyProfile

CREDIT_GROUPS = (
    ('信用中国', ('信用中国', '公共信用')),
    ('国家企业信用信息公示系统', ('企业信用信息公示',)),
    ('中国裁判文书网', ('裁判文书',)),
    ('中国执行信息公开网', ('执行信息公开', '失信被执行人')),
    ('全国建筑市场监管公共服务平台', ('建筑市场',)),
    ('国网供应商不良行为', ('国网', '国家电网')),
)


def credit_materials(profile: CompanyProfile) -> dict:
    groups = {label: [] for label, _ in CREDIT_GROUPS}
    for cert in profile.certificates:
        if cert.status != 'approved' or not cert.attachments:
            continue
        # 不用 source 的目录路径判断网站：客户目录可能混放多个网站截图。
        title = cert.name + ' ' + cert.issuer
        for label, keywords in CREDIT_GROUPS:
            if any(word in title for word in keywords):
                if label == '国网供应商不良行为' and '不良行为' not in title:
                    continue
                groups[label].append(cert)
                break
    return groups


def grid_credit_requirement(trm=None, pkg=None) -> dict:
    """只依据本包和批次公共条款区分提交义务与资格限制，不推断企业事实。"""
    entries = []
    if pkg is not None:
        for q in pkg.qualification:
            entries.extend(('本包资格要求', value) for value in q.other_reqs.values())
        entries.extend(('本包需求清单', value) for value in pkg.demand_details.values())
    if trm is not None:
        entries.extend(('前附表 ' + x.clause_no, x.content) for x in trm.prenotice)
        entries.extend(('否决条款 ' + x.aspect, x.text) for x in trm.rejection_rules)
        entries.extend(('提交清单 ' + x.seq, x.item) for x in trm.submission_table)
        entries.extend(('文件格式 ' + x.title, p) for x in trm.format_blocks
                       for p in ([x.title] + x.paragraphs))
    modes, sources = set(), []
    for location, text in entries:
        # 不跨句借用“信用中国截图”或其他资料的提交指令。
        for clause in re.split(r'[。；\n]', text):
            if '不良行为' not in clause or not re.search(r'国家电网|国网|供应商不良行为', clause):
                continue
            sources.append(f'{location}：{clause.strip()}')
            evidence = bool(re.search(r'截图|截屏|查询结果|查询凭证|查询报告', clause))
            submit = bool(re.search(r'(?:应|须|需|必须).{0,8}(?:提供|提交|附)|提交|上传|附上', clause))
            exempt = bool(re.search(r'无需|不需|不要求|免予', clause))
            buyer = bool(re.search(r'(?:采购人|招标人|评标委员会|评审委员会).{0,12}(?:查询|核查|核验)', clause))
            declaration = bool(re.search(r'承诺书|声明|我方.{0,20}承诺', clause))
            if evidence and submit and not exempt:
                modes.add('evidence')
            elif declaration and (submit or location.startswith('文件格式')):
                modes.add('declaration')
            elif evidence and exempt:
                modes.add('exempt')
            elif buyer:
                modes.add('buyer')
            else:
                modes.add('condition')
    mode = ('conflict' if 'evidence' in modes and 'exempt' in modes else
            next((x for x in ('evidence', 'declaration', 'exempt', 'buyer', 'condition') if x in modes), 'unspecified'))
    return {'mode': mode, 'sources': list(dict.fromkeys(sources))}


def credit_check(profile: CompanyProfile, trm=None, pkg=None) -> tuple[str, list[str]]:
    groups = credit_materials(profile)
    evidence = [f'{label}：{c.name}；查询/出具日期 {c.valid_from or "未录入"}；'
                f'已关联附件 {len(c.attachments)} 份'
                for label, certs in groups.items() for c in certs]
    required = ('信用中国', '国家企业信用信息公示系统', '中国裁判文书网')
    missing = [label for label in required if not groups[label]]
    message = ('已关联查询材料：' + '、'.join(label for label, certs in groups.items() if certs) + '。'
               if evidence else '当前选材中尚未关联已审核的信用查询附件。')
    if missing:
        message += '尚未关联：' + '、'.join(missing) + '；按本包要求确认适用范围及是否需补充。'
    requirement = grid_credit_requirement(trm, pkg)
    mode = requirement['mode']
    if mode == 'evidence':
        message += ('本包原文要求提交国网供应商不良行为查询凭证，已关联材料，请核对范围及时效。'
                    if groups['国网供应商不良行为'] else
                    '本包原文要求提交国网供应商不良行为查询凭证，尚未关联；无不良行为也应提供对应查询结果。')
    elif mode == 'declaration':
        message += '本包要求国网供应商不良行为承诺或声明，请核实企业情况并审阅生成稿中的原文承诺；未识别到额外截图提交要求。'
    elif mode in ('buyer', 'exempt'):
        message += '国网供应商不良行为由采购方核查或原文明示无需提交查询附件，不因未上传截图列为资料缺项。'
    elif mode == 'condition':
        message += '国网供应商不良行为条款属于资格限制，未识别到单独查询截图提交要求，不列为截图缺项；仍须核实是否存在本包限制参与的处理情形。'
    elif mode == 'conflict':
        message += '国网供应商不良行为查询材料的提交与免交条款存在不同表述，请核对适用范围；暂不自动判为缺材料或免交。'
    else:
        message += '已解析内容中未识别到国网供应商不良行为查询附件的提交要求，不自动新增截图缺项；以本包采购原文为准。'
    evidence.extend('要求原文：' + value for value in requirement['sources'])
    message += '已有附件可复用，请核验查询主体、结果、查询日期是否符合本次招标要求；不要求重复提交已有材料。'
    return message, evidence
