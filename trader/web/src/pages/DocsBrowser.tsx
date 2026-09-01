/** 文档区(原型画面九):系统知识资产与执行产出的浏览。
 * 按类型(library:跨天知识)/ 按日期(ephemeral:执行流水)两个旋钮,数据驱动自 manifest.doc_classes。 */
import { Segmented } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get } from '../api/client'
import { OP } from '../lib/icons'
import { PageState, StatusBadge } from '../lib/ui'
import type { DocContent, DocumentBrief, SystemRow } from '../api/types'
import './DocsBrowser.css'

/** manifest.doc_classes 的收窄形状(透传 dict,ADR-0014)。 */
type DocClasses = { library?: string[]; ephemeral?: string[] }

export default function DocsBrowser() {
  const { name = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const initialDoc = params.get('doc_type')
    ? { doc_type: params.get('doc_type') ?? '', name: params.get('doc_name') ?? '', date: params.get('doc_date') ?? '' }
    : null
  const [mode, setMode] = useState<'type' | 'date'>(initialDoc?.date ? 'date' : 'type')
  const [open, setOpen] = useState<{ doc_type: string, name: string, date: string } | null>(initialDoc)

  const detail = useQuery({ queryKey: ['systemDetail', name], queryFn: () => get<SystemRow>(`/systems/${encodeURIComponent(name)}`) })
  const docs = useQuery({
    queryKey: ['docsAll', name],
    queryFn: () => get<DocumentBrief[]>(`/docs?system=${encodeURIComponent(name)}`),
    staleTime: 15000,
  })

  const classes = (detail.data?.manifest?.doc_classes
    ?? { library: ['expectation', 'research', 'note'], ephemeral: ['premarket', 'close'] }) as DocClasses
  const all = (docs.data ?? []).filter(d =>
    [...(classes.library ?? []), ...(classes.ephemeral ?? [])].includes(d.doc_type))

  if (docs.isLoading || docs.error) return <PageState query={docs} />

  function DocRow({ d }: { d: DocumentBrief }) {
    return (
      <div className="doc-row" onClick={() => setOpen({ doc_type: d.doc_type, name: d.name ?? '', date: d.trade_date ?? '' })}>
        <span>{(classes.library ?? []).includes(d.doc_type) ? <OP.lib /> : <OP.doc />}</span>
        <span>{d.name || d.doc_type}</span>
        <span className="m">{[d.doc_type, d.trade_date, (d.updated_at ?? '').slice(5, 16)].filter(Boolean).join(' · ')}</span>
      </div>
    )
  }

  const byType = (classes.library ?? []).map(t => ({ t, rows: all.filter(d => d.doc_type === t) }))
  const ephemTypes = classes.ephemeral ?? []
  const dates = [...new Set(all.filter(d => ephemTypes.includes(d.doc_type))
    .map(d => d.trade_date ?? ''))].sort().reverse()

  return (
    <div className="ws-panel">
      <div className="ws-phead" style={{ borderBottom: 'none' }}>
        <span style={{ fontSize: 15, fontWeight: 700 }}><OP.lib /> 文档</span>
        <StatusBadge>{all.length} 份</StatusBadge>
        <Segmented style={{ marginLeft: 'auto' }} value={mode} onChange={(v) => setMode(v as 'type' | 'date')}
                   options={[{ label: '按类型(知识资产)', value: 'type' }, { label: '按日期(执行流水)', value: 'date' }]} />
      </div>
      <div style={{ color: 'var(--text-3)', fontSize: 12, marginBottom: 8 }}>
        按类型 = 跨天存活的知识(预期/研究);按日期 = 执行产出(预案/复盘——户口在场次,此处只是索引)
      </div>

      {mode === 'type' ? (
        byType.map(({ t, rows }) => rows.length ? (
          <div key={t}>
            <div className="doc-group"><OP.lib /> {t} <span style={{ color: 'var(--text-3)', fontWeight: 400, fontSize: 11.5 }}>{rows.length}</span></div>
            {rows.slice(0, 30).map((d, i) => <DocRow key={i} d={d} />)}
          </div>
        ) : null)
      ) : (
        dates.map(dt => (
          <div key={dt}>
            <div className="doc-group"><OP.calendar /> {dt || '未记日期'}</div>
            {all.filter(d => (d.trade_date ?? '') === dt && ephemTypes.includes(d.doc_type))
              .map((d, i) => <DocRow key={i} d={d} />)}
          </div>
        ))
      )}
      {!all.length && <div style={{ color: 'var(--text-3)', padding: 30, textAlign: 'center' }}>
        还没有文档——跑一次盘前/看盘就有了</div>}

      {open && <DocViewer system={name} doc={open} onClose={() => {
        setOpen(null)
        setParams({}, { replace: true })
      }} />}
    </div>
  )
}

function DocViewer({ system, doc, onClose }: {
  system: string, doc: { doc_type: string, name: string, date: string }, onClose: () => void }) {
  const c = useQuery({
    queryKey: ['docContent', system, doc.doc_type, doc.name, doc.date],
    queryFn: () => get<DocContent>(`/docs/content?doc_type=${encodeURIComponent(doc.doc_type)}&name=${encodeURIComponent(doc.name)}&date=${encodeURIComponent(doc.date)}&system=${encodeURIComponent(system)}`),
  })
  return (
    <div className="doc-viewer-overlay" onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(16,24,40,.45)', zIndex: 1000,
             display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
      <div className="doc-viewer-dialog" onClick={e => e.stopPropagation()} style={{ background: 'var(--surface)', borderRadius: 12, maxWidth: 760, width: '100%',
                maxHeight: '80vh', overflow: 'auto', padding: '18px 22px', boxShadow: '0 20px 60px rgba(16,24,40,.3)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
          <b>{doc.name || doc.doc_type}</b>
          <StatusBadge>{doc.doc_type}</StatusBadge>
          <span style={{ marginLeft: 'auto', cursor: 'pointer', color: 'var(--text-3)' }} onClick={onClose}><OP.close /></span>
        </div>
        <PageState query={c} size="panel">
          <div className="markdown-body"><Markdown remarkPlugins={[remarkGfm]}>{c.data?.content ?? '(无内容)'}</Markdown></div>
        </PageState>
      </div>
    </div>
  )
}
