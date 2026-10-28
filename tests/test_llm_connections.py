"""Multiple connections: encrypted storage, scoped execution and safe API responses."""
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import jb_llm
from jb_store import config, session
from jb_store import llm_connections as connections


def create(client, name='测试连接', key='secret-test-key'):
    response = client.post('/api/config/llm/connections', json={
        'name': name, 'base_url': 'https://model.example/v1', 'model': 'model-test',
        'api_key': key, 'max_tokens': 4096, 'timeout': 120,
    })
    assert response.status_code == 200, response.text
    assert key not in response.text
    return response.json()


def test_encrypted_storage_edit_and_default(client):
    row = create(client)
    with session() as s:
        stored = json.dumps(config.get_setting(s, connections.KEY))
    assert 'secret-test-key' not in stored
    assert connections.resolve(row['id'])['api_key'] == 'secret-test-key'
    listing = client.get('/api/config/llm/connections').json()
    assert listing['default_id'] == 'legacy'
    assert any(r['id'] == 'legacy' for r in listing['connections'])
    assert 'secret' not in json.dumps(listing)
    body = {k: v for k, v in row.items() if k not in ('id', 'key_configured')}
    body.update(name='改名', api_key='')
    assert client.put('/api/config/llm/connections/' + row['id'], json=body).status_code == 200
    assert connections.resolve(row['id'])['api_key'] == 'secret-test-key'
    assert client.post('/api/config/llm/connections/' + row['id'] + '/default').status_code == 200
    assert client.get('/api/config/llm').json()['effective']['model'] == 'model-test'
    listing = client.get('/api/config/llm/connections').json()
    assert listing['default_id'] == row['id']
    assert [r['id'] for r in listing['connections']] == [row['id']]
    assert connections.resolve('legacy')['id'] == 'legacy'  # 兼容已有任务快照
    body['api_key'] = 'replacement-key'
    client.put('/api/config/llm/connections/' + row['id'], json=body)
    assert connections.resolve(row['id'])['api_key'] == 'replacement-key'


def test_pinned_connection_and_concurrent_test(client, monkeypatch):
    first = create(client, 'A', 'key-a')
    second = create(client, 'B', 'key-b')
    connections.set_default(first['id'])
    requests = []

    def post(url, **kw):
        requests.append(kw)
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'finish_reason': 'stop', 'message': {'content': 'OK'}}],
            'usage': {'prompt_tokens': 2, 'completion_tokens': 1},
        })

    monkeypatch.setattr(jb_llm.httpx, 'post', post)
    with jb_llm.using_connection() as snapshot:
        connections.set_default(second['id'])
        with ThreadPoolExecutor() as pool:
            response = pool.submit(lambda: client.post(
                '/api/config/llm/connections/' + second['id'] + '/test')).result()
        assert response.json()['ok']
        jb_llm.chat('hello', max_tokens=12000, timeout=300)
        assert snapshot['name'] == 'A' and 'api_key' not in snapshot
    assert requests[-1]['headers']['Authorization'] == 'Bearer key-a'
    assert requests[-1]['json']['max_tokens'] == 4096
    assert requests[-1]['timeout'] == 120
    assert jb_llm.connection()['id'] == second['id']
    recent = client.get('/api/config/llm').json()['usage']['recent']
    assert {r['connection_name'] for r in recent} == {'A', 'B'}


def test_validation_and_error_redaction(client, monkeypatch):
    row = create(client)
    assert client.post('/api/config/llm/connections', json={
        'name': 'x', 'base_url': 'https://host/?key=secret', 'model': 'x', 'api_key': 'x',
    }).status_code == 400
    response = client.post('/api/config/llm/connections', json={'api_key': 'private-value'})
    assert 'private-value' not in response.text

    def fail(*args, **kwargs):
        raise httpx.ConnectError('secret-test-key private provider response')

    monkeypatch.setattr(jb_llm.httpx, 'post', fail)
    result = client.post('/api/config/llm/connections/' + row['id'] + '/test')
    assert result.json()['ok'] is False
    assert 'secret-test-key' not in result.text
    assert 'secret-test-key' not in client.get('/api/config/llm').text


