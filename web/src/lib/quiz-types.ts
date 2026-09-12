/**
 * Shapes from `contracts/openapi.yaml` (1.2.1) that W2 (quiz engine +
 * dashboard) reads or writes: `GET /me/next`, `POST /me/reviews`,
 * `GET /me/progress`, `GET /me/concept-graph`. Kept local to `web` rather
 * than generated — the same hand-typed-from-the-spec pattern W1 already
 * uses (`useSessionResolve.ts`'s `ResolvedSessionPerson`).
 */

export type ItemKind = 'mcq' | 'msq' | 'self_rated' | 'short_answer' | 'teach_back'

export interface ItemPublic {
  id: string
  concept_id: string
  kind: ItemKind
  prompt: string
  /** mcq/msq -> {options: [str]}; self_rated/short_answer/teach_back -> {}. */
  payload: { options?: string[] }
}

export type NextItemsReason = 'all_mastered' | 'blocked_by_prerequisites'

export interface NextItemsResponse {
  items: ItemPublic[]
  reason?: NextItemsReason
}

/** The one field that actually varies by kind in the request body — see
 * the core spec's `response` shape table this issue starts by reading. */
export type ReviewResponseBody =
  | { choice: number }
  | { choices: number[] }
  | { rating: number }
  | { text: string }
  | Record<string, never>

export interface ReviewSubmitRequest {
  item_id: string
  idempotency_key: string
  response: ReviewResponseBody
  confidence?: number | null
  bypassed?: boolean
}

export interface ConceptState {
  p_known: number
  mastered: boolean
}

export interface ReviewResult {
  grade: number
  rating: number
  correct: boolean | null
  explanation: string | null
  confidence: number | null
  bypassed: boolean
  next_due_at: string
  concept: ConceptState
}

export interface RetentionBand {
  accuracy: number | null
  samples: number
}

export interface RetentionBands {
  d1: RetentionBand
  d7: RetentionBand
  d30: RetentionBand
}

export interface PersonLearningSummary {
  retention: RetentionBands
  bypass_rate: number | null
  calibration: number | null
  review_count: number
  last_active: string | null
}

export interface ProgressEntry {
  concept_id: string
  p_known: number
  mastered: boolean
  due_count: number
  unlocked: boolean
  /** R3a (open): not on the contract yet — `ProgressEntry` has no
   * per-concept rep count. Only ever present if a future contract version
   * adds it; never invented client-side. */
  rep_count?: number
}

export interface ProgressResponse {
  concepts: ProgressEntry[]
  summary: PersonLearningSummary
}

export interface ConceptGraphNode {
  concept_id: string
  slug: string
  title: string
  p_known: number
  mastered: boolean
  unlocked: boolean
}

export interface ConceptGraphEdge {
  from?: string
  to?: string
  a?: string
  b?: string
  kind: string
}

export interface ConceptGraphResponse {
  nodes: ConceptGraphNode[]
  edges: ConceptGraphEdge[]
}
