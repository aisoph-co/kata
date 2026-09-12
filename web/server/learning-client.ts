/**
 * AE-25: the insight lane's only way to touch the learning service — the
 * same trusted-caller shape the SPA's own `/api/*` proxy already uses
 * (`Authorization: Bearer $LEARNING_SERVICE_TOKEN`, `X-Acting-Identity:
 * web:<email>`; see `learning_service/main.py`'s `require_service_token`/
 * `acting_identity`), called directly from this runtime instead of through
 * Caddy/Vite's proxy since the runtime has no browser origin to proxy for.
 *
 * Every read here is a plain `GET`/`POST` against an endpoint the SPA
 * already calls (`/me/progress`, `/me/history`, `/me/next`, `/team/*`);
 * the service's own `resolve_person_id`/`require_manager` dependencies are
 * what actually decide who may see what — this client never second-guesses
 * a 403.
 */

export class LearningApiError extends Error {
  status: number
  code?: string

  constructor(status: number, code: string | undefined, message: string) {
    super(message)
    this.name = 'LearningApiError'
    this.status = status
    this.code = code
  }
}

export interface LearningClientConfig {
  baseUrl: string
  serviceToken: string
}

export interface ConceptProgress {
  concept_id: string
  p_known: number
  mastered: boolean
  due_count: number
  unlocked: boolean
}

export interface RetentionBand {
  accuracy: number | null
  samples: number
}

export interface ProgressSummary {
  retention: { d1: RetentionBand; d7: RetentionBand; d30: RetentionBand }
  bypass_rate: number | null
  calibration: number | null
}

export interface ProgressResponse {
  concepts: ConceptProgress[]
  summary: ProgressSummary
}

export interface HistoryReview {
  created_at: string
  concept_id: string
  item_id: string
  grade: number
  rating: string
  bypassed: boolean
  p_known_after: number | null
}

export interface HistoryResponse {
  days: number
  reviews: HistoryReview[]
}

export interface NextItem {
  id: string
  concept_id: string
  kind: 'mcq' | 'msq' | 'self_rated' | 'short_answer' | 'teach_back'
  prompt: string
  payload: { options?: string[] }
}

export interface NextResponse {
  items: NextItem[]
  reason: string | null
}

export interface TeamOverviewResponse {
  concepts: unknown[]
  people: { person_id: string; adherence: number; velocity: number; last_active: string | null; bypass_rate: number | null }[]
  retention: unknown
}

export interface TeamPersonResponse {
  person_id: string
  concepts: ConceptProgress[]
  adherence: number
  velocity: number
  due_count: number
  last_active: string | null
  bypass_rate: number | null
  retention: unknown
  calibration: number | null
}

export interface ReviewResult {
  grade: number
  rating: number
  correct: boolean
  explanation: string | null
  confidence: number | null
  bypassed: boolean
  next_due_at: string
  concept: { p_known: number; mastered: boolean }
}

export interface ReviewSubmission {
  item_id: string
  idempotency_key: string
  response: Record<string, unknown>
  confidence?: number | null
  bypassed?: boolean
}

async function errorFromResponse(response: Response): Promise<LearningApiError> {
  let code: string | undefined
  let message = response.statusText
  try {
    const body = (await response.json()) as { detail?: { code?: string; message?: string } }
    if (body?.detail?.code) code = body.detail.code
    if (body?.detail?.message) message = body.detail.message
  } catch {
    // non-JSON body — keep statusText
  }
  return new LearningApiError(response.status, code, message)
}

export class LearningClient {
  constructor(private readonly config: LearningClientConfig) {}

  private async request<T>(
    path: string,
    { method = 'GET', actingIdentity, body }: { method?: string; actingIdentity: string; body?: unknown },
  ): Promise<T> {
    const response = await fetch(`${this.config.baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.config.serviceToken}`,
        'X-Acting-Identity': actingIdentity,
        'Content-Type': 'application/json',
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) throw await errorFromResponse(response)
    return (await response.json()) as T
  }

  getProgress(actingIdentity: string): Promise<ProgressResponse> {
    return this.request('/me/progress', { actingIdentity })
  }

  getHistory(actingIdentity: string, days = 30): Promise<HistoryResponse> {
    return this.request(`/me/history?days=${days}`, { actingIdentity })
  }

  getNext(actingIdentity: string, limit = 1): Promise<NextResponse> {
    return this.request(`/me/next?limit=${limit}`, { actingIdentity })
  }

  getTeamOverview(actingIdentity: string): Promise<TeamOverviewResponse> {
    return this.request('/team/overview', { actingIdentity })
  }

  getTeamPerson(actingIdentity: string, personId: string): Promise<TeamPersonResponse> {
    return this.request(`/team/people/${personId}`, { actingIdentity })
  }

  submitReview(actingIdentity: string, submission: ReviewSubmission): Promise<ReviewResult> {
    return this.request('/me/reviews', { actingIdentity, method: 'POST', body: submission })
  }
}
