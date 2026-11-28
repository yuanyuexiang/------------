"""Import the styles, lists and related parts used by a procurement specification."""
from copy import deepcopy
from pathlib import PurePosixPath

from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.parts.numbering import NumberingPart
from lxml import etree

_REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_STYLE_REFS = {qn(f'w:{name}') for name in ('pStyle', 'rStyle', 'tblStyle')}


class SourceContent:
    def __init__(self, source, target):
        self.source = source.part
        self.target = target.part
        self.styles = {}
        self.numberings = {}
        self.abstracts = {}
        self.parts = {}
        self.part_names = {part.partname for part in self.target.package.parts}
        self.part_index = 0
        self.shape_id = max([0, *map(int, target.element.xpath('.//wp:docPr/@id'))])

    def copy(self, element):
        node = deepcopy(element)
        # The specification is inserted as a chapter in the bid's page sequence.
        # Isolated source section breaks must not replace the bid's page settings.
        for section in list(node.iter(qn('w:sectPr'))):
            section.getparent().remove(section)
        for shape in node.iter(qn('wp:docPr')):
            self.shape_id += 1
            shape.set('id', str(self.shape_id))
        self._rewrite_styles(node)
        self._rewrite_links(node, self.source, self.target)
        return node

    def _rewrite_styles(self, node):
        for ref in node.iter():
            value = ref.get(qn('w:val'))
            if ref.tag in _STYLE_REFS and value:
                ref.set(qn('w:val'), self._style(value))
            elif ref.tag == qn('w:numId') and value not in (None, '0'):
                ref.set(qn('w:val'), self._numbering(value))

    def _style(self, value):
        if value in self.styles:
            return self.styles[value]
        source = self.source.styles.element.get_by_id(value)
        target = self.target.styles.element
        existing = target.get_by_id(value)
        if source is None or (existing is not None and
                etree.tostring(existing, method='c14n', exclusive=True) ==
                etree.tostring(source, method='c14n', exclusive=True)
                and not source.xpath('./w:basedOn | ./w:link | .//w:numId')):
            self.styles[value] = value
            return value
        new_id = value
        suffix = 0
        while target.get_by_id(new_id) is not None:
            suffix += 1
            new_id = f'{value}_jb{suffix}'
        self.styles[value] = new_id
        style = deepcopy(source)
        style.set(qn('w:styleId'), new_id)
        style.attrib.pop(qn('w:default'), None)
        target.append(style)
        for ref in style.xpath('./w:basedOn | ./w:link | ./w:next'):
            if ref.get(qn('w:val')):
                ref.set(qn('w:val'), self._style(ref.get(qn('w:val'))))
        self._rewrite_styles(style)
        return new_id

    def _numbering(self, value):
        if value in self.numberings:
            return self.numberings[value]
        source = self.source.numbering_part
        if RT.NUMBERING not in {rel.reltype for rel in self.target.rels.values()}:
            target_part = NumberingPart(self._new_part_name('.xml'), CT.WML_NUMBERING,
                                        OxmlElement('w:numbering'), self.target.package)
            self.target.relate_to(target_part, RT.NUMBERING)
        target = self.target.numbering_part
        original = source.element.xpath(f'./w:num[@w:numId="{int(value)}"]')
        if not original:
            raise ValueError(f'规范书编号 {value} 缺少定义')
        number = deepcopy(original[0])
        new_id = str(max([0, *map(int, target.element.xpath('./w:num/@w:numId'))]) + 1)
        self.numberings[value] = new_id
        number.set(qn('w:numId'), new_id)
        target.element._insert_num(number)
        abstract_ref = number.find(qn('w:abstractNumId'))
        abstract_id = int(abstract_ref.get(qn('w:val')))
        if abstract_id not in self.abstracts:
            abstract = deepcopy(source.element.xpath(
                f'./w:abstractNum[@w:abstractNumId="{abstract_id}"]'
            )[0])
            new_abstract_id = str(max([-1, *map(int, target.element.xpath(
                './w:abstractNum/@w:abstractNumId'
            ))]) + 1)
            self.abstracts[abstract_id] = new_abstract_id
            abstract.set(qn('w:abstractNumId'), new_abstract_id)
            first_number = target.element.find(qn('w:num'))
            first_number.addprevious(abstract)
            if abstract.find('.//' + qn('w:lvlPicBulletId')) is not None:
                raise ValueError('规范书使用图片项目符号，请核对原件')
            for ref in abstract.iter(qn('w:numStyleLink'), qn('w:styleLink')):
                if ref.get(qn('w:val')):
                    ref.set(qn('w:val'), self._style(ref.get(qn('w:val'))))
            self._rewrite_styles(abstract)
        abstract_ref.set(qn('w:val'), self.abstracts[abstract_id])
        self._rewrite_styles(number)
        return new_id

    def _rewrite_links(self, element, source, target):
        for node in element.iter():
            for attr, rid in node.attrib.items():
                if attr.startswith(f'{{{_REL_NS}}}'):
                    rel = source.rels[rid]
                    child = rel.target_ref if rel.is_external else self._copy_part(rel.target_part)
                    node.set(attr, target.relate_to(child, rel.reltype, rel.is_external))

    def _copy_part(self, source):
        if source not in self.parts:
            suffix = PurePosixPath(str(source.partname)).suffix
            copy = Part(self._new_part_name(suffix), source.content_type, source.blob,
                        self.target.package)
            self.parts[source] = copy
            for rid, rel in source.rels.items():
                child = rel.target_ref if rel.is_external else self._copy_part(rel.target_part)
                copy.load_rel(rel.reltype, child, rid, rel.is_external)
        return self.parts[source]

    def _new_part_name(self, extension):
        while True:
            self.part_index += 1
            name = PackURI(f'/word/jinbang-imported/part{self.part_index}{extension}')
            if name not in self.part_names:
                self.part_names.add(name)
                return name
