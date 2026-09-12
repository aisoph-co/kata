import { createRemoteJWKSet, jwtVerify } from 'jose'
import type { VerifiedIdTokenClaims, VerifyIdToken } from './identity.js'

/** Real Auth0 verification, split out from `identity.ts` so the identity
 * decision logic stays unit-testable without a network call or a live
 * tenant (`identity.test.ts` passes a fake `VerifyIdToken` instead). */
export function makeAuth0IdTokenVerifier(domain: string): VerifyIdToken {
  const issuer = `https://${domain}/`
  const jwks = createRemoteJWKSet(new URL(`${issuer}.well-known/jwks.json`))

  return async (token) => {
    try {
      const { payload } = await jwtVerify(token, jwks, { issuer })
      return payload as VerifiedIdTokenClaims
    } catch {
      return null
    }
  }
}
