"""成品导航、章节归属及扫描件边界回归。"""
from types import SimpleNamespace

from docx import Document
from docx.shape import InlineShape
from docx.shared import Cm
from jb_docgen import master as M
from jb_docgen.builder import GenContext
from jb_docgen.master_builder import _insert_drafts
from jb_docgen.navigation import add_navigation
from jb_kb.models import CompanyProfile
from jb_parser.trm import TRM, PackageTRM
from PIL import Image


def test_scan_fits_printable_width_and_height(tmp_path):
    doc = Document()
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(3.17)
    anchor = doc.add_paragraph('证明材料')
    for name, size in [('landscape', (1000, 200)), ('tall', (100, 2000))]:
        path = tmp_path / f'{name}.png'
        Image.new('RGB', size, 'white').save(path)
        paragraph = M.insert_picture_after(doc, anchor._p, str(path))
        assert paragraph is not None
        shape = InlineShape(paragraph._p.xpath('.//wp:inline')[0])
        assert shape.width <= section.page_width - section.left_margin - section.right_margin
        assert shape.height < section.page_height - section.top_margin - section.bottom_margin
        assert abs(shape.width / shape.height - size[0] / size[1]) < 0.001


def test_guidance_cleanup_preserves_required_section():
    doc = Document()
    doc.add_paragraph('（二）专项响应文件（上传招投标交易平台信息系统路径：技术文件）')
    M.remove_guidance(doc)
    assert doc.paragraphs[0].text == '（二）专项响应文件'
    assert doc.paragraphs[0].style.name == 'Heading 1'


def test_drafts_are_placed_under_required_sections_in_template_order():
    doc = Document()
    for title in ['3.对项目的理解', '4.工作规划描述', '5.履约能力及质量保证措施',
                  '6.服务承诺', '7.采购文件技术评分标准涉及的支撑材料']:
        doc.add_paragraph(title)
    drafts = [SimpleNamespace(title=t, text=body) for t, body in [
        ('项目理解与需求分析', '理解正文'), ('文件响应', '文件响应正文'),
        ('质量保证', '质量正文'), ('服务能力', '能力正文'), ('服务方案', '规划正文'),
        ('售后服务与培训', '服务承诺正文')]]
    ctx = GenContext(trm=TRM(), pkg=PackageTRM(), profile=CompanyProfile(name='测试'),
                     drafts=drafts)
    _insert_drafts(doc, ctx)
    text = '\n'.join(p.text for p in doc.paragraphs)
    for start, end, bodies in [
        ('3.对项目的理解', '4.工作规划描述', ['理解正文']),
        ('4.工作规划描述', '5.履约能力及质量保证措施', ['规划正文']),
        ('5.履约能力及质量保证措施', '6.服务承诺', ['质量正文', '能力正文']),
        ('6.服务承诺', '7.采购文件', ['服务承诺正文']),
    ]:
        section = text.split(start, 1)[1].split(end, 1)[0]
        assert all(body in section for body in bodies)
    assert text.index('质量正文') < text.index('能力正文')
    assert text.index('7.采购文件') < text.index('文件响应正文')


def test_navigation_links_to_actual_headings_and_is_idempotent(tmp_path):
    doc = Document()
    doc.add_paragraph('投标文件')
    doc.add_page_break()
    doc.add_heading('业绩文件', level=1)
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = '已核实内容'
    doc.add_heading('人员文件', level=2)
    path = tmp_path / 'bid.docx'
    doc.save(path)
    assert add_navigation(str(path))
    assert not add_navigation(str(path))
    result = Document(path)
    bookmarks = set(result.element.xpath('.//w:bookmarkStart/@w:name'))
    links = result.element.xpath('.//w:hyperlink/@w:anchor')
    assert len(links) == 2 and set(links) <= bookmarks
    assert len(result.element.xpath('.//w:fldSimple[contains(@w:instr,"PAGEREF")]')) == 2
    assert result.tables[0].cell(0, 0).text == '已核实内容'


