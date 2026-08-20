import { Card, Col, Row, Table } from 'antd'
import { useSearchParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'
import { pnlColor, pnlArrow } from '../lib/ui'

export default function Compare() {
  const [params] = useSearchParams()
  const ids = (params.get('ids') ?? '').split(',').filter(Boolean)
  const a = useQuery({ queryKey: ['run', ids[0]], queryFn: () => get(`/runs/${ids[0]}`), enabled: !!ids[0] })
  const b = useQuery({ queryKey: ['run', ids[1]], queryFn: () => get(`/runs/${ids[1]}`), enabled: !!ids[1] })

  if (ids.length < 2) return <Card>请在 <Link to="/runs">场次列表</Link> 勾选两场再对比</Card>
  if (a.isLoading || b.isLoading) return <Card>加载中…</Card>
  const ra = a.data, rb = b.data

  const pvA = JSON.parse(ra.prompt_versions ?? '{}')
  const pvB = JSON.parse(rb.prompt_versions ?? '{}')
  const samePrompt = JSON.stringify(pvA) === JSON.stringify(pvB)
  const sameDate = ra.trade_date === rb.trade_date
  const sameStart = ra.fingerprint && ra.fingerprint === rb.fingerprint

  let verdict = '', attr = ''
  if (samePrompt && sameDate) {
    if (ra.kind !== rb.kind) { verdict = '同数据日同 prompt 的实盘 vs 模拟——同源复现测试:差异来自实时/回放管线差与 LLM 随机性'; attr = '复现测试' }
    else { verdict = '两场血统完全一致——没有单一变量,无可归因差异'; attr = '⚠' }
  } else if (samePrompt) { verdict = `同 prompt,不同数据日(${ra.trade_date} vs ${rb.trade_date})——差异归因:行情日`; attr = '行情日' }
  else if (sameDate) { verdict = '同数据日,prompt 不同——差异归因:prompt ✓ 干净对比'; attr = 'prompt' }
  else { verdict = 'prompt 与数据日都不同——归因不唯一,仅供参考'; attr = '⚠ 不唯一' }
  if (sameStart) verdict += ';起点指纹一致 ✓'

  const m = (r: any) => r.metrics ?? {}
  return (
    <div>
      {/* 归因判定横幅 */}
      <div className="verdict-banner">
        <span className="verdict-tag">{attr}</span>
        <span>{verdict}</span>
      </div>
      <Row gutter={16} style={{ marginTop: 16 }}>
        {[ra, rb].map((r, i) => (
          <Col span={12} key={i}>
            <Card title={<Link to={`/runs/${r.id}`}>{r.slug}</Link>} size="small">
              <div className="metric-row" style={{ gridTemplateColumns: 'repeat(4, 1fr)', margin: 0 }}>
                <div className="metric-card" style={{ boxShadow: 'none', padding: '8px 10px' }}>
                  <div className="metric-label">收益</div>
                  <div className="num" style={{ fontSize: 20, color: pnlColor(m(r).return_pct) }}>
                    {pnlArrow(m(r).return_pct)}{Math.abs(m(r).return_pct ?? 0)}%
                  </div>
                </div>
                <div className="metric-card" style={{ boxShadow: 'none', padding: '8px 10px' }}>
                  <div className="metric-label">回撤</div>
                  <div className="num" style={{ fontSize: 20 }}>{m(r).max_drawdown_pct ?? '-'}%</div>
                </div>
                <div className="metric-card" style={{ boxShadow: 'none', padding: '8px 10px' }}>
                  <div className="metric-label">胜率</div>
                  <div className="num" style={{ fontSize: 20 }}>{m(r).win_rate ?? '-'}%</div>
                </div>
                <div className="metric-card" style={{ boxShadow: 'none', padding: '8px 10px' }}>
                  <div className="metric-label">交易</div>
                  <div className="num" style={{ fontSize: 20 }}>{m(r).n_fills ?? 0}<span className="metric-label"> 笔</span></div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>
      <Card title="封面信息" size="small" style={{ marginTop: 16 }}>
        <Table size="small" pagination={false} rowKey="k" dataSource={[
          { k: '数据日', a: ra.trade_date, b: rb.trade_date },
          { k: 'prompt 版本', a: ra.prompt_versions, b: rb.prompt_versions },
          { k: '起点指纹', a: ra.fingerprint ?? '-', b: rb.fingerprint ?? '-' },
          { k: '系统', a: ra.system, b: rb.system },
        ]} columns={[
          { title: '', dataIndex: 'k', width: 100 },
          { title: ra.slug, dataIndex: 'a', render: (v: string) => <span className="mono" style={{ fontSize: 12 }}>{v}</span> },
          { title: rb.slug, dataIndex: 'b', render: (v: string) => <span className="mono" style={{ fontSize: 12 }}>{v}</span> },
        ]} />
      </Card>
    </div>
  )
}
