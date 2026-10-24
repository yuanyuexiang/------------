import { Avatar } from 'antd'

export default function UserAvatar({ user, size = 32, src }: {
  user: { display_name?: string; username?: string; avatar?: string } | null
  size?: number
  src?: string
}) {
  const name = user?.display_name || user?.username || '用'
  return <Avatar size={size} src={src === undefined ? user?.avatar : src} alt={`${name}的头像`} style={{ backgroundColor: '#e8effc', color: '#2457a6', flexShrink: 0 }}>{Array.from(name)[0]}</Avatar>
}