def test_financial_ratios_use_audited_operating_profit_and_zero_is_not_missing():
    from jb_docgen.master_builder import _fill_financials
    from jb_kb.models import FinancialYear

    doc = Document()
    table = doc.add_table(rows=6, cols=6)
    labels = ['负债总额', '资产负债率＝负债总额÷资产总额×100％',
              '营业利润率＝营业利润÷营业收入净额×100％', '流动比率', '速动比率']
    for cell, text in zip(table.rows[0].cells, ['年份', '财务指标', 'XX年', 'XX年', 'XX年', '平均']):
        cell.text = text
    for i, label in enumerate(labels, 1):
        table.cell(i, 0).text, table.cell(i, 1).text = str(i), label
    profile = CompanyProfile(name='测试', financials=[FinancialYear(
        year=str(y), liability_wan=0, asset_wan=500, revenue_wan=1000,
        operating_profit_wan=100, net_profit_wan=50, current_asset_wan=200,
        current_liability_wan=100, inventory_wan=50, liability_ratio='99%',
    ) for y in [2023, 2024, 2025]])
    _fill_financials(doc, GenContext(trm=TRM(), pkg=PackageTRM(), profile=profile))
    assert table.cell(1, 2).text == '0万元'
    assert table.cell(2, 2).text == '0.00%'
    assert table.cell(3, 2).text == '10.00%'  # 不能把净利润当成营业利润
    assert table.cell(4, 2).text == '200.00%'
    assert table.cell(5, 2).text == '150.00%'
    assert table.cell(3, 5).text == '10.00%'


def test_financial_ratio_with_zero_denominator_requires_review():
    from jb_docgen.master_builder import _fill_financials
    from jb_kb.models import FinancialYear

    doc = Document()
    table = doc.add_table(rows=2, cols=3)
    for cell, text in zip(table.rows[0].cells, ['年份', '财务指标', 'XX年']):
        cell.text = text
    table.cell(1, 1).text = '资产负债率'
    profile = CompanyProfile(name='测试', financials=[FinancialYear(
        year='2025', asset_wan=0, liability_wan=0, liability_ratio='99%')])
    _fill_financials(doc, GenContext(trm=TRM(), pkg=PackageTRM(), profile=profile))
    assert '待补充' in table.cell(1, 2).text


def test_missing_boilerplate_does_not_create_gap_when_draft_already_covers_topic():
    from jb_docgen.master_builder import _insert_boilerplates

    doc = Document()
    doc.add_paragraph('5.履约能力及质量保证措施')
    ctx = GenContext(trm=TRM(), pkg=PackageTRM(), profile=CompanyProfile(name='测试'),
                     drafts=[SimpleNamespace(title='质量保证体系', text='拟组织交付物复核。')])
    _insert_boilerplates(doc, ctx)
    assert len(doc.paragraphs) == 1


def test_wide_table_fits_page_without_losing_merged_cells(tmp_path):
    from jb_docgen.layout import fit_tables

    doc = Document()
    doc.sections[0].left_margin = doc.sections[0].right_margin = Cm(3.17)
    table = doc.add_table(rows=2, cols=3)
    for col in table.columns:
        col.width = Cm(8)
    table.cell(0, 0).merge(table.cell(0, 1)).text = '合并表头'
    table.cell(1, 2).text = '有来源的数据'
    from docx.oxml import OxmlElement
    table._tbl.addnext(OxmlElement('w:customXml'))
    path = tmp_path / 'wide.docx'
    doc.save(path)
    assert fit_tables(str(path)) == 1
    assert fit_tables(str(path)) == 0
    result = Document(path)
    table = result.tables[0]
    section = result.sections[0]
    assert sum(col.width for col in table.columns) <= (
        section.page_width - section.left_margin - section.right_margin)
    assert table.cell(0, 0)._tc is table.cell(0, 1)._tc
    assert table.cell(1, 2).text == '有来源的数据'


