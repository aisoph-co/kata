import { useEffect } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import i18n, { DEFAULT_LANGUAGE, getStoredLanguage, isLanguage, setStoredLanguage } from '@/i18n'
import { AnswersNotes } from '@/pages/AnswersNotes'
import { Audit } from '@/pages/Audit'
import { Connect } from '@/pages/Connect'
import { Focus } from '@/pages/Focus'
import { NextUp } from '@/pages/NextUp'
import { PersonDrilldown } from '@/pages/PersonDrilldown'
import { Progress } from '@/pages/Progress'
import { Recommendations } from '@/pages/Recommendations'
import { Replay } from '@/pages/Replay'
import { SourceExcerpt } from '@/pages/SourceExcerpt'
import { Team } from '@/pages/Team'
import { TeamContext } from '@/pages/TeamContext'

/** Root of every `/:lang/...` route: validates the language segment (an
 * unknown one redirects to the stored/default language), keeps i18next and
 * `<html lang>` in sync with it, and remembers the choice for next time. */
function LangLayout() {
  const { lang } = useParams()
  const valid = isLanguage(lang)

  useEffect(() => {
    if (!valid || !lang) return
    if (i18n.language !== lang) i18n.changeLanguage(lang)
    setStoredLanguage(lang)
    document.documentElement.lang = lang
  }, [lang, valid])

  if (!valid) {
    return <Navigate to={`/${getStoredLanguage() ?? DEFAULT_LANGUAGE}`} replace />
  }

  return <AppShell />
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={`/${getStoredLanguage() ?? DEFAULT_LANGUAGE}`} replace />} />
      <Route path="/:lang" element={<LangLayout />}>
        {/* Index + the four Kata tabs (PLAN_08) */}
        <Route index element={<Navigate to="team-context" replace />} />
        <Route path="team-context" element={<TeamContext />} />
        <Route path="source/:ref" element={<SourceExcerpt />} />
        <Route path="progress" element={<Progress />} />
        <Route path="team" element={<Team />} />
        <Route path="team/:personId" element={<PersonDrilldown />} />
        <Route path="connect" element={<Connect />} />

        {/* Superseded by the tabs above — kept as redirects, not pages. */}
        <Route path="concept-map" element={<Navigate to="../team-context" replace />} />
        <Route path="dashboard" element={<Navigate to="../progress" replace />} />

        {/* The remaining PLAN_06 screens — reachable from the Developer
         * toggle's "All screens" menu, routes unchanged. */}
        <Route path="next-up" element={<NextUp />} />
        <Route path="answers-notes" element={<AnswersNotes />} />
        <Route path="recommendations" element={<Recommendations />} />
        <Route path="focus" element={<Focus />} />
        <Route path="audit" element={<Audit />} />
        <Route path="replay" element={<Replay />} />
        <Route path="*" element={<Navigate to="team-context" replace />} />
      </Route>
      <Route path="*" element={<Navigate to={`/${getStoredLanguage() ?? DEFAULT_LANGUAGE}`} replace />} />
    </Routes>
  )
}
