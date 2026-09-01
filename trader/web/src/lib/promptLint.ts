/** prompt 占位符 lint:运行时报错前移到编辑时(设计:Prompt编辑器IDE化 §5.4)。
 * 纯函数,无依赖——与 PromptWorkbench、替换预览、测试共用。 */

/** 提取文本中的 {xxx} 占位符名(跳过 {{}} 转义与空占位)。 */
export function extractPlaceholders(text: string): string[] {
  const out: string[] = []
  // 先把 {{...}} 转义段挖掉,再扫单层 {name}
  const stripped = text.replace(/\{\{[^}]*\}\}/g, '')
  const re = /\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g
  let m: RegExpExecArray | null
  while ((m = re.exec(stripped)) !== null) {
    if (!out.includes(m[1])) out.push(m[1])
  }
  return out
}

/** 未知占位符:文本里出现但不在可用变量集里的名字(保存前黄条警告用)。 */
export function unknownPlaceholders(text: string, known: string[]): string[] {
  const k = new Set(known)
  return extractPlaceholders(text).filter(n => !k.has(n))
}

/** 把 {name} 替换为值(替换预览用):有值替换,无值保留原样(前端红色高亮)。 */
export function substitute(text: string, values: Record<string, unknown>): string {
  return text.replace(/\{\{([^}]*)\}\}/g, '␊$1␊').   // 保护转义
    replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (full, name) =>
      values[name] != null ? String(values[name]) : full).
    replace(/␊([^␊]*)␊/g, '{{$1}}')                  // 还原转义
}
