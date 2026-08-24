/** 教练工作台:多对话隔离 + @引用随时注入场次/prompt + 建议应用到 prompt。
 * 形态对标 ZCode:对话是工作单元,聊天中途 @#26 / @prompt:xxx 随时加上下文。 */
import { Button, Input, Modal, Radio, Segmented, Select, Spin, Typography, message } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, post, put } from '../api/client'
import { inferRunStage, stageLabel } from '../lib/system'
import { useSystemLabel } from '../lib/useSystems'

interface ChatMessage { role: 'user' | 'assistant', content: string }

/** 用户消息剥离注入前缀(档案/背景),只显示说的话;@引用渲染成 chip */
function UserText({ content }: { content: string }) {
  const i = content.lastIndexOf('\n用户: ')
  const text = i >= 0 ? content.slice(i + 5) : content
  const parts = text.split(/(@#\d+|@prompt:[A-Za-z0-9_\u4e00-\u9fff-]+)/g)
  return <span style={{ fontSize: 14, lineHeight: 1.6 }}>
    {parts.map((p, i) =>
      /^@(#\d+|prompt:[\w\u4e00-\u9fff-]+)$/.test(p)
        ? <span key={i} style={{ background: 'rgba(255,255,255,.25)', borderRadius: 4, padding: '0 4px', fontWeight: 600 }}>{p}</span>
        : <span key={i}>{p}</span>)}
  </span>
}

/** 从 AI 回复中提取建议代码块 */
function extractSuggestions(text: string): string[] {
  const blocks: string[] = []
  const regex = /```(?:prompt|markdown|md)?\s*\n([\s\S]*?)```/g
  let m
  while ((m = regex.exec(text)) !== null)
    if (m[1].trim().length > 30) blocks.push(m[1].trim())
  return blocks
}

/** @候选条目:该系统的场次 + prompts */
function useRefCandidates(system: string) {
  const runs = useQuery({
    queryKey: ['systemRuns', system],
    queryFn: () => get(`/runs?system=${encodeURIComponent(system)}`),
    staleTime: 60_000,
  })
  const prompts = useQuery({
    queryKey: ['prompts', system],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/prompts`),
    staleTime: 60_000,
  })
  return useMemo(() => {
    const items: { insert: string, label: string, hint: string }[] = []
    for (const p of (prompts.data ?? []) as any[])
      items.push({ insert: `@prompt:${p.prompt} `, label: `📄 ${p.stage === '(system)' ? '系统设定' : p.stage}`,
                   hint: p.prompt })
    for (const r of (runs.data ?? []) as any[]) {
      const st = inferRunStage(r, system)
      items.push({
        insert: `@#${r.id} `,
        label: `#️⃣ #${r.id} ${r.slug}`,
        hint: `${r.kind} ${r.trade_date}${st ? ' · ' + stageLabel(st) : ''}${r.metrics ? ` · ${r.metrics.return_pct}%` : ''}`,
      })
    }
    return items
  }, [runs.data, prompts.data, system])
}

