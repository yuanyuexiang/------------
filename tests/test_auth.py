"""账号生命周期、服务端权限和会话撤销回归。"""
from concurrent.futures import ThreadPoolExecutor

from conftest import ADMIN_PASSWORD, login_as
from jb_store import auth as au
from jb_store import session
from jb_store.models import AccountAudit, AuthThrottle, User
from sqlalchemy import select


def create(client, name='zhang', **kw):
    r = client.post('/api/users', json={'username': name, 'display_name': '张三',
        'confirmation_password': ADMIN_PASSWORD, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def activate(client, name, password):
    login_as(client, name, password)
    r = client.put('/api/auth/password', json={'old_password': password,
        'new_password': 'member-long-password-2026'})
    assert r.status_code == 200, r.text
    client.headers.update({'Authorization': 'Bearer ' + r.json()['token']})


def test_login_and_me(client):
    result = client.get('/api/auth/me').json()
    assert result['user']['username'] == 'admin' and result['user']['role'] == 'admin'
    assert result['dev_secret'] is True
    assert '_session_version' not in result['user']
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'wrong'}).status_code == 401
    assert client.get('/api/projects', headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/health', headers={'Authorization': ''}).status_code == 200
    assert client.get('/api/projects', headers={'Authorization': 'Bearer x.y'}).status_code == 401


def test_change_password_revokes_old_sessions(client):
    old_token = client.headers['Authorization']
    assert client.put('/api/auth/password', json={'old_password': 'wrong', 'new_password': 'long-password-2026'}).status_code == 403
    assert client.put('/api/auth/password', json={'old_password': ADMIN_PASSWORD, 'new_password': '123'}).status_code == 400
    assert client.put('/api/auth/password', json={'old_password': ADMIN_PASSWORD, 'new_password': ADMIN_PASSWORD}).status_code == 400
    result = client.put('/api/auth/password', json={'old_password': ADMIN_PASSWORD, 'new_password': 'new-long-password-2026'})
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'no-store'
    assert client.get('/api/auth/me', headers={'Authorization': old_token}).status_code == 401
    client.headers.update({'Authorization': 'Bearer ' + result.json()['token']})
    assert client.get('/api/auth/me').json()['user']['must_change_password'] is False
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': ADMIN_PASSWORD}).status_code == 401


def test_forced_change_is_enforced_by_backend(client):
    result = create(client)
    assert len(result['temporary_password']) >= 15
    login_as(client, 'zhang', result['temporary_password'])
    old_token = client.headers['Authorization']
    assert client.get('/api/auth/me').json()['user']['must_change_password']
    for method, path in [('GET', '/api/projects'), ('GET', '/api/config/rules'),
                         ('PUT', '/api/profiles/测试企业'), ('GET', '/api/users')]:
        response = client.request(method, path, json={})
        assert response.status_code == 403
        assert response.json()['code'] == 'PASSWORD_CHANGE_REQUIRED'
    activate(client, 'zhang', result['temporary_password'])
    assert client.get('/api/projects').status_code == 200
    assert client.get('/api/projects', headers={'Authorization': old_token}).status_code == 401


def test_roles_price_and_knowledge_workflow(client):
    result = create(client)
    uid = result['user']['id']
    assert not result['user']['can_view_price'] and result['user']['role'] == 'member'
    assert client.put('/api/profiles/测试企业', json={'name': '测试企业'}).status_code == 200
    activate(client, 'zhang', result['temporary_password'])
    for path in ['/api/users', '/api/users/audit', '/api/config/llm/connections']:
        assert client.get(path).status_code == 403
    assert client.post('/api/users', json={'username': 'other'}).status_code == 403
    assert client.put('/api/config/rules/SG-16', json={'enabled': False}).status_code == 403
    assert client.put('/api/config/llm', json={'model': 'x'}).status_code == 403
    assert client.get('/api/config/rules').status_code == 200
    assert client.post('/api/profiles/测试企业/certificates', json={'name': 'ISO9001'}).status_code == 201
    sheet = {'pkg_no': '包1', 'lines': []}
    assert client.post('/api/projects/x/price/validate', json=sheet).status_code == 403
    old_token = client.headers['Authorization']
    login_as(client, 'admin', ADMIN_PASSWORD)
    assert client.put(f'/api/users/{uid}', json={'can_view_price': True}).status_code == 400
    assert client.put(f'/api/users/{uid}', json={'can_view_price': True, 'confirmation_password': 'wrong'}).status_code == 403
    assert client.put(f'/api/users/{uid}', json={'can_view_price': True, 'confirmation_password': ADMIN_PASSWORD}).status_code == 200
    assert client.get('/api/auth/me', headers={'Authorization': old_token}).status_code == 401
    login_as(client, 'zhang', 'member-long-password-2026')
    assert client.post('/api/projects/x/price/validate', json=sheet).status_code == 200


def test_reset_disable_restore_and_history(client):
    result = create(client)
    uid = result['user']['id']
    activate(client, 'zhang', result['temporary_password'])
    old_token = client.headers['Authorization']
    login_as(client, 'admin', ADMIN_PASSWORD)
    reset = client.post(f'/api/users/{uid}/reset-password', json={'confirmation_password': ADMIN_PASSWORD})
    assert reset.status_code == 200
    assert reset.json()['user']['must_change_password']
    assert client.get('/api/auth/me', headers={'Authorization': old_token}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'zhang', 'password': 'member-long-password-2026'}).status_code == 401
    activate(client, 'zhang', reset.json()['temporary_password'])
    old_token = client.headers['Authorization']
    login_as(client, 'admin', ADMIN_PASSWORD)
    for active in [False, True]:
        assert client.put(f'/api/users/{uid}', json={'active': active, 'confirmation_password': ADMIN_PASSWORD}).status_code == 200
        assert client.get('/api/auth/me', headers={'Authorization': old_token}).status_code == 401
        if not active:
            assert client.post('/api/auth/login', json={'username': 'zhang', 'password': 'member-long-password-2026'}).status_code == 401
    logs = client.get('/api/users/audit', params={'target_id': uid, 'page_size': 100}).json()
    assert {'create', 'reset_password', 'disable', 'enable', 'change_password'} <= {r['action'] for r in logs['rows']}
    assert client.delete(f'/api/users/{uid}').status_code == 409
    with session() as s:
        serialized = str([r.detail for r in s.scalars(select(AccountAudit))])
    for secret in [ADMIN_PASSWORD, result['temporary_password'], reset.json()['temporary_password'], 'member-long-password-2026']:
        assert secret not in serialized
    assert 'password_hash' not in client.get('/api/users').text
    assert 'session_version' not in client.get('/api/users').text


