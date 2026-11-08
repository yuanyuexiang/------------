"""本包采购要求与选材、文件位置的可追溯关联；关联记录不代替合规审查。"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from jb_kb import attachments
from jb_parser import package_files
from jb_parser.trm import PackageTRM
from jb_store import projects as pm

from . import preparation, workflow

GROUPS = {'terms': '关键投标要求', 'qualification': '资格与证明', 'specification': '技术与服务要求',
          'submission': '提交要求', 'rejection': '否决情形', 'format': '规定格式'}


def catalog(p, index):
    from jb_parser.trm import TRM
    trm = TRM.model_validate(p.trm_confirmed or p.trm or {})
    if not 0 <= index < len(trm.packages):
        raise ValueError('采购包不存在')
    pkg = trm.packages[index]
    rows = []

    def add(group, title, text, source, kinds=(), document='main'):
        if not text.strip():
            return
        ident = workflow.fingerprint([group, source, text])[:24]
        rows.append({'id': ident, 'group': group, 'title': title, 'text': text,
                     'source': source, 'document': document, 'evidence_kinds': list(kinds)})

    def term(clause, value):
        return next((r.content for r in trm.prenotice if r.clause_no == clause),
                    f'{value}（提取值，请核对原件）' if value is not None else '')

    for title, text, source in (
        ('投标有效期', term(trm.key_terms.validity_clause, trm.key_terms.validity_days), '关键条款 · 投标有效期'),
        ('保证金', term(trm.key_terms.deposit_clause, trm.key_terms.deposit_mode), '关键条款 · 保证金'),
        ('签章要求', term(trm.key_terms.sign_clause, trm.key_terms.sign_whole_doc), '关键条款 · 签章'),
        ('招标范围', pkg.scope, '本包需求 · 范围'),
        ('服务期限', pkg.duration_text, '本包需求 · 期限'),
    ):
        add('terms', title, text or '', source)
    for i, clause in enumerate(trm.prenotice):
        add('terms', clause.name or clause.clause_no, clause.content,
            f'前附表 {clause.clause_no} · 条目{i + 1}')
    for i, q in enumerate(pkg.qualification):
        for title, text, kinds in (
            ('业绩要求', q.performance_req, ('performances',)),
            ('检测报告', q.test_report_req, ('test_reports', 'certificates')),
            *((name, value, ('personnel',) if '人员' in name else ('certificates',))
              for name, value in q.other_reqs.items()),
        ):
            add('qualification', title, text, f'本包资格表 · 条目{i + 1} · {title}', kinds, '')
    for i, spec in enumerate(pkg.spec_docs):
        for j, row in enumerate(spec.param_rows):
            add('specification', ('★ ' if row.star else '') + (row.name or f'第{row.row}行'),
                f'{row.name}：{row.required} {row.unit}'.strip(),
                f'{spec.source} · 参数行{row.row} · 条目{j + 1}', ('products', 'test_reports'), f'spec:{i}')
    sources, _ = preparation.requirements(p, index)
    for key, text in sources.items():
        if key.startswith('req-spec-'):
            spec_index = int(key.split('-')[2])
            position = int(key.split('-')[3]) + 1
            source = pkg.spec_docs[spec_index].source if spec_index < len(pkg.spec_docs) else '技术规范书'
            add('specification', f'技术规范正文 · 条目{position}', text, f'{source} · 正文位置{position}',
                ('personnel', 'performances', 'products'), f'spec:{spec_index}')
    for i, row in enumerate(trm.submission_table):
        add('submission', row.item, f'{row.section} · {row.item}\n提交渠道：{ "、".join(row.channels)}\n位置：{row.port}',
            f'提交方式表 · 条目{i + 1}')
    for i, rule in enumerate(trm.rejection_rules):
        add('rejection', rule.aspect or rule.category, rule.text, f'否决情形表 · 条目{i + 1}')
    for i, block in enumerate(trm.format_blocks):
        add('format', block.title, '\n'.join(block.paragraphs), f'文件格式 · 条目{i + 1}')
    return rows


def evidence(s, p, index, cp):
    chosen = workflow.selected_profile(p, index, cp)
    available = {a.id: a for a in attachments.list_attachments(s, cp.name)}
    records = {}
    for kind in ('certificates', 'personnel', 'performances', 'financials', 'products', 'test_reports'):
        for item in getattr(chosen, kind):
            data = item.model_dump()
            key = f'{kind}:{item.id}'
            title = next((str(data[k]) for k in ('name', 'project', 'year', 'model') if data.get(k)), item.id)
            ids = [aid for aid in data.get('attachments', []) if aid in available]
            records[key] = {'id': key, 'kind': kind, 'title': title,
                            'attachments': [{'id': aid, 'filename': available[aid].filename} for aid in ids],
                            '_basis': {'record': data, 'attachments': {aid: available[aid].sha256 for aid in ids}}}
    return records


@lru_cache(maxsize=24)
def document_blocks(path, mtime_ns, size):
    try:
        doc = Document(path)
    except Exception as exc:
        raise ValueError('文档内容无法读取，请下载原件核对或重新生成') from exc
    blocks = []
    heading = ''
    for i, element in enumerate(doc.element.body):
        ident = f'block-{i}'
        if element.tag == qn('w:p'):
            para = Paragraph(element, doc._body)
            text = para.text.strip()
            if para.style.name.startswith('Heading ') and text:
                heading = text
            images = len(element.xpath('.//w:drawing | .//w:pict'))
            if text or images:
                blocks.append({'id': ident, 'kind': 'paragraph', 'text': text, 'heading': heading,
                               'images': images, 'rows': []})
        elif element.tag == qn('w:tbl'):
            table = Table(element, doc._body)
            rows = []
            for row in table.rows:
                seen, values = set(), []
                for cell in row.cells:
                    if cell._tc not in seen:
                        values.append(cell.text)
                        seen.add(cell._tc)
                rows.append(values)
            blocks.append({'id': ident, 'kind': 'table', 'heading': heading, 'rows': rows,
                           'text': '\n'.join(' | '.join(r) for r in rows),
                           'images': len(element.xpath('.//w:drawing | .//w:pict'))})
    return blocks


def read_blocks(path):
    stat = Path(path).stat()
    return document_blocks(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=12)
def _source(zip_path, mtime, size, package_json, source):
    pkg = PackageTRM.model_validate_json(package_json)
    with tempfile.TemporaryDirectory(prefix='jb-source-') as folder:
        files = package_files(zip_path, pkg, workdir=folder)
        if source == 'main':
            path = files.main_doc
        elif source.startswith('spec:'):
            try:
                index = int(source.split(':')[1])
                if not 0 <= index < len(pkg.spec_docs):
                    raise ValueError('规范书不存在')
                spec = pkg.spec_docs[index]
                path = files.spec_docs.get(spec.spec_id or spec.source)
            except (ValueError, IndexError) as exc:
                raise ValueError('规范书不存在') from exc
        else:
            raise ValueError('不支持的原件类型')
        if not path:
            raise ValueError('本包原件缺失或无法唯一定位，请重新核对采购文件')
        return {'filename': Path(path).name, 'blocks': read_blocks(path)}


def source_document(p, index, source):
    from jb_parser.trm import TRM
    trm = TRM.model_validate(p.trm_confirmed or p.trm or {})
    if not 0 <= index < len(trm.packages):
        raise ValueError('采购包不存在')
    stat = Path(p.zip_path).stat()
    return _source(p.zip_path, stat.st_mtime_ns, stat.st_size,
                   trm.packages[index].model_dump_json(), source)


def output_document(p, index, company, filename, out_dir):
    artifact = workflow.latest(p, index)
    if (not artifact or artifact['profile'] != company or filename not in artifact['files']
            or Path(filename).name != filename):
        raise ValueError('文件不属于本包、本企业的当前生成版本')
    path = Path(out_dir) / filename
    if not path.is_file() or workflow.file_hash(path) != artifact['files'][filename]:
        raise ValueError('文件缺失或已修改，请重新生成后查看')
    return {'filename': filename, 'generation_id': artifact['id'], 'blocks': read_blocks(path)}


def _basis(p, index, row, records, link, artifact):
    from jb_parser.trm import TRM
    pkg = TRM.model_validate(p.trm_confirmed or p.trm).packages[index]
    selected = {key: records[key]['_basis'] if key in records else None for key in link.get('evidence_ids', [])}
    response = link.get('response')
    response_file = (artifact or {}).get('files', {}).get((response or {}).get('filename'))
    return workflow.fingerprint({'requirement': row, 'evidence': selected,
        'package': [pkg.sub_no, pkg.sub_name, pkg.pkg_no, pkg.project_name], 'profile': link['profile'],
        'response': response, 'response_hash': response_file,
        'generation_id': (artifact or {}).get('id') if response else None,
        'facts': (p.results or {}).get('bid_facts', {}).get(workflow.material_key(index, link['profile']), {})
        if any(key.startswith('personnel:') for key in selected) else None})


def state(s, p, index, cp, out_dir):
    rows = catalog(p, index)
    records = evidence(s, p, index, cp)
    links = (p.results or {}).get('requirement_links', {}).get(workflow.material_key(index, cp.name), {})
    artifact = workflow.latest(p, index)
    if artifact and artifact['profile'] != cp.name:
        artifact = None
    flow = workflow.workflow_state(s, p, index, cp.name, out_dir)
    generation_stale = flow['stale'] or any('文件缺失或已被修改' in reason for reason in flow['blockers'])
    for row in rows:
        link = links.get(row['id'])
        stale = bool(link and (link.get('basis') != _basis(p, index, row, records, link, artifact)
                              or link.get('response') and generation_stale))
        row['link_revision'] = workflow.fingerprint(link)
        row['link'] = {k: v for k, v in (link or {}).items() if k not in ('basis', 'profile')}
        row['status'] = 'stale' if stale else 'confirmed' if link and link.get('confirmed') else 'linked' if link else 'unlinked'
    return {'revision': workflow.inputs(s, p, cp.name)[2], 'requirements': rows,
            'evidence': [{k: v for k, v in item.items() if k != '_basis'} for item in records.values()],
            'files': list(artifact['files']) if artifact else [], 'generation_id': artifact['id'] if artifact else None,
            'generation_stale': generation_stale, 'review': flow['review'] if artifact else None,
            'review_stale': bool(flow['review'] and (generation_stale or flow['review'].get('rules_hash') != workflow.rules_hash(s))),
            'blockers': flow['blockers'], 'groups': GROUPS}


def save(s, p, index, cp, requirement_id, payload, actor, out_dir):
    if payload.get('revision') != workflow.inputs(s, p, cp.name)[2]:
        raise ValueError('采购要求或投标资料已变化，请刷新后重新关联')
    row = next((r for r in catalog(p, index) if r['id'] == requirement_id), None)
    if row is None:
        raise ValueError('采购要求已变化或不属于当前包，请刷新')
    existing = (p.results or {}).get('requirement_links', {}).get(
        workflow.material_key(index, cp.name), {}).get(requirement_id)
    if payload.get('link_revision') != workflow.fingerprint(existing):
        raise ValueError('这条要求的关联已被更新，请刷新后重新核对')
    records = evidence(s, p, index, cp)
    ids = payload.get('evidence_ids', [])
    if not isinstance(ids, list) or any(not isinstance(key, str) or key not in records for key in ids):
        raise ValueError('只能关联本包当前选用的已审核材料')
    response = payload.get('response')
    if response is not None and (not isinstance(response, dict) or any(
            not isinstance(response.get(key), str) for key in ('filename', 'generation_id', 'block_id'))):
        raise ValueError('响应位置格式不正确')
    artifact = workflow.latest(p, index)
    if response:
        if not isinstance(response, dict) or response.get('generation_id') != (artifact or {}).get('id'):
            raise ValueError('响应位置属于旧版本，请重新选择')
        preview = output_document(p, index, cp.name, response.get('filename', ''), out_dir)
        if response.get('block_id') not in {block['id'] for block in preview['blocks']}:
            raise ValueError('响应段落或表格不存在')
        response = {key: response[key] for key in ('filename', 'generation_id', 'block_id')}
        if payload.get('confirmed') and workflow.source_blockers(s, p, artifact, out_dir, cp.name):
            raise ValueError('本版本输入或确认状态已变化，请更新标书后再核对响应位置')
    note = payload.get('note', '')
    if not isinstance(note, str) or len(note) > 5000 or not isinstance(payload.get('confirmed', False), bool):
        raise ValueError('核对说明格式不正确')
    if payload.get('confirmed') and not (ids or response or note.strip()):
        raise ValueError('请关联证据、响应位置或填写本条核对依据')
    link = {'profile': cp.name, 'evidence_ids': list(dict.fromkeys(ids)), 'response': response,
            'note': note, 'confirmed': payload.get('confirmed', False), 'actor': actor,
            'updated_at': datetime.now(timezone.utc).isoformat()}
    link['basis'] = _basis(p, index, row, records, link, artifact)
    all_links = dict((p.results or {}).get('requirement_links', {}))
    key = workflow.material_key(index, cp.name)
    all_links[key] = {**all_links.get(key, {}), row['id']: link}
    pm.set_result(p, 'requirement_links', all_links)
    pm.log_event(s, p.id, 'requirement_linked', '关联采购要求：' + row['title'],
                 {'requirement_id': row['id'], 'pkg_index': index, 'profile': cp.name})