def test_model_discovery_unsaved_and_saved_key(client, monkeypatch):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={'data': [{'id': 'b'}, {'id': 'a'}, {'id': 'b'}, {}, {'id': 1}]})

    monkeypatch.setattr(httpx, 'get', get)
    r = client.post('/api/config/llm/models', json={'base_url': 'https://model.example/v1', 'api_key': 'temporary-secret'})
    assert r.json()['models'] == ['a', 'b']
    assert calls[-1][1]['headers']['Authorization'] == 'Bearer temporary-secret'
    assert calls[-1][1]['follow_redirects'] is False
    assert 'temporary-secret' not in client.get('/api/config/llm/connections').text
    row = create(client)
    r = client.post('/api/config/llm/models', json={'base_url': row['base_url'], 'connection_id': row['id']})
    assert r.status_code == 200
    assert calls[-1][1]['headers']['Authorization'] == 'Bearer secret-test-key'
    before = len(calls)
    r = client.post('/api/config/llm/models', json={'base_url': 'https://other.example/v1', 'connection_id': row['id']})
    assert r.status_code == 400 and len(calls) == before
    assert client.get('/api/config/llm/connections').json()['default_id'] == 'legacy'


def test_discovery_failures_and_presets(client, monkeypatch):
    providers = client.get('/api/config/llm/providers').json()
    assert {'deepseek', 'qwen', 'glm', 'mimo', 'custom'} <= {p['id'] for p in providers}
    for status, payload in [(401, {'message': 'private-key'}), (404, {}), (200, {'data': []}), (200, {'unexpected': 'private-key'})]:
        monkeypatch.setattr(httpx, 'get', lambda *a, status=status, payload=payload, **kw: httpx.Response(status, json=payload))
        response = client.post('/api/config/llm/models', json={'base_url': 'https://model.example/v1', 'api_key': 'private-key'})
        assert response.status_code == 400
        assert 'private-key' not in response.text
    monkeypatch.setattr(httpx, 'get', lambda *a, **kw: httpx.Response(200, text='private-key not json'))
    assert 'private-key' not in client.post('/api/config/llm/models', json={'base_url': 'https://model.example/v1', 'api_key': 'private-key'}).text


def test_saved_validation_tracks_configuration(client, monkeypatch):
    row = create(client)
    assert connections.validation_status(row['id'])['state'] == 'untested'
    monkeypatch.setattr(jb_llm, 'test_connection', lambda: {'ok': True, 'latency_ms': 25})
    response = client.post('/api/config/llm/connections/' + row['id'] + '/test')
    assert response.json()['ok']
    assert connections.validation_status(row['id'])['state'] == 'passed'
    assert 'signature' not in client.get('/api/config/llm/connections').text
    body = {k: v for k, v in row.items() if k not in ('id', 'key_configured')}
    body.update(model='changed-model', api_key='')
    assert client.put('/api/config/llm/connections/' + row['id'], json=body).status_code == 200
    assert connections.validation_status(row['id'])['state'] == 'stale'
    monkeypatch.setattr(jb_llm, 'test_connection', lambda: {'ok': False, 'latency_ms': 30, 'error': 'timeout'})
    client.post('/api/config/llm/connections/' + row['id'] + '/test')
    assert connections.validation_status(row['id'])['state'] == 'failed'


def test_usage_filters_pagination_and_trace(client):
    with session() as s:
        for purpose, ok, tokens in [('test', True, 2), ('draft', True, 10), ('draft', False, 20)]:
            config.record_usage(s, dict(connection_id='example', connection_name='Example',
                model='model-test', purpose=purpose, ok=ok, prompt_tokens=tokens,
                project_id='project123', task_id='task123', latency_ms=100))
    url = '/api/config/llm/usage'
    data = client.get(url, params={'page_size': 1}).json()
    assert data['total'] == 2 and data['failed'] == 1 and data['prompt_tokens'] == 30
    assert len(data['rows']) == 1 and data['rows'][0]['project_id'] == 'project123'
    second = client.get(url, params={'page_size': 1, 'page': 2}).json()
    assert second['rows'][0]['id'] != data['rows'][0]['id']
    assert client.get(url, params={'purpose': 'test'}).json()['total'] == 1
    assert client.get(url, params={'result': 'failed'}).json()['prompt_tokens'] == 20
    assert client.get(url, params={'connection_id': 'missing'}).json()['total'] == 0
    assert client.get(url, params={'model': 'missing'}).json()['total'] == 0
    assert client.get(url, params={'page': 0}).status_code == 400
