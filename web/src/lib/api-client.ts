/** Typed error carrying the service's status + error code, or 0 for a
 * browser-level network failure (the core unreachable, no response at all). */
export class ApiError extends Error {
  status: number
  code?: string
  body?: unknown

  constructor(status: number, code: string | undefined, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.body = body
  }
}

interface ApiFetchOptions {
  /** A real web session only ever has an `X-Acting-Identity` header value
   * to send — `web:<auth0 subject>` (contract change #7). */
  persona?: { header: string }
  method?: string
  body?: unknown
}

// The core raises `HTTPException(status_code=..., detail={"code", "message"})`,
// which FastAPI's default handler serialises as `{"detail": {"code", "message"}}`.
function errorPayload(body: unknown): Record<string, unknown> | undefined {
  if (!body || typeof body !== 'object') return undefined
  const record = body as Record<string, unknown>
  const detail = record.detail
  if (detail && typeof detail === 'object') return detail as Record<string, unknown>
  return record
}

function extractErrorCode(body: unknown): string | undefined {
  const code = errorPayload(body)?.code
  return typeof code === 'string' ? code : undefined
}

function extractErrorMessage(body: unknown, fallback: string): string {
  const message = errorPayload(body)?.message
  return typeof message === 'string' ? message : fallback
}

/**
 * The one shared API client, web app -> learning-service core. Every call
 * is proxied through `/api/*` (Vite's dev proxy locally, Caddy in prod),
 * which injects `WEB_SERVICE_TOKEN` server-side — the browser never holds
 * it, and never sends its own `Authorization` header (contract change #7:
 * "browsers never call the learning service directly").
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { persona, method = 'GET', body } = options
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (persona) headers['X-Acting-Identity'] = persona.header

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (cause) {
    throw new ApiError(0, 'network_error', 'API not reachable', { cause: String(cause) })
  }

  const text = await response.text()
  let json: unknown = null
  if (text) {
    try {
      json = JSON.parse(text)
    } catch {
      json = text
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, extractErrorCode(json), extractErrorMessage(json, response.statusText), json)
  }

  return json as T
}
