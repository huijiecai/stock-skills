import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, Wallet, FileText, TrendingUp, Cpu } from 'lucide-react'

const navItems = [
  { path: '/', icon: LayoutDashboard, label: 'Dashboard', sub: '场13' },
  { path: '/portfolio', icon: Wallet, label: 'AI账户', sub: '场10' },
  { path: '/report', icon: FileText, label: '每日报告', sub: '场11' },
  { path: '/market', icon: TrendingUp, label: '行情', sub: '场1-4' },
]

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 bg-surface-raised border-r border-border-dim flex flex-col shrink-0">
        {/* Logo */}
        <div className="p-5 border-b border-border-dim">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent-cyan/20 flex items-center justify-center">
              <Cpu className="w-4 h-4 text-accent-cyan" />
            </div>
            <div>
              <div className="text-sm font-semibold text-text-primary tracking-wide">ASTOCK</div>
              <div className="text-[10px] text-text-muted font-mono uppercase tracking-widest">AI Trading</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group ${
                  isActive
                    ? 'bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-overlay border border-transparent'
                }`
              }
            >
              <item.icon className="w-4 h-4 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium">{item.label}</div>
                <div className="text-[10px] text-text-muted font-mono">{item.sub}</div>
              </div>
            </NavLink>
          ))}
        </nav>

        {/* Status */}
        <div className="p-4 border-t border-border-dim">
          <div className="flex items-center gap-2">
            <div className="pulse-dot bg-profit" />
            <span className="text-xs text-text-muted">系统运行中</span>
          </div>
          <div className="mt-1 text-[10px] font-mono text-text-muted">v2.0 · TDX数据</div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-surface">
        <Outlet />
      </main>
    </div>
  )
}
