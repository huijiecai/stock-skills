import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { get, post } from '../api/client'
import RunDiscussion from './RunDiscussion'

vi.mock('../api/client', () => ({ get: vi.fn(), post: vi.fn() }))

const RUN = {
  id: 449,
  stage: 'analyze',
  trade_date: '20260824',
  stage_contract: { prompt: 'analyze' },
}
const getComputedStyle = window.getComputedStyle.bind(window)

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RunDiscussion run={RUN} open onClose={vi.fn()} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  vi.spyOn(window, 'getComputedStyle').mockImplementation(element => getComputedStyle(element))
  vi.mocked(get).mockReset()
  vi.mocked(post).mockReset()
  vi.mocked(get).mockResolvedValue({ messages: [], anchor: { mode: 'frozen' } })
})

afterEach(() => vi.restoreAllMocks())

describe('RunDiscussion', () => {
  it('明确展示冻结上下文，并把追问发给 Run 对话接口', async () => {
    vi.mocked(post).mockResolvedValue({ reply: '量能和板块扩散都不足。' })
    mount()

    expect(await screen.findByText('冻结上下文')).toBeTruthy()
    expect(screen.getByText('只澄清本场结论')).toBeTruthy()
    const input = screen.getByPlaceholderText('追问这次结论…')
    await userEvent.type(input, '为什么认为偏弱？')
    await userEvent.click(screen.getByRole('button', { name: /发\s*送/ }))

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/runs/449/chat', { message: '为什么认为偏弱？' },
    ))
    expect(await screen.findByText('量能和板块扩散都不足。')).toBeTruthy()
  })
})
