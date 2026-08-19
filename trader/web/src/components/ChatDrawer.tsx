import { Button, Drawer, Input, Spin, message, Typography, Tooltip } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, post } from '../api/client'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** 场次讨论抽屉:跑完后跟 AI 教练讨论结果、优化 prompt。
 *  AI 建议用代码块包裹,旁边出现"应用到 prompt"按钮。 */
export default function ChatDrawer({ runId, systemName, open, onClose }: {
  runId: number
  systemName: string
  open: boolean
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  // 加载历史对话
  const history = useQuery({
    queryKey: ['chat', runId],
    queryFn: () => get(`/runs/${runId}/chat`),
    enabled: open && !!runId,
  })

  useEffect(() => {
    if (history.data?.messages) {
      setMessages(history.data.messages)
    }
  }, [history.data])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    if (!input.trim() || sending) return
    const userMsg = input.trim()
    setInput('')
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    try {
      const r = await post<{ reply: string }>(`/runs/${runId}/chat`, { message: userMsg })
      setMessages(prev => [...prev, { role: 'assistant', content: r.reply }])
      qc.invalidateQueries({ queryKey: ['chat', runId] })
    } catch (e: any) {
      message.error(e.message)
      setMessages(prev => prev.slice(0, -1)) // 失败回滚
    } finally {
      setSending(false)
    }
  }

  // 从 AI 回复中提取代码块(作为可应用的 prompt 建议)
  function extractSuggestions(text: string): { suggestion: string; index: number }[] {
    const blocks: { suggestion: string; index: number }[] = []
    const regex = /```(?:prompt|markdown|md)?\s*\n([\s\S]*?)```/g
    let match
    let i = 0
    while ((match = regex.exec(text)) !== null) {
      if (match[1].trim().length > 20) { // 太短的不是建议
        blocks.push({ suggestion: match[1].trim(), index: i++ })
      }
    }
    return blocks
  }

  async function applySuggestion(suggestion: string) {
    // TODO: 需要知道具体的 prompt 名才能应用
    // 简化:复制到剪贴板,让用户粘贴到 PromptEditor
    try {
      await navigator.clipboard.writeText(suggestion)
      message.success('已复制到剪贴板,请到「编辑 prompts」粘贴并保存')
    } catch {
      message.info('请手动复制代码块内容')
    }
  }

  return (
    <Drawer title={`💬 讨论:${systemName}`} width={620} open={open} onClose={onClose}
            styles={{ body: { display: 'flex', flexDirection: 'column', padding: '12px 16px' } }}>
      {/* 消息列表 */}
      <div style={{ flex: 1, overflowY: 'auto', marginBottom: 12 }}>
        {messages.length === 0 && (
          <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 40 }}>
            跑完了?跟 AI 教练聊聊这次结果,<br/>让它帮你优化 prompt。<br/><br/>
            试试:"为什么没分析 X?" / "怎么改进输出格式?" / "还有什么数据源可以加?"
          </Typography.Text>
        )}
        {messages.map((msg, i) => (
          <div key={i} style={{
            marginBottom: 12,
            display: 'flex',
            justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
          }}>
            <div style={{
              maxWidth: '85%',
              padding: msg.role === 'user' ? '8px 14px' : '10px 14px',
              borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
              background: msg.role === 'user' ? '#1677ff' : '#f6f8fa',
              color: msg.role === 'user' ? '#fff' : '#333',
            }}>
              {msg.role === 'user' ? (
                <span style={{ fontSize: 14, lineHeight: 1.5 }}>{msg.content}</span>
              ) : (
                <div className="markdown-body" style={{ fontSize: 14 }}>
                  <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                  {/* 代码块旁的应用按钮 */}
                  {extractSuggestions(msg.content).map((s, j) => (
                    <Tooltip key={j} title="复制建议内容,粘贴到 prompt 编辑器">
                      <Button size="small" type="primary" ghost
                              style={{ marginTop: 4, marginBottom: 8 }}
                              onClick={() => applySuggestion(s.suggestion)}>
                        📋 应用此建议
                      </Button>
                    </Tooltip>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {sending && (
          <div style={{ textAlign: 'center', padding: 12 }}>
            <Spin size="small" /> <Typography.Text type="secondary">AI 正在思考...</Typography.Text>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div style={{ borderTop: '1px solid #e8e8e8', paddingTop: 12 }}>
        <Input.TextArea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="输入问题,Enter 发送,Shift+Enter 换行"
          disabled={sending}
        />
        <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="primary" onClick={send} loading={sending} disabled={!input.trim()}>
            发送
          </Button>
        </div>
      </div>
    </Drawer>
  )
}
