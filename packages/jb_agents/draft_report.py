"""生成后的集中处理清单；不替代版本合规审查或正式导出门禁。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .writer import Draft


class ConfirmationItem(BaseModel):
    category: Literal['本次投标事实待确认', '企业事实待补充', 'AI 起草需重试', '拟实施方案待确认', '原文需核对', '方案响应待完善', '引用依据待核对', '招标原文待核对', '系统生成待修复']
    location: str
    message: str
    action: str
    occurrences: int = 1
    locations: list[str] = []
    details: list[dict[str, str]] = Field(default_factory=list)


def confirmation_items(draft: Draft | None,
                       todos: dict[str, list[str]]) -> list[ConfirmationItem]:
    items: list[ConfirmationItem] = []
    seen: dict[str, ConfirmationItem] = {}

    def add(category, location, message, action):
        from jb_docgen.gaps import is_team_gap
        detail = {'message': message, 'location': location}
        key = 'team-facts' if is_team_gap(message) else message
        if key == 'team-facts':
            message = '本包团队名单、岗位与资格证据（集中核对）'
            category = '本次投标事实待确认'
            action = '在本次项目团队中让AI检索现有证据、推荐岗位；确认人选与可投入状态，各章节共用'
        if key in seen:
            item = seen[key]
            item.occurrences += 1
            if detail not in item.details:
                item.details.append(detail)
            if location not in item.locations:
                item.locations.append(location)
                item.location = '；'.join(item.locations)
        else:
            item = ConfirmationItem(category=category, location=location, message=message,
                                    action=action, locations=[location], details=[detail])
            items.append(item)
            seen[key] = item


    if draft:
        for warning in draft.warnings:
            retry = '起草' in warning
            add('AI 起草需重试' if retry else '原文需核对', '起草检查', warning,
                '检查模型配置后重新生成' if retry else '核对本包规范书原件后重新生成')
        for section in draft.sections:
            if section.by_llm:
                add('拟实施方案待确认', section.title, 'AI 已起草本节，需确认实施可行性与对外承诺',
                    '由投标负责人审阅生成稿；变更基础资料后重新生成并复查')
    for filename, entries in todos.items():
        for message in entries:
            if any(word in message for word in ('数值需核实来源', '引用来源需核实', 'AI角色')):
                add('系统生成待修复', filename, message,
                    '系统先规范引用并检索本包证据后重试；不要求企业补交资料，修复失败保留核查记录')
                continue
            if '人员关系' in message or '关系说明' in message:
                original = '原文' in message
                add('原文需核对' if original else '本次投标事实待确认', filename, message,
                    '核对本次招标原文及格式，无需另行提供承诺书模板' if original else
                    '在工作台确认本包关系情况；存在相关情形时填写双方人员信息，再重新生成')
                continue
            if any(word in message for word in ('招标编号', '采购编号', '分标名称', '招标文件', '招标范围', '技术规范', '采购方要求')):
                add('招标原文待核对', filename, message,
                    '由系统从采购文件和本包规范正文提取；确实没有原件时才补交文件')
                continue
            if '签约日期' in message:
                add('企业事实待补充', filename, message,
                    '在投标准备任务的历史合同日期中选择对应业绩，对照合同签署页填写日期和依据')
                continue
            if any(word in message for word in ('被授权人', '拟任', '拟投入', '可投入', '开工日期')):
                add('本次投标事实待确认', filename, message,
                    '由投标负责人确认本次人选、安排或日期；不要求补写章节')
                continue
            retry = any(word in message for word in ('LLM', '模型未配置', 'AI 起草失败', '起草失败'))
            plan = any(word in message for word in ('具体响应', '逐项响应', '逐条编制', '本节内容'))
            evidence = any(word in message for word in ('数值需核实来源', '引用来源需核实'))
            category = ('AI 起草需重试' if retry else '引用依据待核对' if evidence else
                        '方案响应待完善' if plan else '企业事实待补充')
            action = ('检查模型配置后重新生成' if retry else
                      '对照起草引用依据与原文核对该句；拟定方法及承诺由技术负责人确认' if evidence else
                      '对照 AI 方案核对规范书逐条响应；产品性能仍须提供真实证据' if plan else
                      '核对招标要求与企业证据，补充真实资料后重新生成')
            add(category, filename, message, action)
    return items
