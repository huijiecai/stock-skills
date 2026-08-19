import { Select, Input, Button, message, Space, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { get, put } from '../api/client'

/** Prompt 在线编辑器:选 stage → 载入某版 → 编辑保存新版本 / 切版本回看。
 *  版本库能力前端化;md 编辑面在此退役(实现设计附录 8)。 */
export default function PromptEditor({ system }: { system: string }) {
  const qc = useQueryClient()
  const prompts = useQuery({ queryKey: ['prompts', system], queryFn: () => get(`/systems/${system}/prompts`) })
  const [prompt, setPrompt] = useState('')
  const [content, setContent] = useState('')
  const [version, setVersion] = useState<number | null>(null)
  const [versions, setVersions] = useState<any[]>([])

  useEffect(() => {
    if (prompts.data?.length && !prompt) load(prompts.data[0].prompt)
  }, [prompts.data])

  async function load(p: string) {
    setPrompt(p)
    const vs = await get(`/systems/${system}/prompts/${p}/versions`)
    setVersions(vs)
    if (vs.length) loadVersion(p, vs[0].version)
  }

  async function loadVersion(p: string, v: number) {
    const r = await get(`/systems/${system}/prompts/${p}/versions/${v}`)
    setContent(r.content)
    setVersion(v)
  }

  async function save() {
    const r = await put(`/systems/${system}/prompts/${prompt}`, { content })
    message.success(r.changed ? `已保存 v${r.version}` : '内容未变,无新版本')
    load(prompt)
    qc.invalidateQueries({ queryKey: ['prompts', system] })
  }

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Select style={{ width: 260 }} value={prompt} onChange={load}
                options={(prompts.data ?? []).map((x: any) => ({
                  value: x.prompt, label: `${x.stage} → ${x.prompt}${x.latest_version ? ` (v${x.latest_version})` : ''}`,
                }))} />
        <Select style={{ width: 130 }} value={version} onChange={(v) => loadVersion(prompt, v)}
                options={versions.map((v: any) => ({ value: v.version, label: `v${v.version}` }))} />
        <Button type="primary" onClick={save} disabled={!version}>保存为新版本</Button>
      </Space>
      <Input.TextArea rows={20} value={content} onChange={(e) => setContent(e.target.value)}
                      className="mono" style={{ fontSize: 12 }} />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        切版本=回看/回滚起点,保存=固化新版本;旧版永在版本库,新版本即刻生效于下一场。
      </Typography.Text>
    </div>
  )
}