def test_validation_and_no_partial_mutation(client):
    assert client.post('/api/users', json={'username': 'bad space'}).status_code == 400
    assert client.post('/api/users', json={'username': 'valid', 'password': 'should-not-echo'}).status_code == 400
    assert client.post('/api/users', json={'username': 'valid', 'role': 'unknown'}).status_code == 400
    result = create(client)
    uid = result['user']['id']
    assert client.post('/api/users', json={'username': 'zhang'}).status_code == 400
    r = client.put(f'/api/users/{uid}', json={'display_name': 'must-not-save', 'role': 'admin', 'confirmation_password': 'secret-wrong'})
    assert r.status_code == 403 and 'secret-wrong' not in r.text
    user = client.get('/api/users', params={'q': 'zhang'}).json()['rows'][0]
    assert user['display_name'] == '张三' and user['role'] == 'member'
    for body in [{'active': 'false'}, {'role': None}, {'active': None}, {'reset_password': 'unsupported'}]:
        assert client.put(f'/api/users/{uid}', json=body).status_code == 400


def test_admin_protections_and_inherited_price(client):
    me = client.get('/api/auth/me').json()['user']
    for patch in [{'active': False}, {'role': 'member'}]:
        assert client.put(f"/api/users/{me['id']}", json={**patch, 'confirmation_password': ADMIN_PASSWORD}).status_code == 400
    assert client.post(f"/api/users/{me['id']}/reset-password", json={'confirmation_password': ADMIN_PASSWORD}).status_code == 400
    assert client.post('/api/users', json={'username': 'boss', 'role': 'admin'}).status_code == 400
    other = create(client, 'boss', role='admin')
    uid = other['user']['id']
    assert other['user']['can_view_price']
    response = client.put(f'/api/users/{uid}', json={'role': 'member', 'can_view_price': False, 'confirmation_password': ADMIN_PASSWORD})
    assert response.status_code == 200 and not response.json()['can_view_price']


