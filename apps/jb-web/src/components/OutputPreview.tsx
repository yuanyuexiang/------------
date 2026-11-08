import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Alert, Drawer, Select, Space, Spin, Typography } from 'antd'
import { api, Finding } from '../api'
import { errorMessage } from '../uiLabels'
import { DocumentReader } from './DocumentReader'

export default function OutputPreview({ id, profile, pkgIndex, files, filename, finding, onClose }: {
  id: string; profile: string; pkgIndex: number; files: string[]; filename?: string; finding?: Finding; onClose: () => void
}) {
  const [chosen, setChosen] = useState(filename || (files.length === 1 ? files[0] : undefined))
  const { data, isLoading, error } = useQuery({ queryKey: ['document-preview', id, profile, pkgIndex, chosen],
    queryFn: () => api.documentPreview(id, profile, pkgIndex, chosen!), enabled: !!chosen, retry: false })
  const matches = finding?.location && data ? data.blocks.filter(block => block.text.replace(/\s/g, '').includes(finding.location.replace(/\s/g, ''))) : []
  return <Drawer title={finding ? '对照文件核查问题' : '查看本版本文件内容'} open width="min(1100px, 96vw)" onClose={onClose} destroyOnClose>
    {finding && <Alert type="warning" showIcon message={`${finding.rule_id} · ${finding.title}`} description={<>{finding.message}<div>原记录位置：{finding.location || '未提供具体位置'}；依据：{finding.source || '未提供'}</div></>} />}
    <Space wrap style={{ marginBlock: 16, width: '100%' }}><Select aria-label="预览生成文件" style={{ minWidth: 260, maxWidth: '100%' }} placeholder="选择要核对的本包文件" value={chosen} onChange={setChosen} options={files.map(value => ({ value, label: value }))} />
      {chosen && <a href={api.fileUrl(id, chosen)} target="_blank" rel="noreferrer">下载 Word 查看原版式</a>}</Space>
    {finding && <Typography.Paragraph type="secondary">{matches.length === 1 ? '已按记录位置文字定位到一处内容，请继续核查。' : matches.length > 1 ? '记录位置匹配到多处内容，请用关键词缩小范围。' : '未能按记录位置唯一定位，请在内容中查找要求或问题关键词。'}不推算 Word 页码。</Typography.Paragraph>}
    {isLoading && <Spin />}{error && <Alert type="error" message="文件预览失败" description={errorMessage(error)} />}
    {data && <DocumentReader document={data} selected={matches.length === 1 ? matches[0].id : undefined} />}
  </Drawer>
}