def test_resume_uses_dated_facts_and_project_rows_without_assuming_relevant_experience():
    from jb_docgen.master_builder import _fill_personnel
    from jb_kb.models import Person, PersonProject

    doc = Document()
    summary = doc.add_table(rows=2, cols=5)
    for cell, text in zip(summary.rows[0].cells, ['层级', '职务', '姓名', '职称', '专业']):
        cell.text = text
    doc.add_paragraph('主要人员简历表')
    resume = doc.add_table(rows=6, cols=6)
    for row, values in zip(resume.rows, [
        ['层级', '', '', '', '', ''], ['姓名', '', '性别', '', '年龄', ''],
        ['学历', '', '参加工作时间', '', '工作年限', ''],
        ['主要资历、经验及承担过的项目', '', '', '', '', ''],
        ['项目名称', '建设规模', '项目起止时间', '担负的技术职务', '获奖情况', ''],
        ['', '', '', '', '', ''],
    ]):
        for cell, text in zip(row.cells, values):
            cell.text = text
    person = Person(id='one', name='测试人员', education='本科', gender='女', age=30,
                    age_as_of='2025-10-30', first_employment='2016年', working_years=10,
                    working_years_as_of='2026-10-30', project_experiences=[
                        PersonProject(project='服务甲', scale='10万元', period='2024年至2025年',
                                      role='技术支持', awards='/'),
                        PersonProject(project='服务乙', scale='20万元', period='2025年至2026年',
                                      role='实施人员', awards='/')])
    trm = TRM()
    trm.key_terms.bid_deadline = '2026-10-30 09:00'
    profile = CompanyProfile(name='测试企业', personnel=[person], bid_context={
        'reference_assignments': {'one': {'role': '项目主管', 'tier': '项目负责人'}}})
    _fill_personnel(doc, GenContext(trm=trm, pkg=PackageTRM(), profile=profile))
    result = doc.tables[1]
    assert result.cell(1, 3).text == '女'
    assert '待补充' in result.cell(1, 5).text  # 不能沿用上一年的年龄
    assert result.cell(2, 5).text == '10年'
    assert result.cell(5, 0).text == '服务甲'
    assert result.cell(6, 0).text == '服务乙'
    assert profile.personnel[0].relevant_experience_years is None
    assert summary.cell(1, 0).text == '项目负责人'
    assert summary.cell(1, 1).text == '项目主管'


def test_composition_drops_embedded_template_fonts_but_preserves_text(tmp_path):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from lxml import etree

    doc = Document()
    doc.add_paragraph('新生成的中文正文')
    font_table = doc.part.part_related_by(RT.FONT_TABLE)
    font = Part(PackURI('/word/fonts/subset.odttf'),
                'application/vnd.openxmlformats-officedocument.obfuscatedFont',
                b'template font subset', doc.part.package)
    rid = font_table.relate_to(font, RT.FONT)
    root = etree.fromstring(font_table.blob)
    family = OxmlElement('w:font')
    family.set(qn('w:name'), 'SimSun')
    embedded = OxmlElement('w:embedRegular')
    embedded.set(qn('r:id'), rid)
    family.append(embedded)
    root.append(family)
    font_table._blob = etree.tostring(root)
    M.prepare_composition(doc)
    path = tmp_path / 'composed.docx'
    doc.save(path)
    from zipfile import ZipFile
    with ZipFile(path) as archive:
        assert 'word/fonts/subset.odttf' not in archive.namelist()
        assert b'embedRegular' not in archive.read('word/fontTable.xml')
    assert Document(path).paragraphs[0].text == '新生成的中文正文'
    assert all(f'Heading {n}' in doc.styles for n in range(1, 5))


def test_authority_attachments_are_not_added_when_procurement_explicitly_waives_them(tmp_path):
    from jb_docgen.preparation_document import append_authorization_document

    doc = Document()
    doc.add_paragraph('法定代表人授权委托书（本项目无需提供）')
    path = tmp_path / 'waived.docx'
    doc.save(path)
    profile = CompanyProfile(name='测试', bid_context={
        'authorization': {'name': '授权代表', 'attachments': []}})
    append_authorization_document(path, GenContext(trm=TRM(), pkg=PackageTRM(), profile=profile))
    assert len(Document(path).paragraphs) == 1


