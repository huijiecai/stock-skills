/** VarsPanel:变量契约面板——渲染契约、点击插入 {name}。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import VarsPanel from './VarsPanel'
import { get } from '../../api/client'

vi.mock('../../api/client', () => ({ get: vi.fn() }))

function mount(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

beforeEach(() => vi.mocked(get).mockReset())

describe('VarsPanel(变量面板)', () => {
  it('渲染契约变量(名称/说明/来源),点击在光标处插入 {name}', async () => {
    vi.mocked(get).mockResolvedValue({ kind: 'single', vars: [
      { name: 'date', desc: '目标交易日', example: '20260824', source: 'caller', value: null },
      { name: 'prev', desc: '上一交易日(自动推算)', example: '20260821', source: 'auto', value: null },
    ] })
    const onInsert = vi.fn()
    mount(<VarsPanel system="expectation" stage="premarket" onInsert={onInsert} />)
    await waitFor(() => expect(screen.getByText('{date}')).toBeTruthy())
    expect(screen.getByText(/自动注入/)).toBeTruthy()
    await userEvent.click(screen.getByText('{date}'))
    expect(onInsert).toHaveBeenCalledWith('{date}')
  })

  it('系统设定:显示不做替换的说明', async () => {
    vi.mocked(get).mockResolvedValue({ kind: 'system', vars: [], note: '系统设定不做变量替换,任何 {xxx} 都按字面文本发给模型' })
    mount(<VarsPanel system="s" stage="(system)" onInsert={vi.fn()} />)
    await waitFor(() => expect(screen.getByText(/字面文本/)).toBeTruthy())
  })
})
