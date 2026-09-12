import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { ResolvedSessionPerson } from '@/hooks/useSessionResolve'

/** Roster's role enum (`learning_service/roster/service.py` ROLES) — the
 * only values a resolve response or a re-import can ever carry. */
const ROLE_OPTIONS = ['tech_lead', 'senior_swe', 'junior_swe', 'pm', 'uxd'] as const

/**
 * Screen 2 (W2), happy path: the role already on this person's record
 * (seeded at roster import, row 8), pre-filled — confirmed in one click.
 * "Change" swaps to a picker over the roster's own role enum instead;
 * either way nothing here writes back to `person.role` — only a roster
 * re-import does that — the choice only decides the acting persona for
 * this session (`session-store.ts`).
 */
export function RoleConfirm({
  resolved,
  onConfirm,
}: {
  resolved: ResolvedSessionPerson & { role: string }
  onConfirm: (role: string) => void
}) {
  const { t } = useTranslation()
  const [changing, setChanging] = useState(false)
  const [picked, setPicked] = useState<string>(resolved.role)

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm" data-testid="role-confirm">
        <CardHeader>
          <CardTitle className="text-center font-heading text-lg tracking-[0.14em] text-primary">
            {t('common.wordmark')}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4 text-center">
          <p className="text-sm text-muted-foreground">
            {t('roleConfirm.blurb', { name: resolved.display_name })}
          </p>
          {changing ? (
            <>
              <Select value={picked} onValueChange={setPicked}>
                <SelectTrigger data-testid="role-confirm-picker">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_OPTIONS.map((role) => (
                    <SelectItem key={role} value={role}>
                      {t(`personaBar.role.${role}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button data-testid="role-confirm-save" onClick={() => onConfirm(picked)}>
                {t('roleConfirm.confirm')}
              </Button>
            </>
          ) : (
            <>
              <span className="text-base font-medium" data-testid="role-confirm-current">
                {t(`personaBar.role.${resolved.role}`)}
              </span>
              <div className="flex gap-2">
                <Button data-testid="role-confirm-accept" onClick={() => onConfirm(resolved.role)}>
                  {t('roleConfirm.confirm')}
                </Button>
                <Button variant="outline" data-testid="role-confirm-change" onClick={() => setChanging(true)}>
                  {t('roleConfirm.change')}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
