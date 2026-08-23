import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { api, fmtUtc, User } from '../api'
import { useAuth } from '../auth'

/** 用户与权限（仅管理员）：两种角色 + 按人的价格可见开关；新建/重置密码后强制改密。 */
export default function UsersPage() {
  const qc = useQueryClient()
  const me = useAuth((s) => s.user)
  const { data = [], isLoading } = useQuery({ queryKey: ['users'], queryFn: api.users })
  const [editing, setEditing] = useState<User | 'new' | null>(null)
  const [form] = Form.useForm()
  const refresh = () => qc.invalidateQueries({ queryKey: ['users'] })

  const save = useMutation({
    mutationFn: async () => {
      const v = await form.validateFields()
      return editing === 'new' ? api.createUser(v) : api.updateUser((editing as User).id, v)
    },
    onSuccess: () => { message.success('已保存'); setEditing(null); refresh() },
    onError: (e) => message.error(String(e)),
  })
  const quick = async (u: User, patch: Parameters<typeof api.updateUser>[1]) => {
    try { await api.updateUser(u.id, patch); refresh() } catch (e) { message.error(String(e)) }
  }
  const open = (u: User | 'new') => {
    setEditing(u)
    form.resetFields()
    if (u !== 'new') form.setFieldsValue({ display_name: u.display_name, role: u.role, can_view_price: u.can_view_price, active: u.active })
    else form.setFieldsValue({ role: 'member', can_view_price: false })
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Alert type="info" showIcon message="角色只有两种：管理员（管用户、改配置中心）和成员（做投标、维护知识库）。价格数据（报价单校验、基准价模拟）按人开启「可见价格」，管理员天然可见。所有操作记录操作人，见项目时间线。" />
      <Card size="small" title="用户" extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => open('new')}>新建用户</Button>}>
        <Table<User> size="small" rowKey="id" loading={isLoading} dataSource={data} pagination={false}
          columns={[
            { title: '用户名', dataIndex: 'username', width: 140, render: (v: string, u) => <Space>{v}{u.id === me?.id && <Tag>我</Tag>}</Space> },
            { title: '显示名', dataIndex: 'display_name', width: 140 },
            { title: '角色', dataIndex: 'role', width: 110, render: (r: string, u) => (
              <Select size="small" value={r} style={{ width: 96 }} disabled={u.id === me?.id} onChange={(v) => quick(u, { role: v as User['role'] })}
                options={[{ value: 'admin', label: '管理员' }, { value: 'member', label: '成员' }]} />
            ) },
            { title: '可见价格', dataIndex: 'can_view_price', width: 100, render: (v: boolean, u) => <Switch size="small" checked={v} disabled={u.role === 'admin'} onChange={(c) => quick(u, { can_view_price: c })} /> },
            { title: '启用', dataIndex: 'active', width: 80, render: (v: boolean, u) => <Switch size="small" checked={v} disabled={u.id === me?.id} onChange={(c) => quick(u, { active: c })} /> },
            { title: '密码', dataIndex: 'must_change_password', width: 110, render: (v: boolean) => v ? <Tag color="orange">待改初始密码</Tag> : <Tag color="green">已设置</Tag> },
            { title: '最近登录', dataIndex: 'last_login_at', width: 150, render: (v: string | null) => v ? fmtUtc(v) : <Typography.Text type="secondary">从未</Typography.Text> },
            { title: '创建', dataIndex: 'created_at', width: 150, render: fmtUtc },
            { title: '操作', width: 150, render: (_, u) => (
              <Space size="small">
                <Button size="small" type="link" onClick={() => open(u)}>编辑</Button>
                <Popconfirm title={`删除用户 ${u.username}？历史记录里的操作人仍会保留用户名`} onConfirm={async () => { try { await api.deleteUser(u.id); refresh() } catch (e) { message.error(String(e)) } }}>
                  <Button size="small" type="link" danger disabled={u.id === me?.id}>删除</Button>
                </Popconfirm>
              </Space>
            ) },
          ]} />
      </Card>

      <Modal open={editing !== null} title={editing === 'new' ? '新建用户' : `编辑 ${(editing as User | null)?.username ?? ''}`} onCancel={() => setEditing(null)} onOk={() => save.mutate()} confirmLoading={save.isPending} destroyOnClose>
        <Form form={form} layout="vertical">
          {editing === 'new' && <Form.Item name="username" label="用户名（登录用）" rules={[{ required: true, message: '必填' }, { pattern: /^[a-zA-Z0-9_.-]{2,32}$/, message: '2~32 位字母/数字/_.-' }]}><Input /></Form.Item>}
          <Form.Item name="display_name" label="显示名"><Input placeholder="如：张三" /></Form.Item>
          {editing === 'new'
            ? <Form.Item name="password" label="初始密码（至少 6 位，首次登录强制修改）" rules={[{ required: true, min: 6, message: '至少 6 位' }]}><Input.Password /></Form.Item>
            : <Form.Item name="reset_password" label="重置密码（留空不改；设置后该用户下次登录须改密）" rules={[{ min: 6, message: '至少 6 位' }]}><Input.Password /></Form.Item>}
          <Form.Item name="role" label="角色"><Select options={[{ value: 'admin', label: '管理员' }, { value: 'member', label: '成员' }]} /></Form.Item>
          <Form.Item name="can_view_price" label="可见价格数据" valuePropName="checked"><Switch /></Form.Item>
          {editing !== 'new' && <Form.Item name="active" label="启用" valuePropName="checked"><Switch /></Form.Item>}
        </Form>
      </Modal>
    </Space>
  )
}
