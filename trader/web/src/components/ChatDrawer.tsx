import { Button, Drawer, Input, Spin, message, Typography, Modal, Select, Space } from "antd"
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, post, put } from '../api/client'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

/** 从 AI 回复中提取所有建议代码块 */
function extractSuggestions(text: string): string[] {
  const blocks: string[] = []
  const regex = /```(?:prompt|markdown|md)?\s*\n([\s\S]*?)```/g
  let match
  while ((match = regex.exec(text)) !== null) {
    if (match[1].trim().length > 30) { // 过滤太短的
      blocks.push(match[1].trim())
    }
  }
  return blocks
}

/** 场次讨论抽屉:跑完后跟 AI 教练讨论结果、优化 prompt。 */
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
  const [applyTarget, setApplyTarget] = useState<string | null>(null) // 要应用的建议内容
  const [applyPrompt, setApplyPrompt] = useState<string>('')            // 应用到哪个 prompt
  const bottomRef = useRef<HTMLDivElement>(null)

  const history = useQuery({
    queryKey: ['chat', runId],
    queryFn: () => get(`/runs/${runId}/chat`),
    enabled: open && !!runId,
  })

  // 该系统的 prompt 列表(应用建议时选择目标)
  const prompts = useQuery({
    queryKey: ['prompts', systemName],
    queryFn: () => get(`/systems/${systemName}/prompts`),
    enabled: open && !!systemName,
  })

  useEffect(() => {
    if (history.data?.messages) setMessages(history.data.messages)
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
      const r = await put(`/systems/${systemName}/prompts/${applyPrompt}`, { content: applyTarget })
      message.success(`已保存为 v${r.version},下次运行生效`)
      setApplyTarget(null)
      qc.invalidateQueries({ queryKey: ['prompts', systemName] })
    } catch (e: any) { message.error(e.message) }
  }

  // 当前选中 prompt 的现有内容(对比用)
  const currentContent = useQuery({
    queryKey: ['promptContent', systemName, applyPrompt],
    queryFn: async () => {
      if (!applyPrompt) return ''
      const vs = await get(`/systems/${systemName}/prompts/${applyPrompt}/versions`)
      if (!vs.length) return ''
      const r = await get(`/systems/${systemName}/prompts/${applyPrompt}/versions/${vs[0].version}`)
      return r.content
    },
    enabled: !!applyTarget && !!applyPrompt,
  })

  return (
    <>
      <Drawer title={`💬 讨论:${systemName}`} width={620} open={open} onClose={onClose}
              styles={{ body: { display: 'flex', flexDirection: 'column', padding: '12px 16px' } }}>
        <div style={{ flex: 1, overflowY: 'auto', marginBottom: 12 }}>
          {messages.length === 0 && (
            <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 40 }}>
              跑完了?跟 AI 教练聊聊这次结果,<br/>让它帮你优化 prompt。<br/><br/>
              试试:"为什么没分析 X?" / "怎么改进输出格式?"
            </Typography.Text>
          )}
          {messages.map((msg, i) => {
            const suggestions = msg.role === 'assistant' ? extractSuggestions(msg.content) : []
            return (
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
                    <>
                      <div className="markdown-body" style={{ fontSize: 14 }}>
                        <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                      </div>
                      {/* 单个应用按钮(仅当有建议代码块时) */}
                      {suggestions.length > 0 && (
                        <Button size="small" type="primary" ghost
                                style={{ marginTop: 8 }}
                                onClick={() => {
                                  setApplyTarget(suggestions.join('\n\n---\n\n'))
                                  // 默认选第一个非 system prompt
                                  const first = (prompts.data ?? []).find((p: any) => p.stage !== '(system)')
                                  setApplyPrompt(first?.prompt ?? '')
                                }}>
                          📝 应用建议到 prompt({suggestions.length} 条)
                        </Button>
                      )}
                    </>
                  )}
                </div>
              </div>
            )
          })}
          {sending && (
            <div style={{ textAlign: 'center', padding: 12 }}>
              <Spin size="small" /> <Typography.Text type="secondary">AI 正在思考...</Typography.Text>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div style={{ borderTop: '1px solid #e8e8e8', paddingTop: 12 }}>
          <Input.TextArea rows={2} value={input} onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="输入问题,Enter 发送" disabled={sending} />
          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end' }}>
            <Button type="primary" onClick={send} loading={sending} disabled={!input.trim()}>发送</Button>
          </div>
        </div>
      </Drawer>

      {/* 应用建议弹窗 */}
      <Modal title="应用建议到 prompt" open={!!applyTarget} onCancel={() => setApplyTarget(null)}
             onOk={handleApply} okText="保存为新版本" width={720}
             okButtonProps={{ disabled: !applyPrompt }}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Select style={{ width: '100%' }} value={applyPrompt} onChange={setApplyPrompt}
                  placeholder="选择要更新的 prompt"
                  options={(prompts.data ?? []).map((p: any) => ({
                    value: p.prompt,
                    label: `${p.stage} → ${p.prompt}${p.latest_version ? ` (当前 v${p.latest_version})` : ''}`,
                  }))} />
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>当前版本</Typography.Text>
              <pre style={{ ...preStyle, background: '#fff' }}>
                {(currentContent.data ?? '').slice(0, 1500)}
              </pre>
            </div>
            <div style={{ flex: 1 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12, color: '#1677ff' }}>AI 建议(将替换)</Typography.Text>
              <pre style={{ ...preStyle, background: '#f0f7ff', borderColor: '#91caff' }}>
                {(applyTarget ?? '').slice(0, 1500)}
              </pre>
            </div>
          </div>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            ⚠ 建议内容将完全替换当前 prompt。如果有多个建议,已合并(--- 分隔)。旧版永在版本库可回滚。
          </Typography.Text>
        </Space>
      </Modal>
    </>
  )
}

const preStyle: React.CSSProperties = {
  padding: 10, borderRadius: 6, border: '1px solid #d9d9d9',
  fontSize: 11, maxHeight: 300, overflow: 'auto',
  whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
  fontFamily: 'ui-monospace, SF Mono, Menlo, monospace',
}
