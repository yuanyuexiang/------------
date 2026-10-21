"""路径、原件隔离与起草溯源回归；全部使用临时合成数据。"""
import io
import zipfile
from pathlib import Path

import pytest
from jb_agents.writer import _check_numbers
from jb_parser.pipeline import package_files
from jb_parser.trm import PackageTRM, SpecDoc
from jb_parser.unpack import unpack


@pytest.mark.parametrize('name', ['../escape.txt', '/escape.txt', 'C:/escape.txt', '..\\escape.txt'])
def test_reject_archive_escape(tmp_path, name):
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(name, 'synthetic')
    with pytest.raises(ValueError, match='不安全'):
        unpack(str(archive), str(tmp_path / 'dest'))
    assert not (tmp_path / 'escape.txt').exists()


def test_nested_archive_escape(tmp_path):
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, 'w') as z:
        z.writestr('../escape.txt', 'synthetic')
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('nested.zip', nested.getvalue())
    with pytest.raises(ValueError):
        unpack(str(archive), str(tmp_path / 'dest'))


@pytest.mark.parametrize('name', ['../escape.zip', 'dir/escape.zip', 'C:escape.zip'])
def test_reject_upload_path(client, name):
    response = client.post('/api/projects', files={'file': (name, b'fake', 'application/zip')})
    assert response.status_code == 400
    assert client.get('/api/projects').json() == []


def test_package_originals_are_scoped(tmp_path):
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for sub in ('051', '052'):
            root = f'分标{sub}/包1_完整招标文件_123'
            z.writestr(root + '/招标文件.docx', sub)
            z.writestr(root + '/技术规范书.docx', sub)
    pkg = PackageTRM(sub_no='分标052', pkg_no='包1',
                     spec_docs=[SpecDoc(spec_id='S', source='技术规范书.docx')])
    result = package_files(str(archive), pkg, workdir=str(tmp_path / 'dest'))
    assert Path(result.main_doc).read_text() == '052'
    assert Path(result.spec_docs['S']).read_text() == '052'
    missing = package_files(str(archive), sub_no='分标053', pkg_no='包1',
                            workdir=str(tmp_path / 'other'))
    assert missing.main_doc is None


def test_ambiguous_original_is_rejected(tmp_path):
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('a/招标文件.docx', 'a')
        z.writestr('b/招标文件.docx', 'b')
    with pytest.raises(ValueError, match='不唯一'):
        package_files(str(archive), workdir=str(tmp_path / 'dest'))


@pytest.mark.parametrize('text', [
    '保证99999小时 [来源:made-up]',
    '保证99999小时 [来源:fact-company]',
    '保证3小时',
])
def test_unsubstantiated_numbers_are_blocked(text):
    checked, violations = _check_numbers(text, {'fact-company': '员工20人'})
    assert violations and '【待补充' in checked


def test_cited_number_requires_matching_evidence():
    text = '企业员工20人 [来源:fact-company]'
    assert _check_numbers(text, {'fact-company': '员工20人'}) == (text, [])


def test_source_does_not_cover_the_next_sentence_or_placeholder_line():
    text = '员工20人。[来源:company]保证20小时。另有【待补充：证明】保证99999小时。'
    checked, violations = _check_numbers(text, {'company': '员工20人'})
    assert '20' in violations and '99999' in violations
    assert '保证20小时' not in checked and '保证99999小时' not in checked


def test_source_identifier_is_not_numeric_evidence():
    checked, violations = _check_numbers('交付20台 [来源:fact-perf-20]',
                                         {'fact-perf-20': '[来源:fact-perf-20] 系统实施'})
    assert '20' in violations and '【待补充' in checked


def test_nested_files_remain_relative_through_symlink(tmp_path):
    folder = tmp_path / 'real'
    folder.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(folder, target_is_directory=True)
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, 'w') as z:
        z.writestr('中文.txt', '正常内容')
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('nested.zip', nested.getvalue())
    result = unpack(str(archive), str(alias))
    assert result.files == ['nested/中文.txt']
    assert (Path(result.root) / result.files[0]).read_text() == '正常内容'


def test_list_number_does_not_exempt_business_number():
    checked, violations = _check_numbers('1. 保证1小时', {})
    assert '1' in violations and '保证1小时' not in checked
