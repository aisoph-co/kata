/**
 * AE-25 insight lane: turns a classified `InsightIntent` into a chat reply
 * — real numbers fetched from the learning service, phrased by OpenRouter,
 * plus (for a chart/review-card intent) the authoritative payload for the
 * matching frontend action. The payload always comes straight from the
 * learning service response, never from anything OpenRouter generates —
 * OpenRouter only writes the sentence around it, so a model slip can never
 * put a wrong number on screen (PLAN_15: chart/table values must match the
 * Progress page exactly).
 */
import OpenAI from 'openai'
import { conceptTitle } from './concepts.js'
import { LearningApiError, type LearningClient } from './learning-client.js'
import type { InsightIntent } from './insight-router.js'

export interface OpenRouterConfig {
  apiKey: string
  model: string
}

export interface InsightAction {
  name: string
  args: Record<string, unknown>
}

export interface InsightReply {
  text: string
  action: InsightAction | null
}

export interface InsightContext {
  learningClient: LearningClient
  actingIdentity: string
  openRouter: OpenRouterConfig | null
  userText: string
}

const OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'

function pct(value: number | null): string {
  return value === null ? 'not enough data yet' : `${Math.round(value * 100)}%`
}

/** OpenRouter phrases the final sentence from `dataSummary` alone — told,
 * in the system prompt, to use only the numbers it was given. Falls back to
 * `fallback` (a plain, always-correct template) if no key is configured or
 * the call fails, so a missing/broken key degrades the wording, never the
 * numbers or the turn itself. */
async function phrase(openRouter: OpenRouterConfig | null, userText: string, dataSummary: string, fallback: string): Promise<string> {
  if (!openRouter) return fallback
  try {
    const client = new OpenAI({ apiKey: openRouter.apiKey, baseURL: OPENROUTER_BASE_URL })
    const completion = await client.chat.completions.create({
      model: openRouter.model,
      messages: [
        {
          role: 'system',
          content:
            'You are the Kata learning coach, replying inside a chat popup. ' +
            'Answer the question in 1-3 short sentences using ONLY the numbers given below — ' +
            'never invent or adjust a number, never add numbers that are not given. No markdown tables.',
        },
        { role: 'user', content: `Question: ${userText}\n\nData:\n${dataSummary}` },
      ],
      temperature: 0.3,
      max_tokens: 200,
    })
    const content = completion.choices[0]?.message?.content?.trim()
    return content || fallback
  } catch {
    return fallback
  }
}

/** `403`/`404` from the learning service, phrased without ever naming what
 * was being looked up — PLAN_15: a refusal must never leak that the person
 * asked-about exists, has reports, or anything else about them. */
function messageForApiError(error: LearningApiError): string {
  switch (error.code) {
    case 'unknown_identity':
      return "I can't tell who's asking, so I can't look anything up right now — try signing in again."
    case 'not_a_manager':
    case 'outside_subtree':
      return "I can only show you your own numbers — I don't have manager access to anyone else's."
    default:
      return "I couldn't reach your learning data just now — try again in a moment."
  }
}

export async function buildInsightReply(intent: InsightIntent, ctx: InsightContext): Promise<InsightReply> {
  const { learningClient, actingIdentity, openRouter, userText } = ctx
  try {
    switch (intent.kind) {
      case 'self_summary':
        return await selfSummary(learningClient, actingIdentity, openRouter, userText)
      case 'weakest':
        return await weakest(learningClient, actingIdentity, openRouter, userText)
      case 'mastery_chart':
        return await masteryChart(learningClient, actingIdentity)
      case 'trend_chart':
        return await trendChart(learningClient, actingIdentity)
      case 'next_review':
        return await nextReview(learningClient, actingIdentity)
      case 'team_summary':
        return await teamSummary(learningClient, actingIdentity, openRouter, userText)
      case 'person_summary':
        return await personSummary(learningClient, actingIdentity, intent.person, openRouter, userText)
    }
  } catch (error) {
    if (error instanceof LearningApiError) return { text: messageForApiError(error), action: null }
    return { text: "I couldn't reach your learning data just now — try again in a moment.", action: null }
  }
}

async function selfSummary(
  learningClient: LearningClient,
  actingIdentity: string,
  openRouter: OpenRouterConfig | null,
  userText: string,
): Promise<InsightReply> {
  const progress = await learningClient.getProgress(actingIdentity)
  const { retention, bypass_rate, calibration } = progress.summary
  const masteredCount = progress.concepts.filter((c) => c.mastered).length
  const dataSummary =
    `Retention — 1 day: ${pct(retention.d1.accuracy)}, 7 day: ${pct(retention.d7.accuracy)}, 30 day: ${pct(retention.d30.accuracy)}. ` +
    `Mastery: ${masteredCount} of ${progress.concepts.length} concepts mastered. ` +
    `Bypass rate: ${pct(bypass_rate)}. ` +
    `Calibration: ${calibration === null ? 'not enough data yet' : calibration.toFixed(2)} (positive = over-confident, negative = under-confident).`
  const fallback = `Here's where you stand: ${dataSummary}`
  return { text: await phrase(openRouter, userText, dataSummary, fallback), action: null }
}

