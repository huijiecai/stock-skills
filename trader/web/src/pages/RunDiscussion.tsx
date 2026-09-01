import { Button, Input, message, Modal, Spin, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, post } from '../api/client'
import type { ChatHistory, ChatMessage, ChatReplyOut, RunRow } from '../api/types'
import { stageLabel } from '../lib/system'
import { StatusBadge } from '../lib/ui'

type DiscussionMessage = ChatMessage

export default function RunDiscussion({ run, open, onClose }: {
  run: RunRow
  open: boolean
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [pendingMessages, setPendingMessages] = useState<DiscussionMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const discussion = useQuery({
    queryKey: ['runDiscussion', run.id],
    queryFn: () => get<ChatHistory>(`/runs/${run.id}/chat`),
    enabled: open,
  })

  const messages: DiscussionMessage[] = [
    ...((discussion.data?.messages ?? []) as DiscussionMessage[]),
    ...pendingMessages,
  ]

  useEffect(() => {
    if (open) requestAnimationFrame(() => bottomRef.current?.scrollIntoView())
  }, [discussion.data?.messages?.length, open, pendingMessages.length, sending])

  async function send(preset?: string) {
    const text = (preset ?? input).trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    setPendingMessages([{ role: 'user', content: text }])
    try {
      const result = await post<ChatReplyOut>(`/runs/${run.id}/chat`, { message: text })
      qc.setQueryData(['runDiscussion', run.id], (current: ChatHistory | undefined) => ({
        ...(current ?? {}),
        messages: [...((current?.messages ?? []) as DiscussionMessage[]),
          { role: 'user', content: text }, { role: 'assistant', content: result.reply }],
      }))
      setPendingMessages([])
    } catch (error: any) {
      setPendingMessages([])
      setInput(text)
      message.error(error.message)
    } finally {
      setSending(false)
    }
  }

  const starters = [
    '解释这次结论最关键的三条依据。',
    '结论里哪些部分最不确定？',
    '什么条件出现时，这次结论会失效？',
  ]

  return (
    <Modal open={open} onCancel={onClose} footer={null} width={760}
           title={`继续讨论 · Run #${run.id}`} destroyOnHidden>
      <div className="run-discussion-anchor">
        <StatusBadge>冻结上下文</StatusBadge>
        <span>{run.trade_date || '-'}</span>
        <span>{stageLabel(run.stage, run.stage_contract)}</span>
        <Typography.Text type="secondary">只澄清本场结论</Typography.Text>
      </div>

      <div className="run-discussion-messages">
        {discussion.isLoading && !messages.length ? (
          <div className="run-discussion-empty"><Spin size="small" /> 正在恢复本场上下文…</div>
        ) : discussion.error ? (
          <div className="run-discussion-empty">
            <Typography.Text type="danger">{(discussion.error as Error).message}</Typography.Text>
          </div>
        ) : !messages.length && !sending ? (
          <div className="run-discussion-starters">
            {starters.map(text => <button key={text} onClick={() => send(text)}>{text}</button>)}
          </div>
        ) : messages.map((item, index) => (
          <div key={index} className={`run-discussion-row ${item.role}`}>
            <div className={`coach-bubble ${item.role}`}>
              {item.role === 'assistant' ? (
                <div className="markdown-body" style={{ fontSize: 14 }}>
                  <Markdown remarkPlugins={[remarkGfm]}>{item.content}</Markdown>
                </div>
              ) : item.content}
            </div>
          </div>
        ))}
        {sending && <div className="run-discussion-thinking"><Spin size="small" /> 正在结合本场证据…</div>}
        <div ref={bottomRef} />
      </div>

      <div className="run-discussion-input">
        <Input.TextArea value={input} onChange={event => setInput(event.target.value)}
          autoSize={{ minRows: 2, maxRows: 5 }} maxLength={4000}
          placeholder="追问这次结论…"
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              send()
            }
          }} />
        <Button type="primary" onClick={() => send()} loading={sending} disabled={!input.trim()}>
          发送
        </Button>
      </div>
    </Modal>
  )
}
