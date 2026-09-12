import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { BackstageDrawer } from '@/components/BackstageDrawer'
import { PersonaMenu } from '@/components/PersonaMenu'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useLangPath } from '@/hooks/useLangPath'
import { DEFAULT_LANGUAGE, isLanguage, SUPPORTED_LANGUAGES, type Language } from '@/i18n'
import { useBackstageCalls } from '@/lib/backstage-store'
import { usePersona } from '@/lib/persona-store'
import { cn } from '@/lib/utils'

function LanguageSwitch() {
  const { t } = useTranslation()
  const { lang } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const current = isLanguage(lang) ? lang : DEFAULT_LANGUAGE

  function switchTo(target: Language) {
    if (target === current) return
    const rest = location.pathname.replace(/^\/[a-z]{2}(?=\/|$)/, '')
    navigate(`${rest ? `/${target}${rest}` : `/${target}`}${location.search}`)
  }

  return (
    <div className="flex items-center gap-1" role="group" aria-label={t('languageSwitch.label')}>
      {SUPPORTED_LANGUAGES.map((code) => (
        <Button
          key={code}
          type="button"
          variant={current === code ? 'default' : 'outline'}
          size="sm"
          data-testid={`lang-${code}`}
          onClick={() => switchTo(code)}
        >
          {t(`languageSwitch.${code}`)}
        </Button>
      ))}
    </div>
  )
}

interface Tab {
  to: string
  labelKey: string
  testId: string
  hidden?: boolean
}

/** All-screens entries — 10 of the 11 PLAN_06 pages, developer-only (the
 * 11th, the person drilldown, has no fixed URL to list — it's reached by
 * clicking a person on Team). Clicking "Concept map" or "Dashboard" lands
 * you back on Team context / Progress (their routes now redirect there),
 * listed anyway for continuity. */
const ALL_SCREENS: { to: string; labelKey: string }[] = [
  { to: '/concept-map', labelKey: 'linkConceptMap' },
  { to: '/next-up', labelKey: 'linkNextUp' },
  { to: '/dashboard', labelKey: 'linkDashboard' },
  { to: '/progress', labelKey: 'linkProgress' },
  { to: '/answers-notes', labelKey: 'linkAnswersNotes' },
  { to: '/team', labelKey: 'linkTeam' },
  { to: '/recommendations', labelKey: 'linkRecommendations' },
  { to: '/focus', labelKey: 'linkFocus' },
  { to: '/audit', labelKey: 'linkAudit' },
  { to: '/replay', labelKey: 'linkReplay' },
]

function TopTabs() {
  const { t } = useTranslation()
  const langPath = useLangPath()
  const persona = usePersona()
  const isManager = persona.roles.includes('manager')

  const tabs: Tab[] = [
    { to: '/team-context', labelKey: 'tabs.teamContext', testId: 'tab-team-context' },
    { to: '/progress', labelKey: 'tabs.progress', testId: 'tab-progress' },
    { to: '/team', labelKey: 'tabs.team', testId: 'tab-team', hidden: !isManager },
    { to: '/connect', labelKey: 'tabs.connect', testId: 'tab-connect' },
  ]

  return (
    <nav className="flex h-full items-stretch gap-7" aria-label={t('tabs.ariaLabel')}>
      {tabs
        .filter((tab) => !tab.hidden)
        .map((tab) => (
          <NavLink
            key={tab.to}
            to={langPath(tab.to)}
            data-testid={tab.testId}
            className={({ isActive }) =>
              cn(
                'flex items-center border-b-2 border-transparent text-[15px] text-muted-foreground transition-colors hover:text-foreground',
                isActive && 'border-primary font-medium text-foreground',
              )
            }
          >
            {t(tab.labelKey)}
          </NavLink>
        ))}
    </nav>
  )
}

export function AppShell() {
  const { t } = useTranslation()
  const [backstageOpen, setBackstageOpen] = useState(false)
  // Developer is off by default (David's audience is the product demo, not
  // the request/response log) — a top-bar toggle brings back Backstage and
  // the "All screens" menu (10 of the 11 PLAN_06 pages behind the four
  // tabs — see ALL_SCREENS below for the 11th).
  const [developerMode, setDeveloperMode] = useState(false)
  const calls = useBackstageCalls()
  const langPath = useLangPath()

  useEffect(() => {
    document.title = t('common.appTitle')
  }, [t])

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="flex h-15 items-center gap-9 border-b bg-card px-6">
        <span className="font-heading text-[15px] font-extrabold tracking-[0.14em] text-primary">
          {t('common.wordmark')}
        </span>
        <TopTabs />
        <div className="ml-auto flex items-center gap-2">
          <LanguageSwitch />
          <Button
            variant={developerMode ? 'default' : 'outline'}
            size="sm"
            data-testid="developer-toggle"
            onClick={() => setDeveloperMode((v) => !v)}
          >
            {t('appShell.developer')}
          </Button>
          {developerMode && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" data-testid="all-screens-toggle">
                  {t('appShell.allScreens')}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {ALL_SCREENS.map((screen) => (
                  <DropdownMenuItem key={screen.to} asChild>
                    <NavLink to={langPath(screen.to)}>{t(`nav.${screen.labelKey}`)}</NavLink>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {developerMode && (
            <Button variant="outline" size="sm" onClick={() => setBackstageOpen(true)}>
              {t('appShell.backstage')} {calls.length > 0 && `(${calls.length})`}
            </Button>
          )}
          <div className="ml-1 border-l pl-3">
            <PersonaMenu />
          </div>
        </div>
      </header>
      <main className="min-w-0 flex-1 bg-background">
        <Outlet />
      </main>
      {developerMode && <BackstageDrawer open={backstageOpen} onOpenChange={setBackstageOpen} />}
    </div>
  )
}
