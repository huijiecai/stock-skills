/** 指令台·触发式补全浮层(@ 工具 / { 变量,设计 §5.2)。
 * 纯展示:候选列表 + 键盘导航由父组件经 navAutocomplete 驱动。 */
export interface AcItem {
  label: string          // 插入产物,如 "{date}" / 工具引导行
  title: string          // 主标题,如 date / get_quotes
  desc: string
  tag?: string           // 右侧小标签(自动注入/写/分组)
  danger?: boolean
}

export default function AutocompleteList({ items, index, onPick, onHover }: {
  items: AcItem[], index: number, onPick: (item: AcItem) => void, onHover: (i: number) => void }) {
  if (!items.length) return null
  return (
    <div className="ac-pop" role="listbox">
      {items.map((it, i) => (
        <div key={it.title} role="option" aria-selected={i === index}
             className={`ac-item${i === index ? ' cur' : ''}`}
             onMouseEnter={() => onHover(i)}
             onMouseDown={e => e.preventDefault()}   // 不抢编辑器焦点
             onClick={() => onPick(it)}>
          <span className="t mono">{it.title}</span>
          <span className="d">{it.desc}</span>
          {it.tag && <span className="g">{it.tag}</span>}
        </div>
      ))}
      <div className="ac-hint">↑↓ 选择 · Enter 插入 · Esc 关闭</div>
    </div>
  )
}
