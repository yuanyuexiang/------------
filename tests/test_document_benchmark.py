from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm
from jb_docgen.benchmark import compare, inspect
from jb_docgen.master_builder import _commercial_headings
from PIL import Image


def test_filled_cells_do_not_snap_multiple_line_spacing_to_page_grid():
    from jb_docgen.master import set_cell_text

    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = '原始要求'
    cell = table.cell(1, 1)
    cell.paragraphs[0].paragraph_format.line_spacing = 1.5
    cell.paragraphs[0].add_run('空白响应').bold = True
    before = table.cell(0, 0)._tc.xml
    set_cell_text(cell, '具体响应见表后第1项说明。')
    paragraph = cell.paragraphs[0]
    assert paragraph._p.pPr.find(qn('w:snapToGrid')).get(qn('w:val')) == '0'
    assert paragraph.paragraph_format.line_spacing == 1.15
    assert paragraph.runs[0].bold
    assert table.cell(0, 0)._tc.xml == before


def test_commercial_long_headings_and_subsections_without_promoting_clauses():
    doc = Document()
    for title in [
        '4.企业法人营业执照（或事业单位法人证书或其他组织登记证书）副本（扫描件）',
        '6.1符合第一章响应供应商资格要求的证明文件',
        '6.2查询报告及截图',
        '9.企业名称变更（如有，须提供证明材料）',
        '1.投保人在响应截止时间后撤销其响应文件；',
        '2.响应供应商应以所响应的包为单位计算响应保证金。',
    ]:
        doc.add_paragraph(title)
    _commercial_headings(doc, [])
    assert [p.style.name for p in doc.paragraphs] == [
        'Heading 2', 'Heading 3', 'Heading 3', 'Heading 2', 'Normal', 'Normal']


def test_comparison_tracks_repeated_image_crops_and_missing_sections(tmp_path):
    image = tmp_path / 'proof.png'
    Image.new('RGB', (100, 100), 'white').save(image)
    paths = []
    for name, count in [('reference', 2), ('candidate', 1)]:
        doc = Document()
        if count == 2:
            doc.add_heading('9.企业名称变更', level=2)
        for index in range(count):
            shape = doc.add_picture(str(image), width=Cm(3))
            if index:
                crop = OxmlElement('a:srcRect')
                crop.set('l', '10000')
                shape._inline.xpath('.//pic:blipFill')[0].append(crop)
        path = tmp_path / f'{name}.docx'
        doc.save(path)
        paths.append(str(path))
    report = compare(*paths)
    assert report['missing_image_views'] == 1
    assert report['additional_image_views'] == 0
    assert report['missing_reference_headings'] == ['9.企业名称变更']
    assert report['candidate']['image_occurrences'] == 1
    candidate = Document(paths[1])
    crop = OxmlElement('a:srcRect')
    crop.set('l', '20000')
    candidate.inline_shapes[0]._inline.xpath('.//pic:blipFill')[0].append(crop)
    candidate.save(paths[1])
    changed_view = compare(*paths)
    assert changed_view['missing_image_views'] == 2
    assert changed_view['additional_image_views'] == 1


def test_image_bounds_use_own_section_including_effect_extent(tmp_path):
    image = tmp_path / 'proof.png'
    Image.new('RGB', (100, 100), 'white').save(image)
    doc = Document()
    doc.sections[0].left_margin = doc.sections[0].right_margin = Cm(6)
    shape = doc.add_picture(str(image), width=Cm(12))
    doc.add_section(WD_SECTION_START.NEW_PAGE)
    doc.sections[-1].left_margin = doc.sections[-1].right_margin = Cm(1)
    effects = OxmlElement('wp:effectExtent')
    effects.set('r', '10000')
    shape._inline.append(effects)
    path = tmp_path / 'sections.docx'
    doc.save(path)
    assert inspect(str(path))['overwide_or_overheight_images'] == [1]
