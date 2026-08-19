import { Input, Button, message, Typography, Tabs, Select, Space, Tag } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, put } from '../api/client'

/** 阶段图标 */
function stageIcon(stage: string): string {
  if (stage === '(system)') return '⚙️'
  if (stage.includes('live')) return '📊'
  if (stage.includes('premarket')) return '🌅'
  if (stage.includes('close')) return '🌙'
  if (stage.includes('research')) return '🔍'
  if (stage.includes('replay')) return '🔄'
  return '📄'
}

/** 阶段友好名 */
function stageLabel(stage: string): string {
  if (stage === '(system)') return '系统设定'
  return stage
}

/** Prompt 在线编辑器:阶段Tab + 版本栏 + 编辑/预览。 */
export default function PromptEditor({ system }: { system: string }) {
  const qc = useQueryClient()
  const prompts = useQuery({ queryKey: ['prompts', system], queryFn: () => get(`/systems/${system}/prompts`) })
  const [prompt, setPrompt] = useState('')
  const [content, setContent] = useState('')
  const [version, setVersion] = useState<number | null>(null)
  const [versions, setVersions] = useState<any[]>([])
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (prompts.data?.length && !prompt) load(prompts.data[0].prompt)
  }, [prompts.data])

  async function load(p: string) {
    setPrompt(p)
    setDirty(false)
    const vs = await get(`/systems/${system}/prompts/${p}/versions`)
    setVersions(vs)
    if (vs.length) loadVersion(p, vs[0].version)
  }

  async function loadVersion(p: string, v: number) {
    const r = await get(`/systems/${system}/prompts/${p}/versions/${v}`)
    setContent(r.content)
    setVersion(v)
    setDirty(false)
  }

  async function save() {
    const r = await put(`/systems/${system}/prompts/${prompt}`, { content })
    message.success(r.changed ? `已保存 v${r.version}` : '内容未变')
    setDirty(false)
    load(prompt)
    qc.invalidateQueries({ queryKey: ['prompts', system] })
  }

  const current = (prompts.data ?? []).find((p: any) => p.prompt === prompt)

  return (
    <div>
      {/* 阶段切换 Tab(替代下拉,一目了然) */}
      <Tabs
        size="small"
        activeKey={prompt}
        onChange={load}
        items={(prompts.data ?? []).map((p: any) => ({
          key: p.prompt,
          label: (
            <span>
              {stageIcon(p.stage)} {stageLabel(p.stage)}
              {p.latest_version > 1 && (
                <Tag style={{ marginLeft: 6, fontSize: 10 }} color="blue">v{p.latest_version}</Tag>
              )}
            </span>
          ),
        }))}
      />

      {/* 版本栏 */}
      <Space style={{ marginBottom: 12, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Select size="small" style={{ width: 180 }} value={version}
                  onChange={(v) => loadVersion(prompt, v)}
                  placeholder="版本"
                  options={versions.map((v: any) => ({
                    value: v.version,
                    label: `v${v.version}${v.version === versions[0]?.version ? ' (最新)' : ''}`,
                  }))} />
          {dirty && <Tag color="orange">未保存</Tag>}
        </Space>
        <Button type="primary" size="small" onClick={save} disabled={!version}>
          {dirty ? '保存修改 *' : '保存新版本'}
        </Button>
      </Space>

      {/* 编辑/预览 */}
      <Tabs size="small" items={[
        {
          key: 'edit',
          label: '✏️ 编辑',
          forceRender: true,
          children: (
            <Input.TextArea
              rows={22}
              value={content}
              onChange={(e) => { setContent(e.target.value); setDirty(true) }}
              style={{ fontSize: 12, fontFamily: 'ui-monospace, SF Mono, Menlo, monospace' }}
              placeholder={'在此编写 prompt...\n支持 {date} 等占位符(engine 运行时注入)\n支持 Markdown 语法'}
            />
          ),
        },
        {
          key: 'preview',
          label: '👁 预览',
          children: (
            <div className="markdown-body" style={{
              minHeight: 400, maxHeight: 600, overflow: 'auto',
              border: '1px solid #d9d9d9', borderRadius: 6, padding: 16, background: '#fff',
            }}>
              {content ? <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
                        : <Typography.Text type="secondary">编辑内容后此处显示预览</Typography.Text>}
            </div>
          ),
        },
      ]} />

      <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
        切版本=回看/回滚 · 保存=新版本即刻生效于下一场 · 支持 {'{date}'} {'{prev}'} {'{weekday}'} 占位符
      </Typography.Text>
    </div>
  )
}
