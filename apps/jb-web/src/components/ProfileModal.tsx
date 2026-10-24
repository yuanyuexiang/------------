import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Descriptions, Modal, Space, Typography, Upload, message } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { api } from '../api'
import { useAuth } from '../auth'
import UserAvatar from './UserAvatar'

export default function ProfileModal({ onClose }: { onClose: () => void }) {
  const { user, refresh } = useAuth()
  const qc = useQueryClient()
  const [file, setFile] = useState<File>()
  const [preview, setPreview] = useState<string>()
  const [remove, setRemove] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!file) { setPreview(undefined); return }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  const save = async () => {
    setBusy(true)
    try {
      if (file) await api.uploadAvatar(file)
      else if (remove) await api.removeAvatar()
      await refresh()
      void qc.invalidateQueries({ queryKey: ['users'] })
      void qc.invalidateQueries({ queryKey: ['account-audit'] })
      message.success('头像已更新'); onClose()
    } catch (e) { message.error(String(e)) } finally { setBusy(false) }
  }
  return <Modal title="个人资料" open onCancel={busy ? undefined : onClose} closable={!busy} keyboard={!busy} maskClosable={!busy} okText="保存头像" cancelText="取消" confirmLoading={busy} okButtonProps={{ disabled: !file && !remove }} cancelButtonProps={{ disabled: busy }} onOk={() => void save()}>
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Descriptions column={1} items={[{ key: 'name', label: '姓名', children: user?.display_name }, { key: 'account', label: '登录账号', children: user?.username }, { key: 'role', label: '角色', children: user?.role_cn }]} />
      <Space size="large" align="center">
        <UserAvatar user={user} size={96} src={remove ? '' : preview} />
        <Space direction="vertical">
          <Upload accept="image/jpeg,image/png,image/webp" showUploadList={false} disabled={busy} beforeUpload={candidate => {
            if (!['image/jpeg', 'image/png', 'image/webp'].includes(candidate.type)) { message.error('请选择 JPG、PNG 或 WebP 图片'); return Upload.LIST_IGNORE }
            if (candidate.size > 2 * 1024 * 1024) { message.error('图片不能超过 2 MB'); return Upload.LIST_IGNORE }
            setFile(candidate); setRemove(false); return false
          }}><Button icon={<UploadOutlined />} disabled={busy}>选择头像</Button></Upload>
          <Button type="text" disabled={busy || (!user?.avatar && !file)} onClick={() => { setFile(undefined); setRemove(true) }}>移除头像</Button>
        </Space>
      </Space>
      <Typography.Text type="secondary">支持 JPG、PNG、WebP 静态图片，不超过 2 MB、1600 万像素。头像居中裁剪为正方形，保存后同步显示于右上角和用户列表。</Typography.Text>
      <Alert type="info" showIcon message="未设置头像时显示姓名首字。选择或移除后点击“保存头像”生效。" />
    </Space>
  </Modal>
}
