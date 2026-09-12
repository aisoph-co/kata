/**
 * `/team/*` response shapes (`contracts/openapi.yaml`) — owned by C2
 * (KATA-3), not this issue (W4/KATA-8). Only the fields the team heatmap
 * and its drill-down panel actually render; retention/bypass_rate/
 * calibration are R2/R3's rows on top of this same frozen shape.
 */

export interface RetentionBand {
  accuracy: number | null
  samples: number
}

export interface RetentionBands {
  d1: RetentionBand
  d7: RetentionBand
  d30: RetentionBand
}

export interface TeamConceptSummary {
  concept_id: string
  mean_mastery: number
  share_mastered: number
  at_risk_count: number
}

export interface TeamPersonSummary {
  person_id: string
  adherence: number
  velocity: number
  last_active: string | null
  bypass_rate: number | null
}

export interface TeamOverviewResponse {
  concepts: TeamConceptSummary[]
  people: TeamPersonSummary[]
  retention: RetentionBands
}

export interface TeamConceptPerson {
  person_id: string
  p_known: number
  mastered: boolean
}

/** `GET /team/concepts/{concept_id}` — one column of the heatmap: every
 * subtree member's state on this one concept. The contract has no single
 * endpoint returning the whole person x concept matrix at once, so the
 * heatmap fetches one of these per concept in `overview.concepts` and
 * assembles them client-side (`useTeamHeatmapMatrix`). */
export interface TeamConceptDetailResponse {
  concept_id: string
  people: TeamConceptPerson[]
}

export interface ProgressEntry {
  concept_id: string
  p_known: number
  mastered: boolean
  due_count: number
  unlocked: boolean
}

export interface TeamPersonDetailResponse {
  person_id: string
  concepts: ProgressEntry[]
  adherence: number
  velocity: number
  due_count: number
  last_active: string | null
  bypass_rate: number | null
  retention: RetentionBands
  calibration: number | null
}

export interface AuditEntry {
  id: string
  actor_person_id: string
  subject_scope: string
  endpoint: string
  at: string
}

export interface AuditResponse {
  entries: AuditEntry[]
}
