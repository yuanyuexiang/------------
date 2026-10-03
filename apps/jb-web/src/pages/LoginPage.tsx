import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Alert, Button, ConfigProvider, Form, Input } from 'antd'
import { ArrowRightOutlined, CheckCircleFilled, FileTextOutlined, LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useAuth } from '../auth'
import './LoginPage.css'

export default function LoginPage() {
  const nav = useNavigate()
  const [params] = useSearchParams()
  const login = useAuth((s) => s.login)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const submit = async (v: { username: string; password: string }) => {
    setLoading(true); setError('')
    try {
      await login(v.username, v.password)
      nav(params.get('next') || '/', { replace: true })
    } catch (e) { setError(String(e instanceof Error ? e.message : e)) } finally { setLoading(false) }
  }
  return (
    <ConfigProvider theme={{ token: { colorPrimary: '#2165e8', borderRadius: 10, fontSize: 15 } }}>
      <main className="login-page">
        <header className="login-brand">
          <span className="login-brand-icon"><FileTextOutlined /></span>
          <span className="login-brand-name">金榜<span>JINBANG</span></span>
          <span className="login-brand-divider" />
          <span className="login-brand-description">国网智能投标管理系统</span>
        </header>

        <div className="login-content">
          <section className="login-intro" aria-labelledby="login-headline">
            <div className="login-eyebrow"><span /> 为每一次投标，做好准备</div>
            <h1 id="login-headline">让投标更从容<br /><span>让专业更出众</span></h1>
            <p className="login-intro-description">从招标文件解析到投标文件生成，<br />将繁杂要求理清，让每一步都有据可依。</p>

            <div className="login-visual" aria-hidden="true">
              <div className="login-document">
                <div className="login-document-top"><FileTextOutlined /><span>投标工作台</span><span className="login-document-dots">•••</span></div>
                <div className="login-document-title">项目要求，一目了然</div>
                <div className="login-document-line" /><div className="login-document-line short" />
                <div className="login-document-row"><span className="login-mini-icon"><FileTextOutlined /></span><div>招标文件解析<small>提取关键条款与项目要求</small></div><CheckCircleFilled /></div>
                <div className="login-document-row"><span className="login-mini-icon"><SafetyCertificateOutlined /></span><div>资格与合规检查<small>逐项核查，及时发现待补充材料</small></div><CheckCircleFilled /></div>
                <div className="login-document-progress"><span /> <span /> <span /></div>
              </div>
              <div className="login-floating-badge"><CheckCircleFilled /><div>有据可依<small>让准备更有条理</small></div></div>
            </div>
            <div className="login-capabilities"><span>智能解析</span><i /><span>资格自检</span><i /><span>文件生成</span><i /><span>合规审查</span></div>
          </section>

          <section className="login-panel" aria-labelledby="login-form-title">
            <div className="login-panel-eyebrow">欢迎使用金榜</div>
            <h2 id="login-form-title">登录工作台</h2>
            <p className="login-panel-description">继续您的投标准备工作</p>
            {error && <Alert type="error" showIcon message={error} className="login-error" />}
            <Form onFinish={submit} layout="vertical" size="large" requiredMark={false}>
              <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input prefix={<UserOutlined />} placeholder="请输入用户名" autoComplete="username" autoFocus />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" autoComplete="current-password" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={loading} className="login-submit">登录工作台 {!loading && <ArrowRightOutlined />}</Button>
            </Form>
            <div className="login-account-help"><SafetyCertificateOutlined /><span>账号由企业管理员统一管理<br /><small>如需开通账号或重置密码，请联系管理员</small></span></div>
            <div className="login-panel-footer">企业专属工作空间 · 专注每一份投标</div>
          </section>
        </div>
        <footer className="login-footer"><span>金榜 · 国网智能投标管理系统</span><span>专业准备，从容投标</span></footer>
      </main>
    </ConfigProvider>
  )
}
