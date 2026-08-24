/** 运行弹窗(工作台头部唯一 ▶ 运行):预选当前阶段 + 重复触发预确认
 *  + 启动检测(轮询发现新场次自动跳详情)。 */
import { DatePicker, Input, message, Modal, Select, Space, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { get, post } from '../api/client'
import { stageIcon, kindLabel, stageLabel, orderedStages } from '../lib/system'

const POLL_MS = 2000, DETECT_TIMEOUT_MS = 90_000

export default function LaunchModal({ system, stages, presetStage, open, onClose }: {
  system: string
  stages: Record<string, any>
  presetStage: string        // 从工作台头部打开时预选当前阶段
  open: boolean
  onClose: () => void
}) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [stage, setStage] = useState('')
  const [date, setDate] = useState<any>(dayjs())
  const [interval, setIntervalMin] = useState(5)        // 重演:模拟时钟 分钟/轮
  const [sleepSec, setSleepSec] = useState(0)           // 实时:轮完成后休息,0=连续
  const [clock, setClock] = useState<'real' | 'simulated'>('real')   // 何时:发起时绑定
  const [promptVersion, setPromptVersion] = useState<number | 'latest'>('latest')
  const [opening, setOpening] = useState<'fresh' | 'fork' | 'fork-as-of'>('fresh')
  const [portfolioType, setPortfolioType] = useState<'main' | 'paper'>('main')
  const [instruction, setInstruction] = useState('')
  const timer = useRef<number | null>(null)
  const promptSlug = stages[stage]?.prompt ?? ''
  const versions = useQuery({
    queryKey: ['promptVersions', system, promptSlug],
    queryFn: () => get(`/systems/${encodeURIComponent(system)}/prompts/${encodeURIComponent(promptSlug)}/versions`),
    enabled: open && !!promptSlug,
  })

  useEffect(() => {
    if (open) {
      setStage(presetStage)
      if (presetStage) {
        setIntervalMin(stages[presetStage]?.interval ?? 5)
        setClock('real')
      }
      setPromptVersion('latest')
      setOpening('fresh')
      setPortfolioType('main')
      setSleepSec(0)
      setInstruction('')
      setDate(dayjs())
    }
  }, [open, presetStage, stages])

  useEffect(() => () => { if (timer.current) clearInterval(timer.current) }, [])

  function stopDetect() {
    if (timer.current) { clearInterval(timer.current); timer.current = null }
  }

  async function launch() {
    if (!stage) return
    const d = (date ?? dayjs()).format('YYYYMMDD')
    const sdef = stages[stage] ?? {}
    try {
      const before: any[] = await get(`/runs?system=${encodeURIComponent(system)}`)
      const ids = new Set(before.map(r => r.id))
      // 前端软确认:已有执行中场次先问一句(后端另有硬拦)
      const alive = before.filter(r => r.status === 'running' || r.status === 'stopping')
      const go = async () => doLaunch(d, sdef, before, ids)
      if (alive.length && sdef.kind !== 'single') {
        Modal.confirm({
          title: `已有 ${alive.length} 个执行中场次`,
          content: alive.map(r => `#${r.id} ${r.slug}(${r.status})`).join(' · ')
                   + '——重复触发会被后端拦截;single 阶段重跑出报告不受影响。',
          okText: '仍要运行', cancelText: '取消',
          onOk: go,
        })
        return
      }
      await go()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  async function doLaunch(d: string, sdef: any, before: any[], ids: Set<number>) {
    try {
      const isReal = clock === 'real'
      await post(`/systems/${encodeURIComponent(system)}/run`,
                 isReal
                   ? { date: d, stage, clock: 'real', sleep_seconds: sleepSec,
                       portfolio_type: portfolioType,
                       instruction: instruction.trim(),
                       prompt_version: promptVersion === 'latest' ? null : promptVersion }
                   : { date: d, stage, clock: 'simulated', interval, opening,
                       instruction: instruction.trim(),
                       prompt_version: promptVersion === 'latest' ? null : promptVersion })
      onClose()
      message.success('已发起')

      // 实时时钟续跑:今日同阶段场已存在 → 直接跳既有场。
      if (isReal && sdef?.kind === 'loop') {
        const today = dayjs().format('YYYYMMDD')
        const existing = before.find(r => r.clock === 'real' && r.stage === stage
          && r.trade_date === today && r.kind === (portfolioType === 'paper' ? 'paper' : 'live'))
        if (existing) {
          qc.invalidateQueries({ queryKey: ['systemRuns', system] })
          nav(`/runs/${existing.id}`)
          return
        }
      }
      // 启动检测:子进程建场有延迟,轮询发现新 id 即跳
      stopDetect()
      const deadline = Date.now() + DETECT_TIMEOUT_MS
      timer.current = window.setInterval(async () => {
        try {
          const list: any[] = await get(`/runs?system=${encodeURIComponent(system)}`)
          const fresh = list.filter(r => !ids.has(r.id))
          if (fresh.length) {
            stopDetect()
            qc.invalidateQueries({ queryKey: ['systemRuns', system] })
            nav(`/runs/${fresh[0].id}`)
          } else if (Date.now() > deadline) {
            stopDetect()
            qc.invalidateQueries({ queryKey: ['systemRuns', system] })
            message.info('已发起,建场稍有延迟——稍后在资产视图的今日执行中查看')
          }
        } catch { /* 轮询失败忽略,下一轮再试 */ }
      }, POLL_MS)
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const entries = orderedStages(stages)
  return (
    <Modal title={`运行 · ${system}`} open={open} onCancel={onClose}
           onOk={launch} okText="开始运行" width={420}
           okButtonProps={{ disabled: !stage
             || ((stages[stage]?.vars ?? []).includes('topic') && !instruction.trim())
             || (versions.isSuccess && !(versions.data ?? []).length) }}>
      <Space orientation="vertical" style={{ width: '100%' }} size={12}>
        <Select style={{ width: '100%' }} value={stage} onChange={(v) => {
          setStage(v); setIntervalMin(stages[v]?.interval ?? 5)
          setClock('real'); setPromptVersion('latest')
        }} placeholder="选择要运行的阶段"
                options={entries.map(([s, d]) => ({
                  value: s, label: `${stageIcon(s)} ${stageLabel(s, d)}(${kindLabel(s, d)})` }))} />
        {!!stage && (
          <div>
            <Typography.Text strong style={{ display: 'block', fontSize: 13, marginBottom: 5 }}>
              本次任务 / 分析对象{(stages[stage]?.vars ?? []).includes('topic') ? '' : '（可选）'}
            </Typography.Text>
            <Input.TextArea value={instruction} onChange={e => setInstruction(e.target.value)}
              placeholder="例如：分析沪电股份（002463）今天走势的原因；或分析 PCB 板块未来一周强弱"
              autoSize={{ minRows: 2, maxRows: 5 }} maxLength={4000} showCount />
          </div>
        )}
        {!!stage && (
          <Select style={{ width: '100%' }} value={clock} onChange={setClock}
                  options={[
                    { value: 'real', label: '⏰ 何时:现在(主组合)' },
                    { value: 'simulated', label: '⏪ 何时:重演某日(实验组合)' },
                  ]} />)}
        {(stages[stage]?.kind === 'single' || clock === 'simulated') && (
          <DatePicker style={{ width: '100%' }} value={date} onChange={setDate} />
        )}
        {!!promptSlug && (
          <Select style={{ width: '100%' }} value={promptVersion} onChange={setPromptVersion}
                  loading={versions.isLoading}
                  options={[
                    { value: 'latest', label: `指令版本:最新${versions.data?.[0]?.version ? ` (v${versions.data[0].version})` : ''}` },
                    ...(versions.data ?? []).map((v: any) => ({ value: v.version, label: `钉住 v${v.version} · ${(v.created_at ?? '').slice(0, 16)}` })),
                  ]} />
        )}
        {versions.isSuccess && !!promptSlug && !(versions.data ?? []).length && (
          <Typography.Text type="danger" style={{ fontSize: 12 }}>
            这条阶段指令还没有版本，请先到工作台编辑并保存 v1。
          </Typography.Text>
        )}
        {clock === 'real' && (
          <Select style={{ width: '100%' }} value={portfolioType} onChange={setPortfolioType}
                  options={[
                    { value: 'main', label: '组合:主组合(进入正式履历)' },
                    { value: 'paper', label: '组合:模拟组合(连续虚拟资金)' },
                  ]} />
        )}
        {clock === 'simulated' && (
          <Select style={{ width: '100%' }} value={opening} onChange={setOpening}
                  options={[
                    { value: 'fresh', label: '开局:fresh(初始资金 + 主组合知识)' },
                    { value: 'fork', label: '开局:fork(复制主组合当前状态)' },
                    { value: 'fork-as-of', label: '开局:fork-as-of(折叠到目标日)' },
                  ]} />
        )}
        {/* 实时:轮间隔(默认连续);重演:模拟时钟步进 */}
        {stages[stage]?.kind === 'loop' && clock === 'real' && (
          <Select style={{ width: '100%' }} value={sleepSec} onChange={setSleepSec}
                  options={[
                    { value: 0, label: '连续看盘(每轮完成立即下一轮)' },
                    { value: 30, label: '每轮后休息 30 秒' },
                    { value: 60, label: '每轮后休息 1 分钟' },
                    { value: 180, label: '每轮后休息 3 分钟' },
                    { value: 300, label: '每轮后休息 5 分钟' },
                  ]} />)}
        {stages[stage]?.kind === 'loop' && clock === 'simulated' && (
          <Select style={{ width: '100%' }} value={interval} onChange={setIntervalMin}
                  options={[1, 3, 5, 10, 15, 20, 30].map(i => ({ value: i, label: `每 ${i} 分钟一轮` }))} />)}
        {stages[stage]?.kind === 'single' && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            跑一次出报告；重演时读写实验组合，不会污染主组合。
          </Typography.Text>)}
        {stages[stage]?.kind === 'loop' && clock === 'real' && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            实时行情,15:05 自动收工;同阶段同组合今日场次会接续,随时可停止/继续</Typography.Text>)}
        {stages[stage]?.kind === 'loop' && clock === 'simulated' && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            重演当天 9:35-15:00,实验组合独立,不碰实盘</Typography.Text>)}
      </Space>
    </Modal>
  )
}
