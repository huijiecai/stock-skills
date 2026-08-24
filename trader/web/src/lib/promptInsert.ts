/** 光标插入与触发式补全检测(@ 工具 / { 变量,设计 §5.2)。
 * 纯函数 + 最小 DOM 操作,便于单测。 */

export interface TextareaLike {
  value: string
  selectionStart: number
  selectionEnd: number
}

/** 在光标处插入片段(选中区被替换);返回新文本与新光标位置,调用方负责 setState。 */
export function insertAtCursor(ta: TextareaLike | null, snippet: string):
    { text: string; caret: number } | null {
  if (!ta) return null
  const { value, selectionStart: s, selectionEnd: e } = ta
  return { text: value.slice(0, s) + snippet + value.slice(e),
           caret: s + snippet.length }
}

/** 触发检测:光标前是 @word(工具)或 {word(变量)时返回触发态。
 * {{ 开头(转义)不触发;word 仅限标识符字符。 */
export function detectAutocomplete(text: string, caret: number):
    { trigger: '@' | '{'; query: string; start: number } | null {
  const before = text.slice(0, caret)
  const m = before.match(/([@{])([a-zA-Z0-9_]*)$/)
  if (!m) return null
  const [, trig, query] = m
  const start = caret - query.length - 1
  if (trig === '{' && text[start - 1] === '{') return null   // {{ 转义
  return { trigger: trig as '@' | '{', query, start }
}

/** 浮层键盘导航:开放状态下拦 ↑↓/Enter/Esc,返回处理后的选中索引与动作。 */
export function navAutocomplete(e: { key: string; preventDefault(): void },
    index: number, count: number):
    { index: number; action: 'move' | 'pick' | 'close' } | null {
  if (count <= 0) return null
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    return { index: (index + 1) % count, action: 'move' }
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    return { index: (index - 1 + count) % count, action: 'move' }
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    return { index, action: 'pick' }
  }
  if (e.key === 'Escape') return { index, action: 'close' }
  return null
}
