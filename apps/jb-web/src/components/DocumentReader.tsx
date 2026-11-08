import { useEffect, useRef, useState } from 'react'
import { Alert, Empty, Input, Space, Spin, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { api, DocumentPreview } from '../api'
import { errorMessage } from '../uiLabels'
import './RequirementsPanel.css'

export function DocumentReader({ document, selected, onSelect }: { document: DocumentPreview; selected?: string; onSelect?: (id: string) => void }) {
  const [search, setSearch] = useState('')
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (selected) root.current?.querySelector(`[data-block="${selected.replace(/[^a-z0-9-]/g, '')}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [selected, document])
  const blocks = document.blocks.filter(b => !search || b.text.includes(search))
  return <div className="document-reader">
    <Input.Search aria-label="查找文档内容" placeholder="查找条款、姓名或响应文字" value={search} onChange={e => setSearch(e.target.value)} allowClear />
    <Typography.Paragraph type="secondary" style={{ marginBlock: 8 }}>内容预览不还原 Word 分页与图片版式。图片请核对原文件；段落编号只用于定位。</Typography.Paragraph>
    <div className="document-reader-body" ref={root}>
      {!blocks.length && <Empty description="未找到匹配内容，请尝试条款编号或更短的文字" />}
      {blocks.map(block => <section key={block.id} data-block={block.id} className={`document-block ${selected === block.id ? 'selected' : ''}`}>
        <Space wrap><Typography.Text type="secondary">{block.heading || '正文'} · {block.id.replace('block-', '位置 ')}</Typography.Text>
          {onSelect && <button type="button" className="document-select" aria-pressed={selected === block.id} onClick={() => onSelect(block.id)}>{selected === block.id ? '已选此位置' : '关联此位置'}</button>}</Space>
        {block.kind === 'table' ? <div className="document-table"><table><tbody>{block.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody></table></div>
          : <p>{block.text}</p>}
        {!!block.images && <Tag>包含 {block.images} 个图件，请在原文件中核对</Tag>}
      </section>)}
    </div>
  </div>
}

export default function SourceDocument({ id, pkgIndex, source = 'main' }: { id: string; pkgIndex: number; source?: string }) {
  const { data, error, isLoading } = useQuery({ queryKey: ['source-document', id, pkgIndex, source], queryFn: () => api.sourceDocument(id, pkgIndex, source), staleTime: 60000, retry: false })
  if (isLoading) return <Spin />
  if (error) return <Alert type="warning" showIcon message="本包原件暂时无法预览" description={<>{errorMessage(error)}<div><a href={api.sourceArchiveUrl(id)}>下载采购压缩包核对原件</a></div></>} />
  return data ? <><Typography.Paragraph strong>{data.filename}</Typography.Paragraph><Typography.Paragraph><a href={api.sourceArchiveUrl(id)}>下载采购压缩包核对原版式与图件</a></Typography.Paragraph><DocumentReader document={data} /></> : null
}
