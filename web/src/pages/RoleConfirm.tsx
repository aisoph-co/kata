import { useState } from 'react'
import type { ResolvedSessionPerson } from '@/hooks/useSessionResolve'

/** Roster's role enum (`contracts/openapi.yaml` `PersonSummary.role`) — the
 * only values a resolve response or a re-import can ever carry. */
const ROLE_OPTIONS = ['tech_lead', 'senior_swe', 'junior_swe', 'pm', 'uxd'] as const

const ROLE_LABEL: Record<(typeof ROLE_OPTIONS)[number], string> = {
  tech_lead: 'Tech lead',
  senior_swe: 'Senior SWE',
  junior_swe: 'Junior SWE',
  pm: 'PM',
  uxd: 'UX designer',
}

/**
 * Screen 2, happy path: the role already on this person's record (seeded at
 * roster import, contract change #8), pre-filled — confirmed in one click.
 * "Change" swaps to a picker over the roster's own role enum instead;
 * either way nothing here writes back to `person.role` — only a roster
 * re-import does that — the choice only decides the acting persona for
 * this session (`role-confirm-store.ts`).
 */
export function RoleConfirm({
  resolved,
  onConfirm,
}: {
  resolved: ResolvedSessionPerson & { role: string }
  onConfirm: (role: string) => void
}) {
  const [changing, setChanging] = useState(false)
  const [picked, setPicked] = useState<string>(resolved.role)

  return (
    <div className="gate-screen">
      <div className="gate-card" data-testid="role-confirm">
        <h1 className="gate-wordmark">KATA</h1>
        <p className="gate-blurb">Hi {resolved.display_name} — is this still your role?</p>
        {changing ? (
          <>
            <select
              data-testid="role-confirm-picker"
              value={picked}
              onChange={(event) => setPicked(event.target.value)}
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role} value={role}>
                  {ROLE_LABEL[role]}
                </option>
              ))}
            </select>
            <button data-testid="role-confirm-save" onClick={() => onConfirm(picked)}>
              Confirm
            </button>
          </>
        ) : (
          <>
            <span className="gate-title" data-testid="role-confirm-current">
              {ROLE_LABEL[resolved.role as (typeof ROLE_OPTIONS)[number]] ?? resolved.role}
            </span>
            <div className="gate-actions">
              <button data-testid="role-confirm-accept" onClick={() => onConfirm(resolved.role)}>
                Confirm
              </button>
              <button data-testid="role-confirm-change" onClick={() => setChanging(true)}>
                Change
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
