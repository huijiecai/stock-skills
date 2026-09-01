/** 零依赖行级 diff(LCS):绿增红删,长段未变行折叠。
 * 用于 prompt 版本对比——一眼看清两版之间改了哪几行。 */
import './PromptDiff.css'

type RowType = 'same' | 'add' | 'del' | 'gap'
interface Row { t: RowType; text: string; count?: number }

/** 先裁公共前后缀,再对中段做 LCS;超大方差退化为一删一增。 */
function diffRows(a: string, b: string): Row[] {
  const A = a.split('\n'), B = b.split('\n')
  let s = 0
  while (s < A.length && s < B.length && A[s] === B[s]) s++
  let e = 0
  while (e < A.length - s && e < B.length - s && A[A.length - 1 - e] === B[B.length - 1 - e]) e++
  const midA = A.slice(s, A.length - e), midB = B.slice(s, B.length - e)

  const rows: Row[] = A.slice(0, s).map(t => ({ t: 'same' as const, text: t }))
  if (midA.length * midB.length > 4_000_000) {
    rows.push(...midA.map(t => ({ t: 'del' as const, text: t })))
    rows.push(...midB.map(t => ({ t: 'add' as const, text: t })))
  } else {
    const n = midA.length, m = midB.length
    const dp: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1))
    for (let i = n - 1; i >= 0; i--)
      for (let j = m - 1; j >= 0; j--)
        dp[i][j] = midA[i] === midB[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    let i = 0, j = 0
    while (i < n && j < m) {
      if (midA[i] === midB[j]) { rows.push({ t: 'same', text: midA[i] }); i++; j++ }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { rows.push({ t: 'del', text: midA[i] }); i++ }
      else { rows.push({ t: 'add', text: midB[j] }); j++ }
    }
    while (i < n) { rows.push({ t: 'del', text: midA[i] }); i++ }
    while (j < m) { rows.push({ t: 'add', text: midB[j] }); j++ }
  }
  rows.push(...A.slice(A.length - e).map(t => ({ t: 'same' as const, text: t })))

  // 折叠长段未变行:保留变更处上下各 3 行
  const GAP = 8, CTX = 3
  const out: Row[] = []
  let k = 0
  while (k < rows.length) {
    if (rows[k].t !== 'same') { out.push(rows[k]); k++; continue }
    let run = k
    while (run < rows.length && rows[run].t === 'same') run++
    const len = run - k
    if (len > GAP) {
      out.push(...rows.slice(k, k + CTX))
      out.push({ t: 'gap', text: '', count: len - CTX * 2 })
      out.push(...rows.slice(run - CTX, run))
    } else out.push(...rows.slice(k, run))
    k = run
  }
  return out
}

export default function PromptDiff({ a, b, aLabel = '旧版', bLabel = '新版' }: {
  a: string; b: string; aLabel?: string; bLabel?: string
}) {
  const rows = diffRows(a, b)
  const nAdd = rows.filter(r => r.t === 'add').length
  const nDel = rows.filter(r => r.t === 'del').length
  return (
    <div>
      <div style={{ marginBottom: 8, fontSize: 12, color: 'var(--text-2)' }}>
        <span style={{ color: 'var(--down)' }}>+{nAdd} 行</span> ·{' '}
        <span style={{ color: 'var(--danger)' }}>-{nDel} 行</span>
        <span style={{ marginLeft: 12 }}>{aLabel} → {bLabel}</span>
      </div>
      <div className="diff-box mono">
        {rows.map((r, i) => r.t === 'gap'
          ? <div key={i} className="diff-gap">⋯ {r.count} 行未变 ⋯</div>
          : <div key={i} className={`diff-line diff-${r.t}`}>
              <span className="diff-sign">{r.t === 'add' ? '+' : r.t === 'del' ? '-' : ' '}</span>
              {r.text || '\u00A0'}
            </div>)}
      </div>
    </div>
  )
}
