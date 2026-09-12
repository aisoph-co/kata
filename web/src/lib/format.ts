export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

/** `m:ss`, for the Connections screen's "ingesting" badge (KATA-11). */
export function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/** Locked scale (PLAN_06): 0–0.5 red-ish, 0.5–0.85 amber, ≥0.85 green. */
export function masteryTier(p: number): 'low' | 'mid' | 'high' {
  if (p >= 0.85) return 'high'
  if (p >= 0.5) return 'mid'
  return 'low'
}

export const MASTERY_THRESHOLD = 0.85

// Fields the service strips from item payloads before a learner sees them
// (agency-v1 learning_service/engine/models.py ANSWER_KEY_FIELDS) — surfaced
// in the Backstage drawer so the "nothing hidden, except what's genuinely
// hidden" point is visible, not just asserted.
export const ANSWER_KEY_FIELDS = ['correct_index', 'correct_indices', 'answer', 'reference', 'rubric', 'explanation']

export const RATING_LABEL: Record<number, string> = {
  1: 'Again',
  2: 'Hard',
  3: 'Good',
  4: 'Easy',
}