def test_shared_login_and_reauth_throttles(client):
    for _ in range(5):
        assert client.post('/api/auth/login', json={'username': 'nobody', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'nobody', 'password': 'wrong'}).status_code == 429
    result = create(client)
    uid = result['user']['id']
    for _ in range(5):
        assert client.put(f'/api/users/{uid}', json={'active': False, 'confirmation_password': 'wrong'}).status_code == 403
    assert client.put(f'/api/users/{uid}', json={'active': False, 'confirmation_password': ADMIN_PASSWORD}).status_code == 429
    with session() as s:
        assert len(list(s.scalars(select(AuthThrottle)))) >= 3
    # Cooldown expiry permits a fresh check; failures survive separate transactions.
    import datetime as dt
    with session() as s:
        for row in s.scalars(select(AuthThrottle)):
            row.started_at -= dt.timedelta(minutes=16)
    assert client.put(f'/api/users/{uid}', json={'active': False, 'confirmation_password': ADMIN_PASSWORD}).status_code == 200


def test_user_and_audit_pagination(client):
    create(client, 'zhang')
    create(client, 'li', can_view_price=True)
    data = client.get('/api/users', params={'role': 'member', 'page_size': 1}).json()
    assert data['total'] == 2 and len(data['rows']) == 1
    next_page = client.get('/api/users', params={'role': 'member', 'page_size': 1, 'page': 2}).json()
    assert next_page['rows'][0]['id'] != data['rows'][0]['id']
    assert client.get('/api/users', params={'price': 'denied'}).json()['total'] == 1
    assert client.get('/api/users', params={'q': '%'}).json()['total'] == 0
    assert client.get('/api/users', params={'q': '张三'}).json()['total'] == 2
    assert client.get('/api/users/audit', params={'action': 'create'}).json()['total'] == 2


def test_concurrent_admin_changes_preserve_active_admin(client):
    other = create(client, 'boss', role='admin')
    admin_id = client.get('/api/auth/me').json()['user']['id']
    admin_token = client.headers['Authorization']
    activate(client, 'boss', other['temporary_password'])
    boss_token = client.headers['Authorization']
    def demote(target, token, password):
        return client.put('/api/users/' + target, headers={'Authorization': token},
                          json={'role': 'member', 'confirmation_password': password}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(demote, other['user']['id'], admin_token, ADMIN_PASSWORD)
        b = pool.submit(demote, admin_id, boss_token, 'member-long-password-2026')
        statuses = [a.result(), b.result()]
    assert statuses.count(200) == 1
    assert any(status in (401, 403) for status in statuses)
    with session() as s:
        assert au.admin_count(s) == 1


def test_token_cannot_transfer_to_recreated_identity(client):
    result = create(client)
    login_as(client, 'zhang', result['temporary_password'])
    token = client.headers['Authorization']
    # Simulate an old DB maintenance deletion; ordinary API no longer exposes deletion.
    with session() as s:
        s.delete(s.get(User, result['user']['id']))
    with session() as s:
        au.create_user(s, 'zhang', 'another-long-password')
    assert client.get('/api/auth/me', headers={'Authorization': token}).status_code == 401
