/**
 * W10/AE-25: the small self-hosted CopilotKit runtime the popup talks to.
 * An ordinary turn forwards to Hermes's OpenAI-compatible API-server
 * platform (`POST $HERMES_API_URL/chat/completions`, `Authorization:
 * Bearer $HERMES_API_KEY`) and stamps the caller's identity as
 * `X-Hermes-Session-Key: web:<normalized email>` — the runtime holds the
 * key and does the stamping, never the browser (see `identity.ts`).
 *
 * `HERMES_API_URL` must include the API version prefix Hermes serves under
 * (e.g. `https://hermes-day.example.com/v1`) — the OpenAI SDK appends
 * `/chat/completions` itself.
 *
 * AE-25 adds a second lane: a turn that needs the person's own learning
 * data, a chart, or a review run is routed to OpenRouter instead
 * (`RoutingServiceAdapter`/`insight-router.ts`) and reads/writes the
 * learning service directly (`learning-client.ts`, `LEARNING_SERVICE_URL`/
 * `LEARNING_SERVICE_TOKEN` — the same trusted-caller shape the SPA's own
 * `/api/*` proxy already uses). `POST /copilotkit/review` is the one place
 * this runtime writes anything: it forwards straight to `/me/reviews`,
 * the same endpoint the Next-up screen's Submit/"Just tell me" already
 * call — no grading or bypass logic is reimplemented here.
 */
import http from 'node:http'
import { CopilotRuntime, OpenAIAdapter, copilotRuntimeNodeHttpEndpoint } from '@copilotkit/runtime'
import OpenAI from 'openai'
import { resolveRuntimeIdentity, type RuntimeAuthConfig } from './identity.js'
import { makeAuth0IdTokenVerifier } from './verify-auth0-id-token.js'
import { LearningApiError, LearningClient, type ReviewSubmission } from './learning-client.js'
import { RoutingServiceAdapter } from './insight-adapter.js'
import type { OpenRouterConfig } from './insight-data.js'

const PORT = Number(process.env.COPILOT_RUNTIME_PORT || 8090)
const ENDPOINT = '/copilotkit'
const REVIEW_ENDPOINT = '/copilotkit/review'

const authConfig: RuntimeAuthConfig = {
  auth0Domain: process.env.AUTH0_DOMAIN || undefined,
  auth0ClientId: process.env.AUTH0_CLIENT_ID || undefined,
  e2eBypassToken: process.env.E2E_AUTH_BYPASS_TOKEN || undefined,
}

const verifyIdToken = authConfig.auth0Domain
  ? makeAuth0IdTokenVerifier(authConfig.auth0Domain)
  : async () => null

// Insight lane config (AE-25). Both unset -> the lane silently degrades to
// "not configured" per turn rather than failing every request (missing
// key/URL only fails an insight turn at request time, same convention the
// learning service itself uses for OPENROUTER_API_KEY/LEARNING_LLM).
const learningServiceUrl = process.env.LEARNING_SERVICE_URL
const learningServiceToken = process.env.LEARNING_SERVICE_TOKEN
const learningClient =
  learningServiceUrl && learningServiceToken
    ? new LearningClient({ baseUrl: learningServiceUrl, serviceToken: learningServiceToken })
    : null

const openRouterApiKey = process.env.OPENROUTER_API_KEY
const openRouterConfig: OpenRouterConfig | null = openRouterApiKey
  ? { apiKey: openRouterApiKey, model: process.env.OPENROUTER_MODEL || 'openai/gpt-4o-mini' }
  : null

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

  if (req.url === REVIEW_ENDPOINT && req.method === 'POST') {
    await handleReviewSubmission(req, res)
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
  //
  // X-Hermes-Session-Id: without it, Hermes derives the session id from the
  // system prompt + first user message (gateway/platforms/
  // api_server_openai_routes.py::_derive_chat_session_id) — two learners
  // opening with the same text collide on one id, and the identity cache a
  // learning-tool call reads is keyed by that id (KATA-22). Stamping the
  // same stable per-learner value already used for the session *key* keeps
  // every one of a learner's own turns on the same conversation too.
  const openai = new OpenAI({
    apiKey: hermesApiKey,
    baseURL: hermesApiUrl,
    defaultHeaders: {
      'X-Hermes-Session-Key': identity.sessionKey,
      'X-Hermes-Session-Id': identity.sessionKey,
    },
  })
  const hermesAdapter = new OpenAIAdapter({ openai, model: 'hermes-agent' })
  // AE-25: the insight lane needs both the learning service and OpenRouter
  // configured — either missing, every turn stays on the Hermes-only
  // behaviour this popup shipped with (W10), rather than 401ing/500ing.
  const serviceAdapter = learningClient
    ? new RoutingServiceAdapter({ hermesAdapter, learningClient, actingIdentity: identity.sessionKey, openRouter: openRouterConfig })
    : hermesAdapter
  const runtime = new CopilotRuntime()
  const handler = copilotRuntimeNodeHttpEndpoint({ runtime, serviceAdapter, endpoint: ENDPOINT })
  await handler(req, res)
})

function readJsonBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = []
    req.on('data', (chunk) => chunks.push(chunk))
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8')
      if (!raw) return resolve(undefined)
      try {
        resolve(JSON.parse(raw))
      } catch (cause) {
        reject(cause)
      }
    })
    req.on('error', reject)
  })
}

function isReviewSubmission(body: unknown): body is ReviewSubmission {
  if (!body || typeof body !== 'object') return false
  const b = body as Record<string, unknown>
  return typeof b.item_id === 'string' && typeof b.idempotency_key === 'string' && typeof b.response === 'object' && b.response !== null
}

/**
 * AE-25: the chat review card's Submit/Bypass — the *only* write path this
 * runtime exposes, and it is a straight passthrough to `POST /me/reviews`
 * (`learning_service/reviews.py`), the same endpoint the Next-up screen's
 * Submit/"Just tell me" call. No grading or bypass logic lives here.
 */
async function handleReviewSubmission(req: http.IncomingMessage, res: http.ServerResponse): Promise<void> {
  if (!learningClient) {
    res.writeHead(503, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'runtime not configured: LEARNING_SERVICE_URL/LEARNING_SERVICE_TOKEN unset' }))
    return
  }

  const identity = await resolveRuntimeIdentity(req.headers, authConfig, verifyIdToken)
  if (!identity) {
    res.writeHead(401, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'unauthorized' }))
    return
  }

  let body: unknown
  try {
    body = await readJsonBody(req)
  } catch {
    res.writeHead(400, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'invalid JSON body' }))
    return
  }
  if (!isReviewSubmission(body)) {
    res.writeHead(422, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'expected {item_id, idempotency_key, response}' }))
    return
  }

  try {
    const result = await learningClient.submitReview(identity.sessionKey, body)
    res.writeHead(200, { 'content-type': 'application/json' })
    res.end(JSON.stringify(result))
  } catch (error) {
    if (error instanceof LearningApiError) {
      res.writeHead(error.status, { 'content-type': 'application/json' })
      res.end(JSON.stringify({ error: error.code ?? 'learning_service_error', message: error.message }))
      return
    }
    res.writeHead(502, { 'content-type': 'application/json' })
    res.end(JSON.stringify({ error: 'learning_service_unreachable' }))
  }
}

server.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`Kata CopilotKit runtime listening on :${PORT}${ENDPOINT}`)
})