def test_picture_occurrences_keep_distinct_crops_rotation_and_valid_relationships(tmp_path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from jb_docgen.evidence import insert_scans

    image = tmp_path / 'proof.png'
    Image.new('RGB', (100, 200), 'white').save(image)
    source = Document()
    shape = source.add_paragraph().add_run().add_picture(str(image), width=Cm(5))
    picture = shape._inline.graphic.graphicData.pic
    crop = OxmlElement('a:srcRect')
    crop.set('l', '10000')
    picture.blipFill.append(crop)
    picture.spPr.xfrm.set('rot', '10800000')
    first = shape._inline.xml
    crop.set('l', '30000')
    second = shape._inline.xml
    target = Document()
    target.sections[0].page_width = Cm(8)
    target.sections[0].left_margin = target.sections[0].right_margin = Cm(2)
    anchor = target.add_paragraph('证明材料')
    ctx = GenContext(trm=TRM(), pkg=PackageTRM(), profile=CompanyProfile(name='测试'),
                     attachment_paths={'one': str(image), 'two': str(image)},
                     attachment_layouts={'one': first, 'two': second})
    insert_scans(ctx, target, anchor._p, ['one', 'two'], '两个裁切视图')
    assert len(target.inline_shapes) == 2
    assert [s._inline.xpath('.//a:srcRect')[0].get('l') for s in target.inline_shapes] == ['10000', '30000']
    assert all(s._inline.xpath('.//a:xfrm')[0].get('rot') == '10800000' for s in target.inline_shapes)
    assert all(s.width <= Cm(4) for s in target.inline_shapes)
    ids = target.element.xpath('.//wp:docPr/@id')
    assert len(ids) == len(set(ids))
    for blip in target.element.xpath('.//a:blip'):
        assert target.part.related_parts[blip.get(qn('r:embed'))].blob == image.read_bytes()


def test_optional_sections_require_explicit_decision_and_preserve_following_heading():
    from jb_docgen.optional_sections import apply_optional_sections

    doc = Document()
    doc.add_paragraph('10.联合体协议书（格式）')
    doc.add_paragraph('1.内部条款，不是下一个章节')
    doc.add_paragraph('签章位置与空白模板')
    doc.add_paragraph('11.财务信息审核结果凭证单')
    doc.add_paragraph('该段不得凭缺少附件自行删除')
    ctx = GenContext(trm=TRM(), pkg=PackageTRM(allow_consortium=False),
                     profile=CompanyProfile(name='测试'))
    apply_optional_sections(doc, ctx)
    text = '\n'.join(p.text for p in doc.paragraphs)
    assert '不适用（本包不接受联合体响应）' in text
    assert '签章位置' not in text and '内部条款' not in text
    assert '11.财务信息审核结果凭证单' in text
    assert '该段不得凭缺少附件自行删除' in text


def test_evidence_placeholder_blank_lines_are_trimmed_but_signature_space_is_preserved(tmp_path):
    from docx.oxml import OxmlElement
    from jb_docgen.layout import fit_tables

    doc = Document()
    doc.add_paragraph('9.企业名称变更（如有）')
    for _ in range(12):
        doc.add_paragraph()
    doc.paragraphs[-1]._p.get_or_add_pPr().append(OxmlElement('w:sectPr'))
    doc.add_paragraph('授权人签字（盖章）')
    for _ in range(12):
        doc.add_paragraph()
    doc.paragraphs[-1]._p.get_or_add_pPr().append(OxmlElement('w:sectPr'))
    path = tmp_path / 'spacers.docx'
    doc.save(path)
    fit_tables(str(path))
    result = Document(path)
    split = next(i for i, p in enumerate(result.paragraphs) if p.text == '授权人签字（盖章）')
    assert split == 4  # 条件标题后保留两空行与节属性载体
    assert len(result.paragraphs[split + 1:]) == 12
    assert len(result.element.xpath('.//w:pPr/w:sectPr')) == 2


def test_business_profile_proofs_are_composed_without_reference_mode(tmp_path):
    from jb_docgen.master_builder import build_commercial
    from jb_kb.models import Shareholder

    image = tmp_path / 'proof.png'
    Image.new('RGB', (100, 100), 'white').save(image)
    master = Document()
    master.add_paragraph('第六章 投标文件格式')
    master.add_paragraph('商务文件')
    table = master.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(1, 0).text = '单位名称', '注册地址'
    owners = master.add_table(rows=2, cols=3)
    for cell, text in zip(owners.rows[0].cells, ['股东或上级管理单位名称', '出资金额', '出资比例']):
        cell.text = text
    master.add_paragraph('基本账户证明（扫描件）')
    master.add_paragraph('（此处粘帖银行通过账户管理系统打印的《基本存款账户信息》扫描件')
    master.add_paragraph('2.其他证明要求')
    master.add_paragraph('必须提供真实的基本存款账户信息')
    master.add_paragraph('9.企业名称变更（如有）')
    master.add_paragraph('技术文件')
    path = tmp_path / 'master.docx'
    master.save(path)
    profile = CompanyProfile(name='测试企业', address='测试地址',
                             shareholders=[Shareholder(name='测试股东', amount_wan=100, ratio=100)],
                             shareholder_attachments=['share'], name_change_attachments=['rename'])
    profile.bid_context['commercial_evidence'] = {'bank': ['bank']}
    ctx = GenContext(trm=TRM(), pkg=PackageTRM(), profile=profile,
                     attachment_paths={'share': str(image), 'rename': str(image), 'bank': str(image)})
    output = tmp_path / 'business.docx'
    assert build_commercial(ctx, str(path), str(output))
    result = Document(output)
    assert len(result.inline_shapes) == 3
    text = '\n'.join(p.text for p in result.paragraphs)
    assert '此处粘帖' not in text
    assert '必须提供真实的基本存款账户信息' in text
    assert result.tables[1].cell(1, 0).text == '测试股东'
    assert 'reference_source' not in profile.bid_context


def test_filled_cells_do_not_keep_following_evidence_on_same_page():
    from jb_docgen.master import set_cell_text

    doc = Document()
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    cell.paragraphs[0].paragraph_format.keep_with_next = True
    set_cell_text(cell, '已填写的业绩数据')
    assert cell.paragraphs[0].paragraph_format.keep_with_next is False


def test_long_service_response_is_preserved_after_table_instead_of_narrow_column():
    from jb_docgen.spec_response import respond_service_table, service_table_rows

    doc = Document()
    table = doc.add_table(rows=2, cols=4)
    for cell, text in zip(table.rows[0].cells, ['序号', '成果名称', '成果说明', '应答人应答']):
        cell.text = text
    for cell, text in zip(table.rows[1].cells, ['1', '运营报告', '按月编制', '']):
        cell.text = text
    key = service_table_rows(table)[0][1]
    detailed = '按月收集平台记录，核对数据口径并形成异常闭环清单。' * 12
    following = respond_service_table(table, {key: detailed})
    assert table.cell(1, 2).text == '按月编制'
    assert table.cell(1, 3).text == '具体响应见表后第1项说明。'
    assert following == ['表中第1项响应：' + detailed]


def test_reference_team_review_uses_existing_other_section(tmp_path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from jb_docgen.preparation_document import append_team_document

    doc = Document()
    heading = doc.add_paragraph('10.其他')
    section = OxmlElement('w:sectPr')
    kind = OxmlElement('w:type')
    kind.set(qn('w:val'), 'nextPage')
    section.append(kind)
    heading._p.get_or_add_pPr().append(section)
    doc.add_paragraph('后续保留内容')
    path = tmp_path / 'review.docx'
    doc.save(path)
    profile = CompanyProfile(name='测试', bid_context={'reference_source': '本地标准件'})
    append_team_document(str(path), profile)
    result = Document(path)
    paragraphs = [p.text for p in result.paragraphs]
    assert paragraphs[1] == '本次人员安排核对'
    assert paragraphs[-1] == '后续保留内容'
    assert not result.paragraphs[0]._p.xpath('.//w:sectPr')
    assert result.paragraphs[3]._p.xpath('.//w:sectPr/w:type')[0].get(qn('w:val')) == 'continuous'
