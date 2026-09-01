/** T3.3 页面范式组件单测:PageState 三态、StatusBadge/RunStatusBadge 徽章、ConfirmAction 确认。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PageState, StatusBadge, RunStatusBadge, ConfirmAction } from './ui'

// jsdom 无 ResizeObserver,Popconfirm 气泡定位依赖它
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  unobserve() {}
  disconnect() {}
})

function mount(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

describe('PageState(区块三态)', () => {
  it('loading → 居中 Spin,不渲染 children', () => {
    mount(<PageState query={{ isLoading: true }}>内容</PageState>)
    expect(document.querySelector('.ant-spin')).toBeTruthy()
    expect(screen.queryByText('内容')).toBeNull()
  })

  it('error → 红字展示 message', () => {
    mount(<PageState query={{ error: new Error('连接被拒') }}>内容</PageState>)
    expect(screen.getByText('连接被拒')).toBeTruthy()
    expect(screen.queryByText('内容')).toBeNull()
  })

  it('empty → 空态文案;正常 → children', () => {
    const { rerender } = mount(
      <PageState query={{}} empty emptyText="还没有文档">内容</PageState>)
    expect(screen.getByText('还没有文档')).toBeTruthy()
    rerender(<PageState query={{}}>内容</PageState>)
    expect(screen.getByText('内容')).toBeTruthy()
  })

  it('显式 loading/error 覆盖 query(多 query 合并场景)', () => {
    mount(<PageState query={{}} loading error={new Error('boom')}>内容</PageState>)
    // loading 优先于 error(三态短路顺序)
    expect(document.querySelector('.ant-spin')).toBeTruthy()
    expect(screen.queryByText('boom')).toBeNull()
  })
})

describe('StatusBadge/RunStatusBadge(状态徽章)', () => {
  it('tone → 语义类;pulse → 呼吸点', () => {
    render(<StatusBadge tone="ok">已封场</StatusBadge>)
    expect(document.querySelector('.st-badge.st-ok')).toBeTruthy()
    expect(document.querySelector('.rd-live')).toBeNull()

    render(<StatusBadge tone="live" pulse>运行中</StatusBadge>)
    expect(document.querySelector('.st-badge.st-live .rd-live')).toBeTruthy()
  })

  it('RunStatusBadge:running/sealed/stopping 三态', () => {
    const { rerender } = render(<RunStatusBadge r={{ status: 'running', heartbeat_at: new Date().toISOString() }} />)
    expect(document.querySelector('.st-badge.st-run')).toBeTruthy()
    expect(screen.getByText('运行中')).toBeTruthy()

    rerender(<RunStatusBadge r={{ status: 'sealed' }} />)
    expect(document.querySelector('.st-badge.st-ok')).toBeTruthy()

    rerender(<RunStatusBadge r={{ status: 'stopping' }} />)
    expect(screen.getByText('停止中')).toBeTruthy()
  })

  it('RunStatusBadge:心跳超时 → 疑似僵死(st-stall)', () => {
    render(<RunStatusBadge r={{ status: 'running', heartbeat_at: '2026-01-01T00:00:00Z' }} />)
    expect(document.querySelector('.st-badge.st-stall')).toBeTruthy()
    expect(screen.getByText('疑似僵死')).toBeTruthy()
  })
})

describe('ConfirmAction(确认操作)', () => {
  it('确认后触发 onConfirm', async () => {
    const onConfirm = vi.fn()
    mount(
      <ConfirmAction title="停止 #489?" description="当前轮完成后封场退出"
                     danger okText="停止" onConfirm={onConfirm}>
        <a>停止</a>
      </ConfirmAction>)
    await userEvent.click(screen.getByText('停止'))
    const okBtn = await waitFor(() => {
      const btn = document.querySelector('.ant-popover .ant-btn-primary')
      expect(btn).toBeTruthy()
      return btn as HTMLElement
    })
    await userEvent.click(okBtn)
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1))
  })
})
