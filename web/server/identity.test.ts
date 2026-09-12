import { describe, expect, it, vi } from 'vitest'
import { resolveRuntimeIdentity, type RuntimeAuthConfig, type VerifyIdToken } from './identity'

const BASE_CONFIG: RuntimeAuthConfig = {
  auth0Domain: 'kata-hackathon.us.auth0.com',
  auth0ClientId: 'client-abc',
}

function noVerify(): VerifyIdToken {
  return vi.fn().mockResolvedValue(null)
}

describe('resolveRuntimeIdentity', () => {
  it('rejects a request with neither a bypass header nor an Authorization header (curl with no session -> 401)', async () => {
    const identity = await resolveRuntimeIdentity({}, BASE_CONFIG, noVerify())
    expect(identity).toBeNull()
  })

  it('rejects a bare Bearer header with no token verifier result', async () => {
    const verify = vi.fn().mockResolvedValue(null)
    const identity = await resolveRuntimeIdentity({ authorization: 'Bearer not-a-real-jwt' }, BASE_CONFIG, verify)
    expect(identity).toBeNull()
    expect(verify).toHaveBeenCalledWith('not-a-real-jwt')
  })

  it('rejects a verified token whose email is not verified', async () => {
    const verify = vi.fn().mockResolvedValue({ email: 'hugo@ferry.example', email_verified: false })
    const identity = await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify)
    expect(identity).toBeNull()
  })

  it('rejects a verified token issued for a different Auth0 client (aud mismatch)', async () => {
    const verify = vi.fn().mockResolvedValue({
      email: 'hugo@ferry.example',
      email_verified: true,
      aud: 'someone-elses-client',
    })
    const identity = await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify)
    expect(identity).toBeNull()
  })

  it('rejects a verified token from a different issuer', async () => {
    const verify = vi.fn().mockResolvedValue({
      email: 'hugo@ferry.example',
      email_verified: true,
      aud: 'client-abc',
      iss: 'https://not-this-tenant.example/',
    })
    const identity = await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify)
    expect(identity).toBeNull()
  })

  it('accepts a fully verified token and normalizes+prefixes the email into a session key', async () => {
    const verify = vi.fn().mockResolvedValue({
      email: 'Hugo.Marchetti@Ferry.Example ',
      email_verified: true,
      aud: ['client-abc'],
      iss: 'https://kata-hackathon.us.auth0.com/',
    })
    const identity = await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify)
    expect(identity).toEqual({ email: 'hugo.marchetti@ferry.example', sessionKey: 'web:hugo.marchetti@ferry.example' })
  })

  it("never lets a browser-set header field pick the identity directly — only a verified token's own claims count", async () => {
    const verify = vi.fn().mockResolvedValue({
      email: 'real@ferry.example',
      email_verified: true,
      iss: 'https://kata-hackathon.us.auth0.com/',
    })
    const identity = await resolveRuntimeIdentity(
      { authorization: 'Bearer x', 'x-acting-identity': 'web:someone-else@ferry.example' },
      { auth0Domain: 'kata-hackathon.us.auth0.com' },
      verify,
    )
    expect(identity?.email).toBe('real@ferry.example')
  })

  describe('the e2e bypass', () => {
    const config: RuntimeAuthConfig = { e2eBypassToken: 'test-secret' }

    it('grants the named learner when the exact bypass token and an email are both present', async () => {
      const identity = await resolveRuntimeIdentity(
        { 'x-e2e-auth-bypass': 'test-secret', 'x-e2e-learner-email': 'quinn@ferry.example' },
        config,
        noVerify(),
      )
      expect(identity).toEqual({ email: 'quinn@ferry.example', sessionKey: 'web:quinn@ferry.example' })
    })

    it('refuses a wrong bypass token — a guess does not grant a session', async () => {
      const identity = await resolveRuntimeIdentity(
        { 'x-e2e-auth-bypass': 'guessed', 'x-e2e-learner-email': 'quinn@ferry.example' },
        config,
        noVerify(),
      )
      expect(identity).toBeNull()
    })

    it('is a no-op when this runtime has no bypass token configured, even if the headers are sent', async () => {
      const identity = await resolveRuntimeIdentity(
        { 'x-e2e-auth-bypass': 'test-secret', 'x-e2e-learner-email': 'quinn@ferry.example' },
        {},
        noVerify(),
      )
      expect(identity).toBeNull()
    })
  })
})
