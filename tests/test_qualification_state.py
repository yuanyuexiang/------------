"""资格报告跨页面恢复及资料变更失效，不依赖本地客户样本。"""
from jb_parser.trm import TRM, PackageTRM
from jb_store import Project, session


def project(client):
    for name in ('企业甲', '企业乙'):
        assert client.put(f'/api/profiles/{name}', json={'name': name}).status_code == 200
    trm = TRM(batch_name='合成采购', packages=[
        PackageTRM(sub_no='A', pkg_no='包1'), PackageTRM(sub_no='B', pkg_no='包1'),
    ]).model_dump()
    with session() as s:
        p = Project(filename='test.zip', zip_path='', trm=trm, status='parsed')
        s.add(p)
        s.flush()
        return p.id, trm


def test_reports_restore_per_company_and_expire_when_inputs_change(client):
    pid, _ = project(client)
    url = f'/api/projects/{pid}/qualify'
    assert client.get(url, params={'profile': '企业甲'}).json() == {'report': None, 'stale': False}
    first = client.post(url, params={'profile': '企业甲'}).json()['report']
    assert len(first['packages']) == 2
    assert client.get(url, params={'profile': '企业甲'}).json() == {'report': first, 'stale': False}
    assert client.get(url, params={'profile': '企业乙'}).json()['report'] is None
    client.post(url, params={'profile': '企业乙'})
    assert client.get(url, params={'profile': '企业甲'}).json()['report'] == first
    assert 'qualification_reports' not in client.get(f'/api/projects/{pid}').json()['results']
    client.put('/api/profiles/企业甲', json={'name': '企业甲', 'phone': '12345'})
    assert client.get(url, params={'profile': '企业甲'}).json()['stale'] is True
    assert client.get(url, params={'profile': '企业乙'}).json()['stale'] is False


def test_preliminary_report_requires_recheck_after_confirmation(client):
    pid, trm = project(client)
    url = f'/api/projects/{pid}/qualify'
    client.post(url, params={'profile': '企业甲'})
    client.put(f'/api/projects/{pid}/trm', json=trm)
    assert client.get(url, params={'profile': '企业甲'}).json()['stale'] is True
    client.post(url, params={'profile': '企业甲'})
    assert client.get(url, params={'profile': '企业甲'}).json()['stale'] is False
    trm['packages'][0]['scope'] = '变更后的采购范围'
    client.put(f'/api/projects/{pid}/trm', json=trm)
    assert client.get(url, params={'profile': '企业甲'}).json()['stale'] is True
    assert client.get('/api/projects/missing/qualify', params={'profile': '企业甲'}).status_code == 404


def test_reports_from_previous_day_need_recheck_for_expiring_evidence(client):
    pid, _ = project(client)
    url = f'/api/projects/{pid}/qualify'
    client.post(url, params={'profile': '企业甲'})
    with session() as s:
        p = s.get(Project, pid)
        from jb_store.projects import set_result
        reports = dict(p.results['qualification_reports'])
        reports['企业甲'] = {**reports['企业甲'], 'checked_on': '2000-01-01'}
        set_result(p, 'qualification_reports', reports)
    assert client.get(url, params={'profile': '企业甲'}).json()['stale'] is True
