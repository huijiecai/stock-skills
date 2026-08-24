/** ToolPanel:工具目录面板——分组渲染、领域工具过滤、试运行调 call 端点。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ToolPanel from './ToolPanel'
import { get, post } from '../../api/client'

vi.mock('../../api/client', () => ({ get: vi.fn(), post: vi.fn() }))

const CATALOG = {
  tools: [
    { name: 'get_quotes', group: 'market', write: false, desc: '查多只股票报价',
      doc: '查多只股票报价。', params: [
        { name: 'codes', type: 'list[str]', required: true, default: null },
        { name: 'mode', type: 'str', required: false, default: 'live' }] },
    { name: 'execute', group: 'trading', write: true, desc: '下单', doc: '下单', params: [] },
  ],
  portfolios: [{ id: 107, name: '纸面', type: 'paper', has_positions: true }],
  test_user: { id: 3, display_name: 'API测试' },
}

function mount(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => {
  vi.mocked(get).mockReset()
  vi.mocked(post).mockReset()
  vi.mocked(get).mockResolvedValue(CATALOG)
})

/** 分组默认收起(用户偏好):断言工具内容前先点分组头展开 */
async function expandGroup(name: RegExp) {
  await userEvent.click(await screen.findByText(name))
}

describe('ToolPanel(工具面板)', () => {
  it('默认收起,分组头可展开;渲染目录与写标记', async () => {
    mount(<ToolPanel onInsert={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/行情/)).toBeTruthy())
    expect(screen.queryByText('get_quotes')).toBeNull()          // 未展开不渲染
    await expandGroup(/行情/)
    expect(screen.getByText('get_quotes')).toBeTruthy()
    expect(screen.getByText('查多只股票报价')).toBeTruthy()
    await expandGroup(/交易/)
    expect(screen.getByText('写')).toBeTruthy()
  })

  it('不再按系统白名单置灰，领域工具均可试运行', async () => {
    mount(<ToolPanel enabled={['get_quotes']} onInsert={vi.fn()} />)
    await expandGroup(/行情/)
    await expandGroup(/交易/)
    const btns = screen.getAllByText('▶ 试运行')
    expect(btns[0].closest('button')?.disabled).toBe(false)   // 行情工具可试运行
    expect(btns[1].closest('button')?.disabled).toBe(false)   // execute 由系统策略控制
  })

  it('试运行:提交表单参数 → 展示返回(即 LLM 看到的内容)', async () => {
    vi.mocked(post).mockResolvedValue({
      name: 'get_quotes', output: '【报价】000021 深科技 12.34', truncated: false, write_warning: null })
    mount(<ToolPanel onInsert={vi.fn()} />)
    await expandGroup(/行情/)
    await userEvent.click(screen.getAllByText('▶ 试运行')[0])
    await waitFor(() => expect(screen.getByText(/000021 深科技/)).toBeTruthy())
    expect(vi.mocked(post)).toHaveBeenCalledWith('/tools/get_quotes/call',
      { args: { codes: '', mode: 'live' }, portfolio_id: 107 })
  })

  it('插入说明:onInsert 收到工具文档行', async () => {
    const onInsert = vi.fn()
    mount(<ToolPanel onInsert={onInsert} />)
    await expandGroup(/行情/)
    await userEvent.click(screen.getAllByText('插入说明')[0])
    expect(onInsert).toHaveBeenCalledWith(
      expect.stringContaining('- get_quotes(codes, mode?): 查多只股票报价'))
  })
})
