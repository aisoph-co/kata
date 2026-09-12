import type { ReactNode } from 'react'
import { navigate, useRoute } from '@/lib/router'

const NAV = [
  { path: '/reps', label: 'Reps' },
  { path: '/dashboard', label: 'Dashboard' },
] as const

/**
 * The signed-in app shell: `persona-menu-trigger` is the marker
 * `build-day/tests/e2e` looks for on every screen to know the W1 gate has
 * been passed (`App.tsx`'s previous placeholder carried it; screens landing
 * in other issues — connections, team — read the same route table).
 */
export function AppShell({ children }: { children: ReactNode }) {
  const route = useRoute()
  return (
    <div className="app-shell">
      <header className="app-header" data-testid="persona-menu-trigger">
        <span className="app-wordmark">KATA</span>
        <nav className="app-nav">
          {NAV.map((item) => (
            <button key={item.path} type="button" data-testid={`nav-${item.label.toLowerCase()}`} data-active={route === item.path} onClick={() => navigate(item.path)}>
              {item.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="app-main">{children}</main>
    </div>
  )
}
