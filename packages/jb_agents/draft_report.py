"""生成后的集中处理清单；不替代版本合规审查或正式导出门禁。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .writer import Draft


class ConfirmationItem(BaseModel):
    category: Literal['本次投标事实待确认', '企业事实待补充', 'AI 起草需重试', '拟实施方案待确认', '原文需核对', '方案响应待完善', '引用依据待核对']
    location: str
    message: str
    action: str


def confirmation_items(draft: Draft | None,
                       todos: dict[str, list[str]]) -> list[ConfirmationItem]:
    items: list[ConfirmationItem] = []
    seen: set[tuple[str, str]] = set()

    def add(category, location, message, action):
        key = (location, message)
        if key not in seen:
            items.append(ConfirmationItem(category=category, location=location,
                                          message=message, action=action))
            seen.add(key)

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
            if '人员关系' in message or '关系说明' in message:
                original = '原文' in message
                add('原文需核对' if original else '本次投标事实待确认', filename, message,
                    '核对本次招标原文及格式，无需另行提供承诺书模板' if original else
                    '在工作台确认本包关系情况；存在相关情形时填写双方人员信息，再重新生成')
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
