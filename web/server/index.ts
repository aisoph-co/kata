/**
 * W10: the small self-hosted CopilotKit runtime the popup talks to. Forwards
 * every turn to Hermes's OpenAI-compatible API-server platform
 * (`POST $HERMES_API_URL/chat/completions`, `Authorization: Bearer
 * $HERMES_API_KEY`) and stamps the caller's identity as
 * `X-Hermes-Session-Key: web:<normalized email>` — the runtime holds the
 * key and does the stamping, never the browser (see `identity.ts`).
 *
 * `HERMES_API_URL` must include the API version prefix Hermes serves under
 * (e.g. `https://hermes-day.example.com/v1`) — the OpenAI SDK appends
 * `/chat/completions` itself.
 */
import http from 'node:http'
import { CopilotRuntime, OpenAIAdapter, copilotRuntimeNodeHttpEndpoint } from '@copilotkit/runtime'
import OpenAI from 'openai'
import { resolveRuntimeIdentity, type RuntimeAuthConfig } from './identity.js'
import { makeAuth0IdTokenVerifier } from './verify-auth0-id-token.js'

const PORT = Number(process.env.COPILOT_RUNTIME_PORT || 8090)
const ENDPOINT = '/copilotkit'

const authConfig: RuntimeAuthConfig = {
  auth0Domain: process.env.AUTH0_DOMAIN || undefined,
  auth0ClientId: process.env.AUTH0_CLIENT_ID || undefined,
  e2eBypassToken: process.env.E2E_AUTH_BYPASS_TOKEN || undefined,
}

const verifyIdToken = authConfig.auth0Domain
  ? makeAuth0IdTokenVerifier(authConfig.auth0Domain)
  : async () => null

// Limited to the web app's own origin, same intent as Hermes's own
// `API_SERVER_CORS_ORIGINS` — a browser is the only caller this runtime
// expects, and only from the one deployed SPA.
const allowedOrigin = process.env.WEB_BASE_URL || ''

function applyCorsHeaders(req: http.IncomingMessage, res: http.ServerResponse): void {
  const origin = req.headers.origin
  if (allowedOrigin && origin === allowedOrigin) {
    res.setHeader('Access-Control-Allow-Origin', allowedOrigin)
    res.setHeader('Vary', 'Origin')
  }
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
  res.setHeader(
    'Access-Control-Allow-Headers',
    'Authorization, Content-Type, X-E2E-Auth-Bypass, X-E2E-Learner-Email',
  )
}

const server = http.createServer(async (req, res) => {
  applyCorsHeaders(req, res)
  if (req.method === 'OPTIONS') {
    res.writeHead(204)
    res.end()
    return
  }

  if (req.url === '/healthz') {
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ status: 'ok' }))
    return
  }

  if (req.url !== ENDPOINT || req.method !== 'POST') {
    res.writeHead(404)
    res.end()
    return
  }

  const hermesApiUrl = process.env.HERMES_API_URL
  const hermesApiKey = process.env.HERMES_API_KEY
  if (!hermesApiUrl || !hermesApiKey) {
    res.writeHead(503, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'runtime not configured: HERMES_API_URL/HERMES_API_KEY unset' }))
    return
  }

  const identity = await resolveRuntimeIdentity(req.headers, authConfig, verifyIdToken)
  if (!identity) {
    res.writeHead(401, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'unauthorized' }))
    return
  }

  // Built fresh per request: the only thing that varies call to call is the
  // identity header, and a shared client built once at startup would mean
  // every caller after the first shares whoever made that first request.
  const openai = new OpenAI({
    apiKey: hermesApiKey,
    baseURL: hermesApiUrl,
    defaultHeaders: { 'X-Hermes-Session-Key': identity.sessionKey },
  })
  const serviceAdapter = new OpenAIAdapter({ openai, model: 'hermes-agent' })
  const runtime = new CopilotRuntime()
  const handler = copilotRuntimeNodeHttpEndpoint({ runtime, serviceAdapter, endpoint: ENDPOINT })
  await handler(req, res)
})

server.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`Kata CopilotKit runtime listening on :${PORT}${ENDPOINT}`)
})