export default function Coach() {
  const { name = '' } = useParams()
  const system = name
  const sysLabel = useSystemLabel()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()

  const [convId, setConvId] = useState<number | null>(null)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [mention, setMention] = useState<{ query: string, start: number } | null>(null)
  const [applyTarget, setApplyTarget] = useState<string | null>(null)
  const [applyPrompt, setApplyPrompt] = useState('')
  const [applyMode, setApplyMode] = useState<'replace' | 'append'>('append')
  const [showArchived, setShowArchived] = useState(false)
  const [draft, setDraft] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<any>(null)
  const candidates = useRefCandidates(system)

  const convs = useQuery({
    queryKey: ['coachConvs', system, showArchived],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/coach/conversations?archived=${showArchived}`),
  })
  const conv = useQuery({
    queryKey: ['coachConv', system, convId],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/coach/conversations/${convId}`),
    enabled: convId != null,
  })

  const startDraft = useCallback((preset = '') => {
    setShowArchived(false)
    setConvId(null)
    setDraft(true)
    setMessages([])
    setInput(preset)
    setMention(null)
    requestAnimationFrame(() => taRef.current?.focus())
  }, [])

  // 空白编辑器只是本地草稿；用户发出首条消息后才创建持久化对话。
  const paramKey = params.toString()
  const runPreset = params.get('runs')
  const promptPreset = params.get('prompt')
  const requestNew = params.has('new')
  useEffect(() => {
    const preset = [
      ...(runPreset ? runPreset.split(',').map(id => `@#${id}`) : []),
      ...(promptPreset ? [`@prompt:${promptPreset}`] : []),
    ].join(' ') + ((runPreset || promptPreset) ? ' ' : '')
    if (requestNew || preset) {
      startDraft(preset)
      if (paramKey) setParams({}, { replace: true })
      return
    }
    if (draft || convId != null || !convs.isSuccess) return
    const rows = convs.data ?? []
    if (rows.length) setConvId(rows[0].id)
    else if (!showArchived) startDraft()
  }, [convs.isSuccess, convs.data, convId, draft, paramKey, promptPreset,
      requestNew, runPreset, setParams, showArchived, startDraft])

  useEffect(() => {
    if (conv.data?.messages) setMessages(conv.data.messages)
  }, [conv.data])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  /** 输入变化:检测光标前的 @ 触发候选浮层 */
  function onInput(e: any) {
    const v = e.target.value
    setInput(v)
    const pos = e.target.selectionStart ?? v.length
    const upto = v.slice(0, pos)
    const m = upto.match(/@([^\s@]*)$/)
    if (m) setMention({ query: m[1], start: pos - m[0].length })
    else setMention(null)
  }

  function pickCandidate(c: { insert: string }) {
    if (!mention) return
    const before = input.slice(0, mention.start)
    const after = input.slice(mention.start + mention.query.length + 1)
    const next = before + c.insert + after
    setInput(next)
    setMention(null)
    requestAnimationFrame(() => {
      const p = (before + c.insert).length
      taRef.current?.focus({ cursor: 'start' })
      taRef.current?.resizeTextarea?.()
      const el = taRef.current?.resizableTextArea?.textArea
      el?.setSelectionRange(p, p)
    })
  }

  const filtered = mention
    ? candidates.filter(c =>
        c.label.toLowerCase().includes(mention.query.toLowerCase()) ||
        c.hint.toLowerCase().includes(mention.query.toLowerCase())).slice(0, 8)
    : []

  async function send() {
    const text = input.trim()
    if (!text || sending || selectedArchived || (convId == null && !draft)) return
    const wasDraft = draft || convId == null
    const targetId = wasDraft ? 0 : convId
    setInput('')
    setMention(null)
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content: text }])
    try {
      const r = await post<{ id: number, reply: string, title?: string }>(
        `/systems/${encodeURIComponent(system)}/coach/conversations/${targetId}`, { message: text })
      if (wasDraft) {
        setConvId(r.id)
        setDraft(false)
      }
      setMessages(prev => [...prev, { role: 'assistant', content: r.reply }])
      if (wasDraft || r.title) qc.invalidateQueries({ queryKey: ['coachConvs', system] })
    } catch (e: any) {
      message.error(e.message)
      setMessages(prev => prev.slice(0, -1))
      setInput(text)
    } finally {
      setSending(false)
    }
  }

  async function handleApply() {
    if (!applyPrompt || !applyTarget) return
    try {
      let content = applyTarget
      if (applyMode === 'append') {
        const stamp = dayjs().format('YYYY-MM-DD')
        content = (currentContent.data ?? '').trimEnd()
          + `\n\n<!-- ── 复盘教练建议追加 ${stamp} ──>\n\n` + applyTarget
      }
      const r = await put(`/systems/${encodeURIComponent(system)}/prompts/${applyPrompt}`, { content })
      message.success(`已保存为 v${r.version},下次运行生效`)
      setApplyTarget(null)
      qc.invalidateQueries({ queryKey: ['prompts', system] })
    } catch (e: any) { message.error(e.message) }
  }

  const currentContent = useQuery({
    queryKey: ['promptContent', system, applyPrompt],
    queryFn: async () => {
      if (!applyPrompt) return ''
      const vs = await get(`/systems/${encodeURIComponent(system)}/prompts/${applyPrompt}/versions`)
      if (!vs.length) return ''
      const r = await get(`/systems/${encodeURIComponent(system)}/prompts/${applyPrompt}/versions/${vs[0].version}`)
      return r.content
    },
    enabled: !!applyTarget && !!applyPrompt,
  })

  const promptCandidates = candidates.filter(c => c.insert.startsWith('@prompt:'))
  const runCandidates = candidates.filter(c => c.insert.startsWith('@#'))
  const addReference = (insert: string) => {
    setInput(v => `${v}${v && !v.endsWith(' ') ? ' ' : ''}${insert}`)
    requestAnimationFrame(() => taRef.current?.focus())
  }
  const selectedArchived = !draft && !!conv.data?.archived

  async function setArchived(id: number, archived: boolean) {
    try {
      await post(`/systems/${encodeURIComponent(system)}/coach/conversations/${id}/archive`, { archived })
      qc.setQueryData(['coachConv', system, id], (current: any) =>
        current ? { ...current, archived } : current)
      message.success(archived ? '对话已归档' : '对话已恢复')
      await qc.invalidateQueries({ queryKey: ['coachConvs', system] })
      if (id === convId) {
        setDraft(false)
        setShowArchived(archived)
        setConvId(id)
      }
    } catch (e: any) { message.error(e.message) }
  }

  return (
    <div className="coach-layout">
      {/* 左栏:对话列表 + 可点击上下文。 */}
      <aside className="coach-side">
        <Button type="primary" block onClick={() => startDraft()}>＋ 新开对话</Button>
        <div className="stg-group" style={{ marginTop: 10 }}>对话 · {sysLabel(system)}</div>
        <Segmented block size="small" value={showArchived ? 'archived' : 'active'}
          onChange={(value) => {
            setShowArchived(value === 'archived'); setConvId(null); setDraft(false); setMessages([])
          }}
          options={[{ label: '进行中', value: 'active' }, { label: '已归档', value: 'archived' }]} />
        <div className="coach-conv-list">
          {(convs.data ?? []).map((c: any) => (
            <div key={c.id}
                 className={`stg-item${c.id === convId ? ' active' : ''}`}
                 onClick={() => { setDraft(false); setConvId(c.id); setMessages([]) }}>
              <span className="stg-icon">💬</span>
              <span className="stg-label" title={c.title}>{c.title}</span>
              <button className="coach-archive-action"
                      title={c.archived ? '恢复对话' : '归档对话'}
                      aria-label={`${c.archived ? '恢复' : '归档'} ${c.title}`}
                      onClick={e => { e.stopPropagation(); setArchived(c.id, !c.archived) }}>
                <span className="coach-archive-glyph" aria-hidden="true">
                  {c.archived ? '↑' : '↓'}
                </span>
              </button>
            </div>
          ))}
          {convs.isSuccess && !(convs.data ?? []).length && (
            <Typography.Text type="secondary" style={{ fontSize: 12, padding: 8, display: 'block' }}>
              {showArchived ? '没有已归档的对话' : '还没有对话'}
            </Typography.Text>)}
        </div>
        <div className="stg-group">当前上下文</div>
        <div className="coach-context-list">
          {promptCandidates.slice(0, 5).map(c => (
            <button key={c.insert} className="coach-context-item" onClick={() => addReference(c.insert)}>
              <span>{c.label}</span><small>{c.hint}</small>
            </button>
          ))}
          {runCandidates.slice(0, 5).map(c => (
            <button key={c.insert} className="coach-context-item" onClick={() => addReference(c.insert)}>
              <span>{c.label}</span><small>{c.hint}</small>
            </button>
          ))}
          {!candidates.length && <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无可引用内容</Typography.Text>}
        </div>
      </aside>

      {/* 右侧:当前对话 */}
      <div className="coach-main">
        {convId == null && !draft ? (
          <div className="coach-loading"><Typography.Text type="secondary">选择一段对话</Typography.Text></div>
        ) : (
          <>
            <div className="coach-chat-head">
              <div><b>教练</b><span>系统进化讨论</span></div>
              <span className="st-badge st-neutral">
                {draft ? '新对话' : `${selectedArchived ? '已归档 · ' : ''}对话 #${convId}`}
              </span>
            </div>
            <div className="coach-msgs">
              {!messages.length && !sending && (
                <div className="coach-starters">
                  <button onClick={() => setInput(runCandidates[0]
                    ? `${runCandidates[0].insert} 复盘这场执行，区分指令问题和执行问题。`
                    : '检查当前系统的指令结构，指出最值得先验证的一处。')}>复盘最近场次</button>
                  <button onClick={() => setInput(promptCandidates[0]
                    ? `${promptCandidates[0].insert} 审查这条指令，给出可验证的改进建议。`
                    : '从风险约束和证据闭环两方面检查当前系统。')}>审查当前指令</button>
                </div>
              )}
              {messages.map((msg, i) => {
                const sugg = msg.role === 'assistant' ? extractSuggestions(msg.content) : []
                return (
                  <div key={i} style={{ marginBottom: 14, display: 'flex',
                                        justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <div className={`coach-bubble ${msg.role}`}>
                      {msg.role === 'user'
                        ? <UserText content={msg.content} />
                        : <>
                            <div className="markdown-body" style={{ fontSize: 14 }}>
                              <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                            </div>
                            {sugg.length > 0 && (
                              <Button size="small" type="primary" ghost style={{ marginTop: 8 }}
                                      onClick={() => setApplyTarget(sugg.join('\n\n---\n\n'))}>
                                📝 应用建议到 prompt({sugg.length} 条)
                              </Button>)}
                          </>}
                    </div>
                  </div>
                )
              })}
              {sending && (
                <div style={{ textAlign: 'center', padding: 12 }}>
                  <Spin size="small" /> <Typography.Text type="secondary">教练思考中…</Typography.Text>
                </div>)}
              <div ref={bottomRef} />
            </div>

            {/* 输入区:@ 候选浮层 + TextArea */}
            <div className="coach-input">
              {mention && filtered.length > 0 && (
                <div className="mention-pop">
                  {filtered.map((c, i) => (
                    <div key={i} className="mention-item" onClick={() => pickCandidate(c)}>
                      <b>{c.label}</b>
                      <span style={{ color: 'var(--text-3)', marginLeft: 8, fontSize: 11 }}>{c.hint}</span>
                    </div>
                  ))}
                </div>)}
              <Input.TextArea ref={taRef} rows={3} value={input}
                onChange={onInput}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !mention) { e.preventDefault(); send() }
                }}
                placeholder="输入问题，@ 可引用场次或指令"
                disabled={sending || selectedArchived} />
              <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <Button onClick={() => nav(`/systems/${encodeURIComponent(system)}`)}>📊 去看履历</Button>
                <Button type="primary" onClick={send} loading={sending}
                        disabled={!input.trim() || selectedArchived}>发送</Button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* 应用建议弹窗(追加/替换) */}
      <Modal title="应用建议到 prompt" open={!!applyTarget} onCancel={() => setApplyTarget(null)}
             onOk={handleApply} okText="保存为新版本" width={720}
             okButtonProps={{ disabled: !applyPrompt }}>
        <Radio.Group value={applyMode} onChange={(e) => setApplyMode(e.target.value)}
                     optionType="button" size="small" style={{ marginBottom: 12 }}>
          <Radio.Button value="append">➕ 追加到末尾(片段类建议,安全)</Radio.Button>
          <Radio.Button value="replace">🔄 完全替换(教练给了完整版时用)</Radio.Button>
        </Radio.Group>
        <Select style={{ width: '100%', marginBottom: 12 }} value={applyPrompt || undefined}
                onChange={setApplyPrompt} placeholder="选择要更新的 prompt"
                options={(candidates ?? [])
                  .filter((c: any) => c.insert.startsWith('@prompt:'))
                  .map((c: any) => ({ value: c.hint, label: `${c.label} (${c.hint})` }))} />
        <div style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>当前版本</Typography.Text>
            <pre style={preStyle}>{(currentContent.data ?? '').slice(0, 1500)}</pre>
          </div>
          <div style={{ flex: 1 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12, color: '#1677ff' }}>
              AI 建议({applyMode === 'append' ? '将追加到末尾' : '将替换全文'})
            </Typography.Text>
            <pre style={{ ...preStyle, background: '#f0f7ff', borderColor: '#91caff' }}>
              {(applyTarget ?? '').slice(0, 1500)}
            </pre>
          </div>
        </div>
      </Modal>
    </div>
  )
}

const preStyle: React.CSSProperties = {
  padding: 10, borderRadius: 6, border: '1px solid #d9d9d9',
  fontSize: 11, maxHeight: 300, overflow: 'auto',
  whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
  fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
}