async function weakest(
  learningClient: LearningClient,
  actingIdentity: string,
  openRouter: OpenRouterConfig | null,
  userText: string,
): Promise<InsightReply> {
  const progress = await learningClient.getProgress(actingIdentity)
  const unlocked = progress.concepts.filter((c) => c.unlocked)
  if (unlocked.length === 0) {
    return { text: "You don't have any concepts unlocked yet, so there's nothing to compare.", action: null }
  }
  const weakest = unlocked.reduce((a, b) => (b.p_known < a.p_known ? b : a))
  const dataSummary = `Weakest unlocked concept: ${conceptTitle(weakest.concept_id)}, mastery ${pct(weakest.p_known)}, ${weakest.due_count} due now.`
  const fallback = `Your weakest spot right now is ${conceptTitle(weakest.concept_id)}, at ${pct(weakest.p_known)} mastery.`
  return { text: await phrase(openRouter, userText, dataSummary, fallback), action: null }
}

async function masteryChart(learningClient: LearningClient, actingIdentity: string): Promise<InsightReply> {
  const progress = await learningClient.getProgress(actingIdentity)
  const concepts = progress.concepts
    .slice()
    .sort((a, b) => b.p_known - a.p_known)
    .map((c) => ({ concept_id: c.concept_id, p_known: c.p_known, unlocked: c.unlocked }))
  return {
    text: "Here's your mastery across every concept:",
    action: { name: 'showMasteryChart', args: { concepts } },
  }
}

const CHART_DAYS = 30

async function trendChart(learningClient: LearningClient, actingIdentity: string): Promise<InsightReply> {
  const [progress, history] = await Promise.all([
    learningClient.getProgress(actingIdentity),
    learningClient.getHistory(actingIdentity, CHART_DAYS),
  ])
  const reviewCountByConcept = new Map<string, number>()
  for (const r of history.reviews) reviewCountByConcept.set(r.concept_id, (reviewCountByConcept.get(r.concept_id) ?? 0) + 1)

  const mostReviewed = [...reviewCountByConcept.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]
  const conceptId = mostReviewed ?? progress.concepts[0]?.concept_id
  if (!conceptId) return { text: "You don't have any review history yet, so there's no trend to chart.", action: null }

  const conceptReviews = history.reviews.filter((r) => r.concept_id === conceptId)
  return {
    text: `Here's your ${conceptTitle(conceptId)} progress over the last ${CHART_DAYS} days:`,
    action: {
      name: 'showPKnownTrend',
      args: { conceptId, conceptTitle: conceptTitle(conceptId), days: CHART_DAYS, reviews: conceptReviews },
    },
  }
}

async function nextReview(learningClient: LearningClient, actingIdentity: string): Promise<InsightReply> {
  const next = await learningClient.getNext(actingIdentity, 1)
  const item = next.items[0]
  if (!item) {
    const reason =
      next.reason === 'all_mastered'
        ? "you've mastered everything that's unlocked right now"
        : next.reason === 'blocked_by_prerequisites'
          ? 'the rest is still locked behind prerequisites'
          : 'nothing is due right now'
    return { text: `Nothing to review — ${reason}.`, action: null }
  }
  return {
    text: `Here's your next one, on ${conceptTitle(item.concept_id)}:`,
    action: { name: 'showReviewCard', args: { item } },
  }
}

async function teamSummary(
  learningClient: LearningClient,
  actingIdentity: string,
  openRouter: OpenRouterConfig | null,
  userText: string,
): Promise<InsightReply> {
  const overview = await learningClient.getTeamOverview(actingIdentity)
  const people = overview.people
  if (people.length === 0) {
    return { text: "Your team overview doesn't have anyone in it yet.", action: null }
  }
  const bypassRates = people.map((p) => p.bypass_rate).filter((v): v is number => v !== null)
  const avgBypass = bypassRates.length ? bypassRates.reduce((a, b) => a + b, 0) / bypassRates.length : null
  const avgAdherence = people.reduce((a, b) => a + b.adherence, 0) / people.length
  const dataSummary = `Team size: ${people.length}. Average adherence: ${pct(avgAdherence)}. Average bypass rate: ${pct(avgBypass)}.`
  const fallback = `Your team: ${dataSummary}`
  return { text: await phrase(openRouter, userText, dataSummary, fallback), action: null }
}

async function personSummary(
  learningClient: LearningClient,
  actingIdentity: string,
  person: { firstName: string; personId: string },
  openRouter: OpenRouterConfig | null,
  userText: string,
): Promise<InsightReply> {
  const summary = await learningClient.getTeamPerson(actingIdentity, person.personId)
  const masteredCount = summary.concepts.filter((c) => c.mastered).length
  const dataSummary =
    `${person.firstName}: mastery ${masteredCount} of ${summary.concepts.length} concepts, ` +
    `adherence ${pct(summary.adherence)}, bypass rate ${pct(summary.bypass_rate)}, due count ${summary.due_count}.`
  const fallback = `${dataSummary}`
  return { text: await phrase(openRouter, userText, dataSummary, fallback), action: null }
}
