import { recordBackstageCall } from './backstage-store'

/** Typed error carrying the service's status + error code, or 0 for a network failure. */
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

  /**
   * True when the service could not be reached at all — a browser-level
   * network failure (status 0), or the Vite dev proxy's own 502/503/504
   * when the upstream API refuses the connection (the common case; the
   * proxy answers the browser itself rather than letting fetch throw).
   */
  get isUnreachable(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504
  }
}

interface ApiFetchOptions {
  // Structural, not the full `Persona` shape — callers only ever need to
  // supply an `X-Acting-Identity` header value, no avatar/roles/etc.
  persona?: { header: string }
  method?: string
  body?: unknown
}

function redactHeaders(headers: Record<string, string>): Record<string, string> {
  const redacted: Record<string, string> = {}
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() === 'authorization') continue
    redacted[key] = value
  }
  return redacted
}

// The service raises `HTTPException(status_code=..., detail={"code", "message"})`,
// which FastAPI's default handler serialises as `{"detail": {"code", "message"}}`.
// A couple of alternate shapes are tolerated defensively.
function errorPayload(body: unknown): Record<string, unknown> | undefined {
  if (!body || typeof body !== 'object') return undefined
  const record = body as Record<string, unknown>
  const detail = record.detail
  if (detail && typeof detail === 'object') return detail as Record<string, unknown>
  const error = record.error
  if (error && typeof error === 'object') return error as Record<string, unknown>
  return record
}

function extractErrorCode(body: unknown): string | undefined {
  const payload = errorPayload(body)
  const code = payload?.code
  return typeof code === 'string' ? code : undefined
}

function extractErrorMessage(body: unknown, fallback: string): string {
  const payload = errorPayload(body)
  const message = payload?.message
  return typeof message === 'string' ? message : fallback
}

/**
 * The one shared API client. Every call is proxied through Vite's /api → the
 * service; the proxy injects the bearer token so the browser never sees it.
 * Every call — success or failure — is recorded into the Backstage store.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { persona, method = 'GET', body } = options
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (persona) headers['X-Acting-Identity'] = persona.header

  const started = performance.now()

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (cause) {
    const durationMs = performance.now() - started
    recordBackstageCall({
      method,
      path,
      headers: redactHeaders(headers),
      body,
      status: 0,
      response: { error: 'network_error', message: 'API not reachable' },
      durationMs,
    })
    throw new ApiError(0, 'network_error', 'API not reachable — run `npm run demo`', {
      cause: String(cause),
    })
  }

  const durationMs = performance.now() - started
  const text = await response.text()
  let json: unknown = null
  if (text) {
    try {
      json = JSON.parse(text)
    } catch {
      json = text
    }
  }

  recordBackstageCall({
    method,
    path,
    headers: redactHeaders(headers),
    body,
    status: response.status,
    response: json,
    durationMs,
  })

  if (!response.ok) {
    throw new ApiError(
      response.status,
      extractErrorCode(json),
      extractErrorMessage(json, response.statusText),
      json,
    )
  }

  return json as T
}
