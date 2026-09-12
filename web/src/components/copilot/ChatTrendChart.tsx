import { ProgressChart, type HistoryReview } from '@/components/progress/ProgressChart'

/** "Show my p_known over the last 30 days" (PLAN_15): the exact
 * `ProgressChart` the Progress screen renders — no second chart
 * implementation, so the hand-drawn SVG style always matches. */
export function ChatTrendChart({
  conceptId,
  days,
  reviews,
}: {
  conceptId: string
  conceptTitle?: string
  days: number
  reviews: HistoryReview[]
}) {
  return (
    <div className="rounded-lg border bg-card p-3" data-testid="chat-trend-chart">
      <ProgressChart allReviews={reviews} conceptReviews={reviews} conceptId={conceptId} days={days} updatedAt={Date.now()} />
    </div>
  )
}
