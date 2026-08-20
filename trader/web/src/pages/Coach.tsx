/** 教练工作台:多对话隔离 + @引用随时注入场次/prompt + 建议应用到 prompt。
 * 形态对标 ZCode:对话是工作单元,聊天中途 @#26 / @prompt:xxx 随时加上下文。 */
import { Button, Empty, Input, Modal, Radio, Select, Spin, Typography, message } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
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
  const bottomRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<any>(null)
  const candidates = useRefCandidates(system)

  const convs = useQuery({
    queryKey: ['coachConvs', system],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/coach/conversations`),
  })
  const conv = useQuery({
    queryKey: ['coachConv', system, convId],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/coach/conversations/${convId}`),
    enabled: convId != null,
  })

  // URL ?new=1 → 新开对话;?runs=26 → 新开并预填引用
  useEffect(() => {
    if (convId != null || !convs.isSuccess) return
    const preset = params.get('runs')
    if (params.get('new') || preset) {
      post(`/systems/${encodeURIComponent(system)}/coach/conversations`).then(r => {
        setConvId(r.id)
        if (preset) setInput(preset.split(',').map(id => `@#${id} `).join(''))
        setParams({})
      })
    } else if ((convs.data ?? []).length) {
      setConvId(convs.data[0].id)
    }
  }, [convs.isSuccess, convs.data, convId])

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
    if (!text || sending || convId == null) return
    setInput('')
    setMention(null)
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content: text }])
    try {
      const r = await post<{ reply: string, title?: string }>(
        `/systems/${encodeURIComponent(system)}/coach/conversations/${convId}`, { message: text })
      setMessages(prev => [...prev, { role: 'assistant', content: r.reply }])
      if (r.title) qc.invalidateQueries({ queryKey: ['coachConvs', system] })
    } catch (e: any) {
      message.error(e.message)
      setMessages(prev => prev.slice(0, -1))
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

  return (
    <div className="coach-layout">
      {/* 左栏:对话列表 + @引用说明 */}
      <aside className="coach-side">
        <Button type="primary" block onClick={async () => {
          const r = await post(`/systems/${encodeURIComponent(system)}/coach/conversations`)
          setConvId(r.id); setMessages([])
          qc.invalidateQueries({ queryKey: ['coachConvs', system] })
        }}>＋ 新开对话</Button>
        <div className="stg-group" style={{ marginTop: 10 }}>对话 · {sysLabel(system)}</div>
        <div className="coach-conv-list">
          {(convs.data ?? []).map((c: any) => (
            <div key={c.id}
                 className={`stg-item${c.id === convId ? ' active' : ''}`}
                 onClick={() => { setConvId(c.id); setMessages([]) }}>
              <span className="stg-icon">💬</span>
              <span className="stg-label" title={c.title}>{c.title}</span>
            </div>
          ))}
          {convs.isSuccess && !(convs.data ?? []).length && (
            <Typography.Text type="secondary" style={{ fontSize: 12, padding: 8, display: 'block' }}>
              还没有对话——新开一个,输入 @ 引用场次或 prompt 开始讨论
            </Typography.Text>)}
        </div>
        <div className="stg-group">引用语法</div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '0 10px', lineHeight: 1.8 }}>
          聊天中随时输入 <b>@</b> 弹出候选:<br />
          <code>@#26</code> 注入场次档案<br />
          <code>@prompt:round_live</code> 注入 prompt 全文<br />
          多场对比就 @ 两场一起
        </div>
      </aside>

      {/* 右侧:当前对话 */}
      <div className="coach-main">
        {convId == null ? (
          <Empty style={{ marginTop: 80 }} description="新开一个对话开始进化讨论" />
        ) : (
          <>
            <div className="coach-msgs">
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
                placeholder="讨论…(输入 @ 引用场次/prompt,Enter 发送,Shift+Enter 换行)"
                disabled={sending} />
              <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <Button onClick={() => nav(`/systems/${encodeURIComponent(system)}/stage/live/runs`)}>📊 去看场次</Button>
                <Button type="primary" onClick={send} loading={sending} disabled={!input.trim()}>发送</Button>
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
