import { useTranslation } from 'react-i18next'
import { MasteryBar } from '@/components/MasteryBar'
import { conceptSlug } from '@/lib/ferry-scenario'

export interface ChatConceptMastery {
  concept_id: string
  p_known: number
  unlocked: boolean
}

/** "Show my mastery by concept" (PLAN_15): one `MasteryBar` per concept —
 * the same component and mastery-tier colours the Progress screen's own
 * per-concept list uses, not a new chart style. */
export function ChatMasteryChart({ concepts }: { concepts: ChatConceptMastery[] }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-card p-3" data-testid="chat-mastery-chart">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {t('progress.masteryPerConceptTitle')}
      </h4>
      <ul className="flex flex-col gap-2">
        {concepts.map((c) => (
          <li key={c.concept_id} className="flex items-center gap-2 text-xs" data-testid={`chat-mastery-row-${conceptSlug(c.concept_id)}`}>
            <code className="w-28 shrink-0 truncate font-mono text-[11px]">{conceptSlug(c.concept_id)}</code>
            {c.unlocked ? <MasteryBar p={c.p_known} /> : <span className="text-muted-foreground">{t('common.locked', { defaultValue: 'locked' })}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}
