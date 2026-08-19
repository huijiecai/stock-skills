import { Select, Input, Button, message, Space, Typography, Tabs, Tooltip } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { get, put } from '../api/client'

/** Prompt 在线编辑器:选 stage → 载入某版 → 编辑/预览切换 → 保存新版本。
 *  版本库能力前端化;md 编辑面在此退役(实现设计附录 8)。 */
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
    message.success(r.changed ? `已保存 v${r.version}` : '内容未变,无新版本')
    setDirty(false)
    load(prompt)
    qc.invalidateQueries({ queryKey: ['prompts', system] })
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select style={{ width: 260 }} value={prompt} onChange={load}
                placeholder="选择 prompt" loading={prompts.isLoading}
                options={(prompts.data ?? []).map((x: any) => ({
                  value: x.prompt, label: `${x.stage} → ${x.prompt}${x.latest_version ? ` (v${x.latest_version})` : ''}`,
                }))} />
        <Select style={{ width: 120 }} value={version}
                onChange={(v) => loadVersion(prompt, v)}
                placeholder="版本"
                options={versions.map((v: any) => ({ value: v.version, label: `v${v.version}` }))} />
        <Tooltip title={dirty ? '有未保存的修改' : '保存为新版本(旧版永在版本库)'}>
          <Button type="primary" onClick={save} disabled={!version}>
            {dirty ? '保存修改 *' : '保存新版本'}
          </Button>
        </Tooltip>
      </Space>

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
              className="mono"
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
              border: '1px solid #d9d9d9', borderRadius: 6, padding: 16,
              background: '#fff',
            }}>
              {content ? <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
                        : <Typography.Text type="secondary">编辑内容后此处显示 Markdown 预览</Typography.Text>}
            </div>
          ),
        },
      ]} />

      <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 8, display: 'block' }}>
        切版本=回看/回滚起点,保存=固化新版本;旧版永在版本库,新版本即刻生效于下一场。
        支持 {'{date}'} {'{prev}'} {'{weekday}'} 等占位符。
      </Typography.Text>
    </div>
  )
}
