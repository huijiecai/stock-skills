/** 系统切换器(全屏系统页的紧凑入口)。 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { get } from '../api/client'

export default function SystemSwitcher({ current }: { current: string }) {
  const nav = useNavigate()
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get('/systems'), staleTime: 60000 })
  return (
    <select className="ws-syswitch" value={current}
            onChange={(e) => nav(`/systems/${encodeURIComponent(e.target.value)}`)}>
      {(systems.data ?? []).map((s: any) => (
        <option key={s.slug} value={s.slug}>
          {s.display_name || s.slug}{s.status === 'archived' ? '(归档)' : ''}
        </option>
      ))}
    </select>
  )
}
