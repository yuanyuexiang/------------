"""本包人员安排与授权附件装配；不依赖数据库。"""
import re

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def append_team_document(path, profile):
    """将本包岗位与承诺确定性写入技术文件，避免模型漏写或把全局可用状态当成本包承诺。"""
    team = profile.bid_context.get('team')
    if not team:
        if profile.bid_context.get('reference_source'):
            from . import master as M
            from .placeholders import todo
            doc = Document(path)
            anchor = M.find_paragraph(doc, r'^10[.．、]其他$', max_len=15)
            last = anchor._p if anchor is not None else M.last_body_element(doc)
            last = M.insert_heading_after(doc, last, '本次人员安排核对', level=2)._p
            last = M.insert_paragraph_after(doc, last, '人员名单、岗位及证明材料按指定成品资料整理；'
                                            '历史资料不能自动证明本包当前可投入状态。')._p
            note = M.insert_paragraph_after(
                doc, last, todo('本包团队专业、相关经历、可投入状态与到岗承诺确认'))
            if anchor is not None:
                section = anchor._p.find('./' + qn('w:pPr') + '/' + qn('w:sectPr'))
                if section is not None:
                    # 空“其他”标题自身可能携带下一页分节；补入正文后将节尾移到正文后。
                    section.getparent().remove(section)
                    kind = section.find(qn('w:type'))
                    if kind is None:
                        kind = OxmlElement('w:type')
                        section.insert(0, kind)
                    kind.set(qn('w:val'), 'continuous')
                    note._p.get_or_add_pPr().append(section)
            doc.save(path)
        return
    from .placeholders import todo
    doc = Document(path)
    doc.add_heading('本次项目团队与到岗安排', level=2)
    doc.add_paragraph('以下安排经本次投标负责人确认；人员资格及工作经历以所附证明为准。')
    table = doc.add_table(rows=1, cols=4)
    for cell, value in zip(table.rows[0].cells, ('姓名', '本次岗位', '可投入状态', '资格与经历依据')):
        cell.text = value
    people = {x.id: x for x in profile.personnel}
    for member in team['members']:
        person = people.get(member['person_id'])
        if person is None:
            continue
        cells = table.add_row().cells
        cells[0].text, cells[1].text = person.name, member['role']
        cells[2].text = '本包已确认可投入' if member['available'] else todo(person.name + '本包可投入状态')
        cells[3].text = '；'.join(x for x in [person.education, person.major, person.title,
                                             person.experience_source, person.source] if x)
    if team['arrival_commitment'] and all(x['available'] for x in team['members']) and team['members']:
        doc.add_heading('本次人员到岗承诺', level=3)
        doc.add_paragraph(f'{profile.name}承诺按本次确认的岗位安排组织上述人员到岗，'
                          '具体到岗时间、采购人审核和人员变更按采购文件及合同约定执行。')
        doc.add_paragraph('投标人（盖章）：\n授权代表（签字）：\n日期：')
    else:
        doc.add_paragraph(todo('拟投入本包人员名单及到岗承诺'))
    doc.save(path)


def append_authorization_document(path, ctx):
    authority = ctx.profile.bid_context.get('authorization')
    if not authority:
        return
    from .master_builder import _insert_scans
    from .placeholders import todo
    doc = Document(path)
    if any(re.search(r'授权委托书.*本项目无需提供', p.text) for p in doc.paragraphs):
        return
    heading = doc.add_heading('本次授权人身份证明附件', level=2)
    if authority['attachments']:
        _insert_scans(ctx, doc, heading._p, authority['attachments'], authority['name'] + '身份证明')
    else:
        doc.add_paragraph(todo('被授权人' + authority['name'] + '身份证明附件'))
    doc.save(path)
