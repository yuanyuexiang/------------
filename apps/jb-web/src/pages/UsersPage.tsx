import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Descriptions, Drawer, Form, Input, Modal, Select, Space, Switch, Table, Tabs, Tag, Typography, message } from 'antd'
import { PlusOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { AccountAudit, api, fmtUtc, User } from '../api'
import { useAuth } from '../auth'
import UserAvatar from '../components/UserAvatar'

const ACTIONS: Record<string, string> = { create: '新增账号', update: '修改资料或权限', enable: '恢复账号', disable: '停用账号', reset_password: '重置密码', change_password: '修改密码', login: '登录', avatar_update: '设置头像', avatar_remove: '移除头像' }
const FIELDS: Record<string, string> = { display_name: '姓名', role: '角色', can_view_price: '单独授予价格权限', active: '启用状态' }
const valueLabel = (value: unknown) => value === true ? '是' : value === false ? '否' : value === 'admin' ? '管理员' : value === 'member' ? '成员' : String(value ?? '—')
function changes(before: Record<string, unknown> = {}, after: Record<string, unknown> = {}) {
  return Object.keys(after).filter(k => before[k] !== after[k]).map(k => `${FIELDS[k] ?? k}：${valueLabel(before[k])} → ${valueLabel(after[k])}`)
}

function AuditList({ targetId = '' }: { targetId?: string }) {
  const [filters, setFilters] = useState({ action: '', result: '', page: 1 })
  const { data, isFetching, error } = useQuery({ queryKey: ['account-audit', targetId, filters], queryFn: () => api.accountAudit({ ...filters, target_id: targetId }) })
  return <Space direction="vertical" style={{ width: '100%' }} size="middle">
    <Typography.Text type="secondary">记录本次升级后的账号操作，历史记录不补造。密码和令牌不会写入日志。</Typography.Text>
    <Space wrap>
      <Select aria-label="操作类型" style={{ width: 180 }} value={filters.action} onChange={action => setFilters(f => ({ ...f, action, page: 1 }))} options={[{ value: '', label: '全部操作' }, ...Object.entries(ACTIONS).map(([value, label]) => ({ value, label }))]} />
      <Select aria-label="操作结果" style={{ width: 130 }} value={filters.result} onChange={result => setFilters(f => ({ ...f, result, page: 1 }))} options={[{ value: '', label: '全部结果' }, { value: 'success', label: '成功' }, { value: 'failed', label: '失败' }]} />
    </Space>
    {error && <Alert type="error" message={String(error)} />}
    <Table<AccountAudit> rowKey="id" size="small" loading={isFetching} dataSource={data?.rows ?? []} scroll={{ x: 700 }} pagination={{ current: filters.page, pageSize: 10, total: data?.total ?? 0, showSizeChanger: false, onChange: page => setFilters(f => ({ ...f, page })) }} columns={[
      { title: '时间', dataIndex: 'created_at', width: 155, render: fmtUtc },
      { title: '操作人', dataIndex: 'actor', render: v => v || '未认证访客' },
      { title: '对象账号', dataIndex: 'target_name', render: v => v || '—' },
      { title: '操作', dataIndex: 'action', render: v => ACTIONS[v] ?? v },
      { title: '结果', dataIndex: 'ok', render: v => <Tag color={v ? 'green' : 'red'}>{v ? '成功' : '失败'}</Tag> },
      { title: '变更与说明', render: (_, r) => r.detail.reason || changes(r.detail.before, r.detail.after).join('；') || '—' },
    ]} />
  </Space>
}

function PermissionGuide() {
  return <Card title={<Space><SafetyCertificateOutlined />角色与权限说明</Space>}>
    <Typography.Paragraph>角色决定功能范围，价格权限单独授予成员。当前业务资料在企业工作空间内共享，尚未按项目成员隔离。价格功能授权不对原始附件和正文中的金额自动脱敏。</Typography.Paragraph>
    <Table rowKey="feature" pagination={false} dataSource={[
      { feature: '投标项目、企业知识库', admin: '可使用和维护', member: '可使用和维护' },
      { feature: '用户管理、配置修改、AI 连接与日志', admin: '可管理', member: '不可管理' },
      { feature: '评分模板与否决规则查询', admin: '可查看', member: '可查看' },
      { feature: '价格功能（报价校验、基准价模拟）', admin: '角色自带', member: '需单独授权' },
    ]} columns={[{ title: '功能', dataIndex: 'feature' }, { title: '管理员', dataIndex: 'admin' }, { title: '成员', dataIndex: 'member' }]} />
    <Typography.Paragraph style={{ marginTop: 20 }}>新增账号默认为成员且不授予价格权限。管理员价格权限由角色继承；降为成员后，以保存时明确选择的价格权限为准。</Typography.Paragraph>
    <Typography.Paragraph type="secondary">停用账号保留历史身份；恢复后需重新登录。权限变更、重置密码或修改密码均使旧登录会话失效。</Typography.Paragraph>
  </Card>
}

type Draft = { username?: string; display_name: string; role: User['role']; can_view_price: boolean }
type Confirmation = { title: string; lines: string[]; run: (password: string) => Promise<void> }

export default function UsersPage() {
  const qc = useQueryClient()
  const me = useAuth(s => s.user)
  const refreshMe = useAuth(s => s.refresh)
  const [tab, setTab] = useState('people')
  const [filters, setFilters] = useState({ q: '', role: '', active: '', price: '', page: 1 })
  const { data, isFetching, error } = useQuery({ queryKey: ['users', filters], queryFn: () => api.users(filters) })
  const [editing, setEditing] = useState<User | 'new' | null>(null)
  const [drawerTab, setDrawerTab] = useState('basic')
  const [form] = Form.useForm<Draft>()
  const role = Form.useWatch('role', form)
  const [busy, setBusy] = useState(false)
  const [confirmation, setConfirmation] = useState<Confirmation>()
  const [password, setPassword] = useState('')
  const [credential, setCredential] = useState<{ username: string; password: string }>()
  const refresh = () => { void qc.invalidateQueries({ queryKey: ['users'] }); void qc.invalidateQueries({ queryKey: ['account-audit'] }) }
  const action = async (run: () => Promise<void>) => {
    setBusy(true)
    try { await run(); refresh(); return true } catch (e) { message.error(String(e)); refresh(); return false } finally { setBusy(false) }
  }
  const ask = (value: Confirmation) => { setPassword(''); setConfirmation(value) }
  const open = (user: User | 'new') => {
    form.resetFields(); setDrawerTab('basic'); setEditing(user)
    form.setFieldsValue(user === 'new' ? { display_name: '', role: 'member', can_view_price: false } : { display_name: user.display_name, role: user.role, can_view_price: user.role === 'admin' ? false : user.can_view_price })
  }
  const save = async () => {
    let values: Draft
    try { values = await form.validateFields() } catch { return }
    const creating = editing === 'new'
    if (!editing) return
    const selected = editing
    const patch = { ...values, can_view_price: values.role === 'admin' ? false : values.can_view_price }
    const run = async (confirmation_password = '') => {
      if (creating) {
        const result = await api.createUser({ ...patch, username: values.username!, confirmation_password })
        setCredential({ username: result.user.username, password: result.temporary_password })
      } else {
        const { username: _username, ...body } = patch
        await api.updateUser((selected as User).id, { ...body, confirmation_password })
        if ((selected as User).id === me?.id) await refreshMe()
        message.success('用户资料已保存')
      }
      setEditing(null)
    }
    const sensitive = creating ? values.role === 'admin' || values.can_view_price : values.role !== (selected as User).role || (values.role !== 'admin' && values.can_view_price !== (selected as User).can_view_price)
    if (sensitive) ask({ title: creating ? '确认创建授权账号' : '确认权限变更', lines: creating ? [`账号：${values.username}`, `角色：${valueLabel(values.role)}`, `价格权限：${values.role === 'admin' ? '管理员自带' : valueLabel(values.can_view_price)}`] : [`账号：${(selected as User).username}`, ...changes({ role: (selected as User).role, can_view_price: (selected as User).can_view_price }, { role: values.role, can_view_price: values.role === 'admin' ? true : values.can_view_price }), '保存后该用户的旧会话将失效。'], run })
    else await action(() => run())
  }
  const changeStatus = (user: User) => ask({ title: user.active ? '停用账号' : '恢复账号', lines: [`账号：${user.username}`, user.active ? '该账号将无法登录，现有会话立即失效。历史操作记录保留。' : '该账号恢复使用，须重新登录；原有角色和权限保持不变。'], run: async confirmation_password => {
    await api.updateUser(user.id, { active: !user.active, confirmation_password }); setEditing(null); message.success(user.active ? '账号已停用' : '账号已恢复')
  } })
  const reset = (user: User) => ask({ title: '重置密码', lines: [`账号：${user.username}`, '将生成新的临时密码，旧密码与旧会话立即失效。用户下次登录必须修改密码。'], run: async confirmation_password => {
    const result = await api.resetUserPassword(user.id, confirmation_password)
    setEditing(null); setCredential({ username: user.username, password: result.temporary_password })
  } })
  const filter = (key: string, value: string) => setFilters(f => ({ ...f, [key]: value, page: 1 }))
  return <>
    <Tabs activeKey={tab} onChange={setTab} items={[{ key: 'people', label: '人员账号' }, { key: 'permissions', label: '权限说明' }, { key: 'audit', label: '账号操作日志' }]} />
    {tab === 'permissions' ? <PermissionGuide /> : tab === 'audit' ? <Card><AuditList /></Card> : <Card title="人员账号" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => open('new')}>新增用户</Button>}>
      <Space wrap style={{ marginBottom: 20 }}>
        <Input.Search aria-label="搜索姓名或账号" placeholder="搜索姓名或账号" allowClear onSearch={v => filter('q', v)} style={{ width: 240 }} />
        <Select aria-label="角色筛选" style={{ width: 130 }} value={filters.role} onChange={v => filter('role', v)} options={[{ value: '', label: '全部角色' }, { value: 'admin', label: '管理员' }, { value: 'member', label: '成员' }]} />
        <Select aria-label="状态筛选" style={{ width: 130 }} value={filters.active} onChange={v => filter('active', v)} options={[{ value: '', label: '全部状态' }, { value: 'enabled', label: '已启用' }, { value: 'disabled', label: '已停用' }]} />
        <Select aria-label="价格权限筛选" style={{ width: 160 }} value={filters.price} onChange={v => filter('price', v)} options={[{ value: '', label: '全部价格权限' }, { value: 'allowed', label: '可见价格' }, { value: 'denied', label: '不可见价格' }]} />
      </Space>
      {error && <Alert type="error" message={String(error)} />}
      <Table<User> rowKey="id" loading={isFetching} dataSource={data?.rows ?? []} scroll={{ x: 800 }} pagination={{ current: filters.page, pageSize: 10, total: data?.total ?? 0, showSizeChanger: false, showTotal: total => `共 ${total} 人`, onChange: page => setFilters(f => ({ ...f, page })) }} columns={[
        { title: '姓名 / 账号', render: (_, u) => <Space><UserAvatar user={u} size={36} /><span><Typography.Text strong>{u.display_name}</Typography.Text> {u.id === me?.id && <Tag>我</Tag>}<br /><Typography.Text type="secondary">{u.username}</Typography.Text></span></Space> },
        { title: '角色', dataIndex: 'role_cn', render: v => <Tag>{v}</Tag> },
        { title: '价格权限', render: (_, u) => u.role === 'admin' ? '管理员自带' : u.can_view_price ? '已授权' : '未授权' },
        { title: '状态', render: (_, u) => <Space direction="vertical" size={4}><Tag color={u.active ? 'green' : 'default'}>{u.active ? '已启用' : '已停用'}</Tag>{u.must_change_password && <Tag color="orange">待改初始密码</Tag>}</Space> },
        { title: '最近登录', dataIndex: 'last_login_at', render: v => v ? fmtUtc(v) : '从未登录' },
        { title: '操作', render: (_, u) => <Button type="link" onClick={() => open(u)}>管理</Button> },
      ]} />
    </Card>}
    <Drawer title={editing === 'new' ? '新增用户' : `管理账号 · ${editing?.username ?? ''}`} width={600} open={!!editing} onClose={busy ? undefined : () => setEditing(null)} keyboard={!busy} closable={!busy} maskClosable={!busy} destroyOnClose footer={drawerTab === 'basic' && <Space><Button disabled={busy} onClick={() => setEditing(null)}>取消</Button><Button type="primary" loading={busy} onClick={() => void save()}>{editing === 'new' ? '创建账号' : '保存修改'}</Button></Space>}>
      {editing && editing !== 'new' && <Tabs activeKey={drawerTab} onChange={setDrawerTab} items={[{ key: 'basic', label: '资料与权限' }, { key: 'security', label: '账号安全' }, { key: 'activity', label: '操作记录' }]} />}
      <div style={{ display: drawerTab === 'basic' ? undefined : 'none' }}>
        {editing === 'new' && <Alert type="info" showIcon message="系统生成随机临时密码，创建后仅展示一次。首次登录必须修改密码。" style={{ marginBottom: 20 }} />}
        <Form form={form} layout="vertical" disabled={busy}>
          {editing === 'new' && <Form.Item name="username" label="登录账号" rules={[{ required: true, pattern: /^[a-zA-Z0-9_.-]{2,32}$/, message: '请输入 2～32 位字母、数字或 _ . -' }]}><Input autoComplete="off" maxLength={32} /></Form.Item>}
          <Form.Item name="display_name" label="姓名 / 显示名" rules={[{ max: 64 }]}><Input maxLength={64} placeholder="例如：张三" /></Form.Item>
          <Form.Item name="role" label="角色" extra="管理员可管理用户和系统配置，并自带价格权限。"><Select disabled={editing !== 'new' && editing?.id === me?.id} onChange={() => form.setFieldValue('can_view_price', false)} options={[{ value: 'member', label: '成员' }, { value: 'admin', label: '管理员' }]} /></Form.Item>
          {role === 'admin' ? <Alert type="info" message="价格权限由管理员角色继承，无需单独授权。" /> : <Form.Item name="can_view_price" label="价格功能权限" valuePropName="checked" extra="允许使用报价校验和基准价模拟。"><Switch /></Form.Item>}
        </Form>
        {editing && editing !== 'new' && <Descriptions style={{ marginTop: 24 }} column={1} items={[{ key: 'username', label: '登录账号', children: editing.username }, { key: 'created', label: '创建时间', children: fmtUtc(editing.created_at) }]} />}
      </div>
      {drawerTab === 'security' && editing && editing !== 'new' && <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Alert type="info" message="账号安全操作独立执行，须验证当前管理员身份。" />
        <Card size="small" title="密码"><Typography.Paragraph>{editing.must_change_password ? '用户尚未完成初始密码修改。' : '用户已设置密码。'}</Typography.Paragraph><Button disabled={editing.id === me?.id || !editing.active} onClick={() => reset(editing)}>重置密码</Button>{editing.id === me?.id && <Typography.Paragraph type="secondary">修改自己的密码请使用右上角账号菜单。</Typography.Paragraph>}</Card>
        <Card size="small" title="账号状态"><Typography.Paragraph>{editing.active ? '账号已启用。停用后禁止登录，保留历史操作记录。' : '账号已停用。恢复后需要重新登录。'}</Typography.Paragraph><Button danger={editing.active} disabled={editing.id === me?.id} onClick={() => changeStatus(editing)}>{editing.active ? '停用账号' : '恢复账号'}</Button></Card>
      </Space>}
      {drawerTab === 'activity' && editing && editing !== 'new' && <AuditList targetId={editing.id} />}
    </Drawer>
    <Modal title={confirmation?.title} open={!!confirmation} okText="确认执行" cancelText="取消" confirmLoading={busy} keyboard={!busy} closable={!busy} maskClosable={false} cancelButtonProps={{ disabled: busy }} onCancel={() => { setConfirmation(undefined); setPassword('') }} onOk={async () => {
      if (!confirmation || !password) { message.warning('请填写当前管理员密码'); return }
      const ok = await action(() => confirmation.run(password))
      setPassword('')
      if (ok) setConfirmation(undefined)
    }} destroyOnClose>
      {confirmation?.lines.map((line, index) => <Typography.Paragraph key={index}>{line}</Typography.Paragraph>)}
      <label htmlFor="account-confirm-password">当前管理员密码</label>
      <Input.Password id="account-confirm-password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} maxLength={128} style={{ marginTop: 8 }} />
    </Modal>
    <Modal title="请保存临时登录凭据" open={!!credential} onCancel={() => setCredential(undefined)} footer={<Button type="primary" onClick={() => setCredential(undefined)}>已保存，关闭</Button>} maskClosable={false} destroyOnClose>
      <Alert type="warning" showIcon message="临时密码仅在此展示一次，请通过企业认可的渠道交给本人。关闭后无法再次查看，可重新重置。" style={{ marginBottom: 16 }} />
      <Descriptions column={1} items={[{ key: 'username', label: '登录账号', children: credential?.username }]} />
      <Input.Password aria-label="临时密码" readOnly value={credential?.password ?? ''} autoComplete="off" />
      <Button style={{ marginTop: 12 }} onClick={async () => { try { await navigator.clipboard.writeText(credential?.password ?? ''); message.success('已复制临时密码') } catch { message.info('请展开密码后手动复制') } }}>复制临时密码</Button>
    </Modal>
  </>
}
