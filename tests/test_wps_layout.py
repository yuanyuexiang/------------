"""WPS 排版回归：跨 run 保真填空、可更新目录、简明团队表。"""
import re

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from jb_docgen.master import fill_paragraph
from jb_docgen.navigation import add_navigation
from jb_docgen.preparation_document import append_team_document
from jb_kb.models import CompanyProfile, Person


def test_cross_run_fill_preserves_unmodified_character_formatting():
    doc = Document()
    p = doc.add_paragraph()
    label = p.add_run('单位：')
    label.bold = True
    start = p.add_run('{{公')
    start.font.name = '仿宋'
    start.underline = True
    end = p.add_run('司}}')
    end.italic = True
    tail = p.add_run('（盖章）')
    tail.font.size = Pt(14)
    properties = [r._r.rPr.xml for r in p.runs]
    assert fill_paragraph(p, [(re.compile(r'\{\{公司\}\}'), '测试企业')])
    assert p.text == '单位：测试企业（盖章）'
    assert [r.text for r in p.runs] == ['单位：', '测试企业', '', '（盖章）']
    assert [r._r.rPr.xml for r in p.runs] == properties


def test_multiple_and_zero_width_replacements_retain_label_and_tail():
    p = Document().add_paragraph()
    p.add_run('甲XX乙XX').bold = True
    p.add_run('单位：').italic = True
    assert fill_paragraph(p, [(re.compile('XX'), lambda m: '替换值'),
                              (re.compile(r'(?<=单位：)$'), '企业')])
    assert p.text == '甲替换值乙替换值单位：企业'
    assert p.runs[0].bold and p.runs[1].italic


def test_fields_and_page_breaks_are_not_destroyed_by_fill():
    p = Document().add_paragraph('单位：XX')
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), ' PAGE ')
    p._p.append(field)
    before = p._p.xml
    assert not fill_paragraph(p, [(re.compile('XX'), '企业')])
    assert p._p.xml == before


def test_native_toc_wraps_cache_and_preserves_source_toc(tmp_path):
    d = Document()
    d.add_paragraph('投标文件')
    d.add_page_break()
    d.add_heading('人员安排', level=1)
    path = tmp_path / 'toc.docx'
    d.save(path)
    assert add_navigation(str(path))
    d = Document(path)
    codes = d.element.xpath('.//w:instrText/text()')
    assert any('TOC ' in code and '\\o "1-3"' in code for code in codes)
    assert d.element.xpath('.//w:fldChar[@w:fldCharType="separate"]')
    assert len(d.element.xpath('.//w:hyperlink')) == 1
    before = d.element.xml
    assert not add_navigation(str(path))
    assert Document(path).element.xml == before
    # 模拟系统旧版目录：仅移除外层 TOC 域，保留其原有链接和页码缓存。
    for node in list(d.element.xpath('.//w:fldChar | .//w:instrText')):
        node.getparent().remove(node)
    d.save(path)
    assert add_navigation(str(path))
    assert len(Document(path).element.xpath('.//w:instrText[contains(.,"TOC ")]')) == 1


def test_team_table_does_not_publish_long_internal_sources(tmp_path):
    source = '内部资料/历史合同路径及人工核对说明；' * 100
    cp = CompanyProfile(name='企业', personnel=[Person(id='p1', name='张某', source=source,
        experience_source=source)], bid_context={'team': {'members': [
            {'person_id': 'p1', 'role': '项目负责人', 'available': True}], 'arrival_commitment': False}})
    path = tmp_path / 'team.docx'
    Document().save(path)
    append_team_document(str(path), cp)
    d = Document(path)
    table = d.tables[0]
    assert table.cell(1, 3).text == '见人员简历及证明材料'
    assert not any('历史合同路径' in c.text for r in table.rows for c in r.cells)
    assert cp.personnel[0].source == source
    assert table._tbl.xpath('./w:tr[1]/w:trPr/w:tblHeader')
    assert all(r._tr.xpath('./w:trPr/w:cantSplit') for r in table.rows)
    assert '【待补充：拟投入本包人员名单及到岗承诺】' in '\n'.join(p.text for p in d.paragraphs)


def test_generated_copy_is_editable_without_modifying_protected_master(tmp_path):
    from jb_docgen.master import prepare_composition
    path = tmp_path / 'protected-master.docx'
    d = Document()
    protection = OxmlElement('w:documentProtection')
    protection.set(qn('w:edit'), 'comments')
    protection.set(qn('w:enforcement'), '1')
    d.settings.element.append(protection)
    d.save(path)
    source_bytes = path.read_bytes()
    output = Document(path)
    prepare_composition(output)
    assert not output.settings.element.xpath('./w:documentProtection')
    assert path.read_bytes() == source_bytes
    assert Document(path).settings.element.xpath('./w:documentProtection')


def test_font_audit_reports_exact_missing_fonts_without_substitution(tmp_path):
    from jb_docgen.font_audit import report
    d = Document()
    r = d.add_paragraph().add_run('采购正文')
    r.font.name = '宋体'
    r._r.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), '宋体')
    p = tmp_path / 'fonts.docx'
    d.save(p)
    missing = report(str(p), ['Noto Serif CJK SC'])
    assert '宋体' in missing['missing_declared_fonts']
    matched = report(str(p), ['SimSun'])
    assert '宋体' not in matched['missing_declared_fonts']
    assert missing['font_inventory_hash'] != matched['font_inventory_hash']
    assert Document(p).paragraphs[0].runs[0].font.name == '宋体'


def test_empty_terminal_section_is_joined_without_removing_signature_space(tmp_path):
    from docx.enum.section import WD_SECTION_START
    from jb_docgen.layout import fit_tables
    d = Document()
    d.add_paragraph('投标人盖章及印模位置')
    for _ in range(8):
        d.add_paragraph('')
    d.add_section(WD_SECTION_START.NEW_PAGE)
    d.add_paragraph('')
    p = tmp_path / 'signature.docx'
    d.save(p)
    fit_tables(str(p))
    result = Document(p)
    assert result.sections[-1].start_type == WD_SECTION_START.CONTINUOUS
    assert len(result.paragraphs) >= 9
    assert result.paragraphs[0].text == '投标人盖章及印模位置'
    # 真正有后续正文的分节不得合并。
    d = Document()
    d.add_paragraph('商务文件')
    d.add_section(WD_SECTION_START.NEW_PAGE)
    d.add_paragraph('有正文的下一节')
    d.save(p)
    fit_tables(str(p))
    assert Document(p).sections[-1].start_type == WD_SECTION_START.NEW_PAGE


def test_intentional_odd_page_terminal_section_is_preserved(tmp_path):
    from docx.enum.section import WD_SECTION_START
    from jb_docgen.layout import fit_tables
    d = Document()
    d.add_paragraph('正文')
    d.add_section(WD_SECTION_START.ODD_PAGE)
    p = tmp_path / 'odd-page.docx'
    d.save(p)
    fit_tables(str(p))
    assert Document(p).sections[-1].start_type == WD_SECTION_START.ODD_PAGE
