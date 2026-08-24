import { describe, expect, it } from 'vitest'
import { insertAtCursor, detectAutocomplete, navAutocomplete } from './promptInsert'

describe('insertAtCursor(光标插入)', () => {
  it('在光标处插入,选中区被替换,返回新光标', () => {
    const ta = { value: '【】', selectionStart: 1, selectionEnd: 2 }   // 选中"】"
    expect(insertAtCursor(ta, '{date}')).toEqual({ text: '【{date}', caret: 7 })
  })
  it('无 DOM 引用返回 null', () => {
    expect(insertAtCursor(null, 'x')).toBeNull()
  })
})

describe('detectAutocomplete(触发检测)', () => {
  it('@ 前缀触发工具补全', () => {
    expect(detectAutocomplete('调用 @get', 7)).toEqual({ trigger: '@', query: 'get', start: 3 })
  })
  it('{ 前缀触发变量补全(含已输入前缀)', () => {
    expect(detectAutocomplete('目标 {we', 6)).toEqual({ trigger: '{', query: 'we', start: 3 })
  })
  it('{{ 转义不触发', () => {
    expect(detectAutocomplete('JSON {{na', 8)).toBeNull()
  })
  it('普通文本不触发', () => {
    expect(detectAutocomplete('普通文本', 4)).toBeNull()
  })
})

describe('navAutocomplete(键盘导航)', () => {
  const mk = (key: string) => ({ key, preventDefault: () => {} })
  it('↑↓ 循环移动', () => {
    expect(navAutocomplete(mk('ArrowDown'), 0, 3)?.index).toBe(1)
    expect(navAutocomplete(mk('ArrowDown'), 2, 3)?.index).toBe(0)   // 环回
    expect(navAutocomplete(mk('ArrowUp'), 0, 3)?.index).toBe(2)
  })
  it('Enter 选中 / Esc 关闭 / 其他键透传', () => {
    expect(navAutocomplete(mk('Enter'), 1, 3)?.action).toBe('pick')
    expect(navAutocomplete(mk('Escape'), 1, 3)?.action).toBe('close')
    expect(navAutocomplete(mk('a'), 1, 3)).toBeNull()
  })
  it('空候选不接管键盘', () => {
    expect(navAutocomplete(mk('Enter'), 0, 0)).toBeNull()
  })
})
