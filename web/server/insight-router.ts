/**
 * AE-25: deterministic classification of one chat turn into a lane —
 * `null` for an ordinary conversational turn (stays on Hermes, unchanged),
 * or a specific `InsightIntent` for a turn that needs the person's own
 * learning data, a chart, or a review run (routed to OpenRouter instead).
 *
 * Deliberately not model-based: the phrasing this feature is scored
 * against (`PLAN_15` acceptance criteria) is a fixed, known set of
 * archetypes ("how am I doing?", "show my mastery by concept", "what
 * should I review?", "where am I weakest?"), so a small pattern set is
 * both accurate for those and fully deterministic — no extra network call
 * (and no non-determinism) just to decide which lane a turn takes. See the
 * PR description for the fuller routing rationale.
 */
import { findPersonByName, type RosterPerson } from './roster.js'

export type InsightIntent =
  | { kind: 'self_summary' }
  | { kind: 'weakest' }
  | { kind: 'mastery_chart' }
  | { kind: 'trend_chart' }
  | { kind: 'next_review' }
  | { kind: 'team_summary' }
  | { kind: 'person_summary'; person: RosterPerson }

const SELF_RE = /\bhow(?:'?m| am) i doing\b|\bmy (?:progress|retention|mastery|calibration|numbers|stats)\b|\bam i (?:doing|improving)\b/i
const WEAKEST_RE = /\b(?:weak(?:est)?|worst|struggling|behind)\b/i
const MASTERY_CHART_RE = /\bmastery\b.*\b(?:concept|chart|graph|breakdown|bar)\b|\b(?:chart|graph)\b.*\bmastery\b/i
const TREND_RE = /\btrend\b|\bover time\b|p.?known|\blast (?:\d+ )?days\b|\bhistory chart\b|\bprogress chart\b/i
const REVIEW_RE = /what should i review|\bquiz me\b|\btest me\b|give me a question|\bnext (?:review|up|card)\b|review (?:something|now)/i
const TEAM_RE = /\bmy team\b|\bthe team\b|\bteam'?s\b|\beveryone\b|\bmy reports\b|\bteam overview\b/i

export function classifyIntent(text: string): InsightIntent | null {
  const t = text.trim()
  if (!t) return null

  if (SELF_RE.test(t) && !MASTERY_CHART_RE.test(t) && !TREND_RE.test(t)) return { kind: 'self_summary' }
  if (WEAKEST_RE.test(t)) return { kind: 'weakest' }
  if (MASTERY_CHART_RE.test(t)) return { kind: 'mastery_chart' }
  if (TREND_RE.test(t)) return { kind: 'trend_chart' }
  if (REVIEW_RE.test(t)) return { kind: 'next_review' }
  if (TEAM_RE.test(t)) return { kind: 'team_summary' }

  const person = findPersonByName(t)
  if (person) return { kind: 'person_summary', person }

  return null
}
