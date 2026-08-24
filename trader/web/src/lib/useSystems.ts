/** 系统显示名映射:name(英文键) → display_name(中文显示)。
 * 全局 ['systems'] 缓存共享,任何页面显示系统名都走这里保证一致。 */
import { useQuery } from '@tanstack/react-query'
import { get } from '../api/client'

export function useSystemLabel(): (name: string) => string {
  const systems = useQuery({ queryKey: ['systems'], queryFn: () => get('/systems'), staleTime: 60_000 })
  const map = new Map<string, string>()
  for (const s of (systems.data ?? []) as any[]) {
    map.set(s.slug ?? s.name, s.display_name || s.slug || s.name)
  }
  return (name: string) => map.get(name) ?? name
}
