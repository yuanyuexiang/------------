"""生成前准备门禁；缺少业务确认可明确生成草稿，解析错包不可绕过。"""
from __future__ import annotations

import re

from jb_agents.preflight import generation_issues
from jb_parser.trm import TRM


def readiness(p, index, profile):
    from .preparation import fact_state, team_blockers
    from .workflow import relationship_state, selected_profile

    trm = TRM.model_validate(p.trm_confirmed or p.trm or {})
    if not 0 <= index < len(trm.packages):
        return {'blockers': ['请先选择有效标包'], 'confirmations': [], 'warnings': [], 'ready': False}
    pkg = trm.packages[index]
    issues = generation_issues(trm, pkg)
    blockers = [x['message'] for x in issues if x['blocking']]
    warnings = [x['message'] for x in issues if not x['blocking']]
    confirmations = []
    try:
        chosen = selected_profile(p, index, profile)
        for item in chosen.performances:
            if not item.signed_date:
                warnings.append(f'所选历史业绩《{item.project}》签约日期尚未录入，请核对本包是否要求')
    except ValueError as exc:
        blockers.append(str(exc))
    facts = fact_state(p, index, profile)
    formats = '\n'.join(x.title + '\n' + '\n'.join(x.paragraphs) for x in trm.format_blocks)
    authority = facts['authorization']
    if re.search('授权委托书|授权书|委托代理人', formats):
        if not authority['confirmation'] or authority['stale']:
            confirmations.append({'task': 'authorization', 'title': '本次授权',
                                  'message': '请确认本包被授权人及职务'})
        elif not authority['confirmation']['data'].get('identity_attachments'):
            warnings.append('本次授权尚未关联身份证明，生成稿中将保留缺项提示')
    team = team_blockers(p, index, profile)
    if team:
        confirmations.append({'task': 'team', 'title': '本次项目团队', 'message': '；'.join(team)})
    relationship = relationship_state(p, index, profile.name)
    if relationship['options'] or re.search('与国家电网公司系统人员关系说明', formats):
        if not relationship['confirmation'] or relationship['stale']:
            confirmations.append({'task': 'relationship', 'title': '国网人员关系确认',
                                  'message': '请确认本包适用的人员关系情况'})
    if not trm.format_blocks:
        warnings.append('未解析到完整投标格式，准备检查可能不完整；请核对原件，生成后仍需逐节审阅')
    return {'blockers': list(dict.fromkeys(blockers)), 'confirmations': confirmations,
            'warnings': list(dict.fromkeys(warnings)), 'ready': not blockers and not confirmations}
