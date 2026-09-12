import { useTranslation } from 'react-i18next'
import { MASTERY_THRESHOLD, formatPercent, masteryTier } from '@/lib/format'
import { cn } from '@/lib/utils'

const TIER_BG: Record<string, string> = {
  low: 'bg-mastery-low',
  mid: 'bg-mastery-mid',
  high: 'bg-mastery-high',
}

/** Horizontal p_known bar with a tick at the 0.85 mastery mark. */
export function MasteryBar({ p, label }: { p: number; label?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-full min-w-24 overflow-visible rounded-full bg-muted">
        <div
          className={cn('h-2 rounded-full transition-all', TIER_BG[masteryTier(p)])}
          style={{ width: `${Math.min(100, Math.max(0, p * 100))}%` }}
        />
        <div
          className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-foreground/50"
          style={{ left: `${MASTERY_THRESHOLD * 100}%` }}
          title={t('common.masteryMarkTitle')}
        />
      </div>
      <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
        {label ?? formatPercent(p)}
      </span>
    </div>
  )
}

const TIER_CELL_BG: Record<string, string> = {
  low: 'bg-mastery-low/70',
  mid: 'bg-mastery-mid/70',
  high: 'bg-mastery-high/70',
}

/** Compact heatmap cell: fill colour = mastery tier, optional at-risk dot. */
export function MasteryCell({ p, atRisk }: { p: number; atRisk?: boolean }) {
  return (
    <div
      className={cn(
        'relative flex size-9 items-center justify-center rounded text-[10px] font-medium text-white',
        TIER_CELL_BG[masteryTier(p)],
      )}
      title={formatPercent(p)}
    >
      {Math.round(p * 100)}
      {atRisk && (
        <span className="absolute -right-1 -top-1 size-2.5 rounded-full border border-card bg-destructive" />
      )}
    </div>
  )
}
