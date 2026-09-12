/**
 * `node --test` rather than vitest: this repo's web app ships no test runner
 * (`package.json` has no vitest), and the identity decision is plain
 * functions with an injected verifier — nothing here needs a DOM or a
 * bundler. Run with `npm run test:server`.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { resolveRuntimeIdentity, type RuntimeAuthConfig, type VerifyIdToken } from './identity.ts'

const BASE_CONFIG: RuntimeAuthConfig = {
  auth0Domain: 'kata-hackathon.us.auth0.com',
  auth0ClientId: 'client-abc',
}

const ISSUER = `https://${BASE_CONFIG.auth0Domain}/`

/** Records its calls so a test can assert what the runtime handed the verifier. */
function verifier(result: unknown): VerifyIdToken & { calls: string[] } {
  const calls: string[] = []
  const fn = async (token: string) => {
    calls.push(token)
    return result as never
  }
  return Object.assign(fn, { calls })
}

const never = () => verifier(null)

describe('resolveRuntimeIdentity', () => {
  it('rejects a request with neither a bypass header nor an Authorization header', async () => {
    assert.equal(await resolveRuntimeIdentity({}, BASE_CONFIG, never()), null)
  })

  it('rejects a Bearer token the verifier refuses, and passes it the raw token', async () => {
    const verify = verifier(null)
    assert.equal(
      await resolveRuntimeIdentity({ authorization: 'Bearer not-a-real-jwt' }, BASE_CONFIG, verify),
      null,
    )
    assert.deepEqual(verify.calls, ['not-a-real-jwt'])
  })

  it('rejects a non-Bearer Authorization scheme', async () => {
    assert.equal(
      await resolveRuntimeIdentity({ authorization: 'Basic aGk6dGhlcmU=' }, BASE_CONFIG, never()),
      null,
    )
  })

  it('rejects a verified token whose email is not verified', async () => {
    const verify = verifier({ email: 'hugo@ferry.example', email_verified: false, aud: 'client-abc', iss: ISSUER })
    assert.equal(await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify), null)
  })

  it('rejects a token minted for a different client id', async () => {
    const verify = verifier({ email: 'hugo@ferry.example', email_verified: true, aud: 'someone-else', iss: ISSUER })
    assert.equal(await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify), null)
  })

  it('rejects a token from a different issuer', async () => {
    const verify = verifier({
      email: 'hugo@ferry.example',
      email_verified: true,
      aud: 'client-abc',
      iss: 'https://evil.example/',
    })
    assert.equal(await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify), null)
  })

  it('accepts a verified token and normalizes the email into the session key', async () => {
    const verify = verifier({ email: '  Hugo@Ferry.Example ', email_verified: true, aud: 'client-abc', iss: ISSUER })
    assert.deepEqual(await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify), {
      email: 'hugo@ferry.example',
      sessionKey: 'web:hugo@ferry.example',
    })
  })

  it('accepts an aud array that contains the client id', async () => {
    const verify = verifier({
      email: 'hugo@ferry.example',
      email_verified: true,
      aud: ['client-abc', 'https://api.example/'],
      iss: ISSUER,
    })
    const identity = await resolveRuntimeIdentity({ authorization: 'Bearer x' }, BASE_CONFIG, verify)
    assert.equal(identity?.sessionKey, 'web:hugo@ferry.example')
  })

  it('accepts the e2e bypass pair without ever calling the verifier', async () => {
    const verify = verifier(null)
    const identity = await resolveRuntimeIdentity(
      { 'x-e2e-auth-bypass': 'shhh', 'x-e2e-learner-email': 'Dee@Ferry.Example' },
      { ...BASE_CONFIG, e2eBypassToken: 'shhh' },
      verify,
    )
    assert.deepEqual(identity, { email: 'dee@ferry.example', sessionKey: 'web:dee@ferry.example' })
    assert.deepEqual(verify.calls, [])
  })

  it('ignores a bypass header carrying the wrong token', async () => {
    const identity = await resolveRuntimeIdentity(
      { 'x-e2e-auth-bypass': 'wrong', 'x-e2e-learner-email': 'dee@ferry.example' },
      { ...BASE_CONFIG, e2eBypassToken: 'shhh' },
      never(),
    )
    assert.equal(identity, null)
  })

  it('ignores bypass headers entirely when no bypass token is configured', async () => {
    const identity = await resolveRuntimeIdentity(
      { 'x-e2e-auth-bypass': 'shhh', 'x-e2e-learner-email': 'dee@ferry.example' },
      BASE_CONFIG,
      never(),
    )
    assert.equal(identity, null)
  })
})
