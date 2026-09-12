/**
 * Who a CopilotKit turn runs as — resolved here, server-side, before the
 * turn ever reaches Hermes (W10's "one real design point": the person the
 * popup acts as is always the person who signed in, never anything the
 * browser can set).
 *
 * Two paths, both reused from W1/Caddy rather than invented fresh for this
 * runtime:
 *
 * - The e2e bypass (`E2E_AUTH_BYPASS_TOKEN`, AGCTM-64/finding #5): the same
 *   header pair Caddy's `/__e2e/session` route already trusts. The test
 *   harness attaches these to every request it makes on a browser context
 *   (see `useE2ESession`'s doc comment), including the ones this runtime
 *   receives directly — no app code has to forward them.
 * - A real session: the raw Auth0 ID token the browser already holds,
 *   verified against the tenant's JWKS. `email_verified`, `aud`, and `iss`
 *   are checked exactly as `SessionGate`'s `RequireAuth0Session` already
 *   checks `email_verified` client-side — this is that same gate, run again
 *   here because the frontend can't be trusted to have run it honestly.
 */

export interface RuntimeAuthConfig {
  auth0Domain?: string
  auth0ClientId?: string
  e2eBypassToken?: string
}

export interface RuntimeIdentity {
  /** Normalized email — the same normalization W1 applies before
   * `POST /identities/resolve` (trim + lowercase). */
  email: string
  /** `web:<email>` — stamped onto every Hermes request as
   * `X-Hermes-Session-Key`, so `pre_gateway_dispatch` sees the same shape
   * of value every other platform's `event.source.user_id` carries. */
  sessionKey: string
}

export interface VerifiedIdTokenClaims {
  email?: string
  email_verified?: boolean
  aud?: string | string[]
  iss?: string
}

/** Verify a raw ID token's signature and return its claims, or `null` if
 * the token is missing, expired, or fails verification. Never throws. */
export type VerifyIdToken = (token: string) => Promise<VerifiedIdTokenClaims | null>

export type HeaderBag = Record<string, string | string[] | undefined>

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase()
}

function toIdentity(email: string): RuntimeIdentity {
  const normalized = normalizeEmail(email)
  return { email: normalized, sessionKey: `web:${normalized}` }
}

function headerValue(headers: HeaderBag, name: string): string | undefined {
  const value = headers[name]
  return Array.isArray(value) ? value[0] : value
}

export async function resolveRuntimeIdentity(
  headers: HeaderBag,
  config: RuntimeAuthConfig,
  verifyIdToken: VerifyIdToken,
): Promise<RuntimeIdentity | null> {
  if (config.e2eBypassToken) {
    const sent = headerValue(headers, 'x-e2e-auth-bypass')
    const email = headerValue(headers, 'x-e2e-learner-email')
    if (sent === config.e2eBypassToken && email) {
      return toIdentity(email)
    }
  }

  const authHeader = headerValue(headers, 'authorization') ?? ''
  const [scheme, token] = authHeader.split(' ', 2)
  if (!token || scheme?.toLowerCase() !== 'bearer') return null

  const claims = await verifyIdToken(token)
  if (!claims || claims.email_verified !== true || !claims.email) return null

  if (config.auth0ClientId) {
    const aud = Array.isArray(claims.aud) ? claims.aud : claims.aud ? [claims.aud] : []
    if (!aud.includes(config.auth0ClientId)) return null
  }
  if (config.auth0Domain && claims.iss !== `https://${config.auth0Domain}/`) return null

  return toIdentity(claims.email)
}
