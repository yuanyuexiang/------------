"""采购要求关联：按包/企业隔离，证据来源、生成位置及修改失效。"""
from types import SimpleNamespace

import pytest
from docx import Document
from jb_docgen import traceability, workflow
from jb_kb.models import CompanyProfile, Performance
from jb_parser.trm import TRM, PackageTRM, QualificationItem, SpecDoc
from jb_store import Project, Task, session


@pytest.fixture()
def case(client):
    company = CompanyProfile(name='关联测试企业', performances=[
        Performance(id='proof', project='所选业绩', signed_date='2025-01-01'),
        Performance(id='unused', project='未选业绩', signed_date='2025-02-01')])
    client.put('/api/profiles/关联测试企业', json=company.model_dump())
    client.put('/api/profiles/其他企业', json={'name': '其他企业'})
    trm = TRM(batch_no='TRACE', packages=[PackageTRM(sub_no=sub, sub_name='服务', pkg_no='包1',
        qualification=[QualificationItem(performance_req='应提供相关服务合同')],
        spec_docs=[SpecDoc(spec_id='spec', source='规范.docx', n_paragraphs=30)]) for sub in ('A', 'B')]).model_dump()
    with session() as s:
        p = Project(filename='test.zip', zip_path='', status='confirmed', trm=trm, trm_confirmed=trm)
        s.add(p)
        s.flush()
        pid = p.id
        from jb_kb.repo import load_profile
        workflow.save_selection(p, 0, load_profile(s, company.name), {'performances': ['proof']})
    return client, pid


def get(case, index=0, company='关联测试企业'):
    client, pid = case
    response = client.get(f'/api/projects/{pid}/requirements', params={'profile': company, 'pkg_index': index})
    assert response.status_code == 200, response.text
    return response.json()


def save(case, state, **changes):
    client, pid = case
    payload = {'revision': state['revision'], 'evidence_ids': ['performances:proof'],
               'link_revision': state['requirements'][0]['link_revision'],
               'note': '核对过所选合同的服务范围', 'confirmed': True, **changes}
    return client.put(f'/api/projects/{pid}/requirements/{state["requirements"][0]["id"]}',
                      params={'profile': '关联测试企业', 'pkg_index': 0}, json=payload)


def test_requirement_binding_is_scoped_and_does_not_approve_bid(case):
    state = get(case)
    assert [e['id'] for e in state['evidence']] == ['performances:proof']
    assert state['requirements'][0]['status'] == 'unlinked'
    assert save(case, state).status_code == 200
    assert save(case, state, note='并发旧编辑不能覆盖新记录').status_code == 409
    assert get(case)['requirements'][0]['status'] == 'confirmed'
    assert get(case, index=1)['requirements'][0]['status'] == 'unlinked'
    assert get(case, company='其他企业')['requirements'][0]['status'] == 'unlinked'
    assert get(case)['review'] is None and get(case)['blockers']
    assert save(case, get(case), evidence_ids=['performances:unused']).status_code == 409
    assert save(case, get(case), evidence_ids=[], note='').status_code == 409


def test_binding_expires_on_selected_evidence_change_not_unrelated_contact(case):
    state = get(case)
    save(case, state)
    client, _ = case
    profile = client.get('/api/profiles/关联测试企业').json()
    profile['phone'] = '12345'
    client.put('/api/profiles/关联测试企业', json=profile)
    assert get(case)['requirements'][0]['status'] == 'confirmed'
    assert save(case, state).status_code == 409  # 防止使用过期编辑快照覆盖。
    profile['performances'][0]['project'] = '已变更的服务合同'
    client.put('/api/profiles/关联测试企业', json=profile)
    assert get(case)['requirements'][0]['status'] == 'stale'


def test_document_position_is_bound_to_current_version_and_file_integrity(case, monkeypatch, tmp_path):
    client, pid = case
    folder = tmp_path / pid / 'out'
    folder.mkdir(parents=True)
    monkeypatch.setattr('jb_api.workspace.output_dir', lambda _: str(folder))
    path = folder / '技术文件.docx'
    doc = Document()
    doc.add_heading('业绩响应', 1)
    doc.add_paragraph('本次提供的合同范围见所附证明。')
    doc.save(path)
    with session() as s:
        p = s.get(Project, pid)
        artifact = {'id': 'generation-one', 'pkg_index': 0, 'profile': '关联测试企业',
                    'created_at': '2026-01-01T00:00:00',
                    'files': {path.name: workflow.file_hash(path)}, 'input_hash': workflow.inputs(s, p, '关联测试企业')[2]}
        s.add(Task(id=artifact['id'], project_id=pid, kind='generate', status='done', result={}))
        workflow.save_artifact(p, artifact)
    params = {'profile': '关联测试企业', 'pkg_index': 0, 'filename': path.name}
    preview = client.get(f'/api/projects/{pid}/document-preview', params=params)
    assert preview.status_code == 200, preview.text
    block = preview.json()['blocks'][1]['id']
    response = {'filename': path.name, 'generation_id': 'generation-one', 'block_id': block}
    assert save(case, get(case), response=response).status_code == 200
    assert save(case, get(case), response={**response, 'block_id': 'block-999'}).status_code == 409
    assert save(case, get(case), response={**response, 'generation_id': 'older'}).status_code == 409
    for changes in ({'pkg_index': 1}, {'profile': '其他企业'}, {'filename': '../技术文件.docx'}):
        assert client.get(f'/api/projects/{pid}/document-preview', params={**params, **changes}).status_code == 409
    doc.add_paragraph('文件被外部修改')
    doc.save(path)
    assert client.get(f'/api/projects/{pid}/document-preview', params=params).status_code == 409
    assert get(case)['requirements'][0]['status'] == 'stale'


def test_source_preview_uses_selected_package_and_exposes_unavailable_source(case, monkeypatch, tmp_path):
    _, pid = case
    archive = tmp_path / 'test.zip'
    archive.write_bytes(b'test')
    doc = Document()
    doc.add_paragraph('采购原文只读预览')
    source = tmp_path / '采购文件.docx'
    doc.save(source)
    seen = []

    def files(path, pkg, workdir):
        seen.append(pkg.sub_no)
        return SimpleNamespace(main_doc=str(source), spec_docs={'spec': str(source)})

    monkeypatch.setattr(traceability, 'package_files', files)
    with session() as s:
        p = s.get(Project, pid)
        p.zip_path = str(archive)
        assert traceability.source_document(p, 1, 'main')['blocks'][0]['text'] == '采购原文只读预览'
        assert seen == ['B']
        with pytest.raises(ValueError):
            traceability.source_document(p, 1, 'spec:-1')
        with pytest.raises(ValueError):
            traceability.source_document(p, 1, '/etc/passwd')
    assert case[0].get(f'/api/projects/{pid}/requirements', params={'profile': '关联测试企业', 'pkg_index': -1}).status_code == 400
