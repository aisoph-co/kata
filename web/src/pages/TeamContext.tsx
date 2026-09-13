import { useQueries, useQuery } from '@tanstack/react-query'
import cytoscape from 'cytoscape'
import { ArrowRight, Loader2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ApiStatusBanner } from '@/components/ApiStatusBanner'
import {
  buildElements,
  computeChain,
  FADE_EASING,
  FADE_MS,
  resolveThemeColors,
  startNextPulse,
  stylesheet,
  type GraphEdgeInput,
  type GraphNodeInput,
  type ThemeColors,
} from '@/components/concept-map/graph'
import { DataState } from '@/components/DataState'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiQuery } from '@/hooks/useApiQuery'
import { useLangPath } from '@/hooks/useLangPath'
import { apiFetch } from '@/lib/api-client'
import { useConnectState, PLATFORMS } from '@/lib/connect-store'
import { conceptTitle } from '@/lib/ferry-scenario'
import { formatElapsed, formatPercent, masteryTier } from '@/lib/format'
import { INGESTION_SOURCES, streamIngestion, type IngestedConcept } from '@/lib/ingestion-sources'
import { PERSONAS } from '@/lib/personas'
import { usePersona } from '@/lib/persona-store'
import { cn } from '@/lib/utils'

// Team context (demo beat 0): GET /me/concept-graph returns the 14
// curriculum nodes + 21 edges. The acting persona's own /topics highlights
// their concepts teal. The bottom row is always Hugo/Daniel/Shane's real
// topics (contract v1.2.1 carries their source citations), matching the
// AGCTM-56 mock's frame 02 exactly.
const BOTTOM_TOPIC_PERSONAS = ['hugo', 'daniel', 'shane'].map((id) => PERSONAS.find((p) => p.id === id)!)

interface GraphNode {
  concept_id: string
  slug: string
  title: string
  p_known: number
  mastered: boolean
  unlocked: boolean
}

interface GraphEdge {
  from_concept_id: string
  to_concept_id: string
  kind: 'prerequisite' | 'related'
  weight: number
}

interface Topic {
  id: string
  slug: string
  title: string
  description: string
  persona_role: string
  entry_concept_id: string
  concept_ids: string[]
  grounded_in: string[]
}

interface ProgressConcept {
  concept_id: string
  due_count: number
}

const NODE_SIZE_HALF_GUESS = 90
const TOOLTIP_WIDTH = 300

const DOT_GRID_STYLE = {
  backgroundImage: 'radial-gradient(color-mix(in oklch, var(--foreground) 12%, transparent) 1px, transparent 1px)',
  backgroundSize: '18px 18px',
}

declare global {
  interface Window {
    __kataGraph?: { nodeCount: number; edgeCount: number; highlighted: string[] }
  }
}
type KataGraphDebug = NonNullable<Window['__kataGraph']>
// Not gated on import.meta.env.DEV: this also has to be readable against
// the built-and-served (Docker/Caddy) production bundle, where DEV is
// always false. The value carries nothing sensitive (node/edge counts,
// concept ids already visible in the graph and in API responses).
function setKataGraphDebug(value: KataGraphDebug) {
  window.__kataGraph = value
}
function clearKataGraphDebug() {
  delete window.__kataGraph
}

/** Left "Connect team context" panel — reads Connect's localStorage state
 * only (PLAN_08's one deliberate mock), never the API. Renders a fixed row
 * per platform (never just the connected ones) so disconnecting a source
 * flips its own row to "Connect →" instead of the row disappearing. */
function ConnectPanel() {
  const { t } = useTranslation()
  const langPath = useLangPath()
  const connected = useConnectState()
  const connectedCount = PLATFORMS.filter((p) => connected[p.id]).length

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-5">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-semibold">{t('teamContext.connectPanelTitle')}</h2>
          <span className="rounded-full bg-kata-teal-2 px-2.5 py-0.5 text-xs font-semibold text-kata-teal-3">
            {t('teamContext.sourcesCount', { count: connectedCount })}
          </span>
        </div>

        <ul className="flex flex-col" data-testid="team-context-sources">
          {PLATFORMS.map((platform) => {
            const isOn = !!connected[platform.id]
            return (
              <li key={platform.id} className="flex items-center gap-3 border-b py-2.5 text-sm last:border-b-0" data-testid={`source-row-${platform.id}`}>
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                  {platform.name.toLowerCase().replace(/\s+/g, '-')}
                </span>
                {isOn ? (
                  <>
                    <span className="text-muted-foreground">
                      {platform.stats.threads} {platform.statLabelOverride?.threads ?? t('connect.stat.threads')}
                    </span>
                    <span className="ml-auto text-xs font-semibold text-kata-good">{t('teamContext.connectedTag')}</span>
                  </>
                ) : (
                  <Link
                    to={langPath('/connect')}
                    data-testid={`source-connect-${platform.id}`}
                    className="ml-auto flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                  >
                    {t('teamContext.connectCta')} <ArrowRight className="size-3" />
                  </Link>
                )}
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}

type IngestStatus = 'idle' | 'running' | 'empty' | 'done' | 'error'

/** Ingestion-source list (KATA-11): repo, issues, releases, Slack, Exa,
 * each with a count derived from the loaded `LEARNING_SEED=ferry` fixtures,
 * plus a live-ticking "ingesting" badge. Renders from the already-loaded
 * seed by default — the "Ingest now" action (KATA-22/CI1) is the "Connect
 * team context" action's real trigger: it calls `GET /admin/ingest` and
 * streams real `concept` rows into the list below as they're produced. */
function IngestionSourcesPanel() {
  const { t } = useTranslation()
  const active = usePersona()
  const [elapsedMs, setElapsedMs] = useState(0)
  const [status, setStatus] = useState<IngestStatus>('idle')
  const [liveConcepts, setLiveConcepts] = useState<IngestedConcept[]>([])
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  // `GET /admin/ingest` is operator-gated server-side (same as every other
  // `/admin/*` route) — only Quinn carries the `operator` role in the Ferry
  // seed (`fixtures/ferry/roster.json`'s only `is_operator: true` row), so
  // the trigger is hidden rather than shown to 403 for everyone else.
  const isOperator = active.roles.includes('operator')

  useEffect(() => {
    const id = setInterval(() => setElapsedMs((ms) => ms + 1000), 1000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    // Aborts an in-flight stream if the persona switches or the screen
    // unmounts mid-run, so a stale stream can't keep writing state after.
    return () => abortRef.current?.abort()
  }, [])

  function triggerIngestion() {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setStatus('running')
    setLiveConcepts([])
    setErrorMessage(null)
    void streamIngestion(
      active,
      (event) => {
        if (event.type === 'concept') setLiveConcepts((prev) => [...prev, event.concept])
        else if (event.type === 'empty') setStatus('empty')
        else if (event.type === 'done') setStatus('done')
        else if (event.type === 'error') {
          setStatus('error')
          setErrorMessage(event.message)
        }
      },
      controller.signal,
    )
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 pt-5">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-base font-semibold">{t('teamContext.ingestionPanelTitle')}</h2>
          <span
            className="rounded-full bg-kata-warn-2 px-2.5 py-0.5 text-xs font-semibold text-kata-warn"
            data-testid="ingesting-badge"
          >
            {t('teamContext.ingestingBadge', { time: formatElapsed(elapsedMs) })}
          </span>
        </div>

        <ul className="flex flex-col" data-testid="ingestion-sources">
          {INGESTION_SOURCES.map((source) => (
            <li
              key={source.id}
              className="flex items-center gap-3 border-b py-2.5 text-sm last:border-b-0"
              data-testid={`ingestion-source-${source.id}`}
            >
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">{source.id}</span>
              <span className="text-muted-foreground">{source.label}</span>
              <span className="ml-auto text-xs font-semibold" data-testid={`ingestion-source-count-${source.id}`}>
                {source.id === 'issues' && liveConcepts.length > 0
                  ? t('teamContext.ingestConceptCount', { count: liveConcepts.length })
                  : source.count}
              </span>
            </li>
          ))}
        </ul>

        {isOperator && (
          <div className="flex flex-col gap-2 border-t pt-3">
            <Button
              size="sm"
              variant="outline"
              className="self-start"
              disabled={status === 'running'}
              onClick={triggerIngestion}
              data-testid="ingest-trigger"
            >
              {status === 'running' && <Loader2 className="mr-1.5 size-3.5 animate-spin" />}
              {t('teamContext.ingestTrigger')}
            </Button>

            {(status === 'running' || status === 'done') && liveConcepts.length > 0 && (
              <ul className="flex flex-col gap-1" data-testid="ingested-concepts">
                {liveConcepts.map((concept) => (
                  <li
                    key={concept.id}
                    className="rounded bg-muted/60 px-2 py-1 font-mono text-xs"
                    data-testid={`ingested-concept-${concept.slug}`}
                  >
                    {concept.title}
                  </li>
                ))}
              </ul>
            )}

            {status === 'empty' && (
              <p className="text-xs text-muted-foreground" data-testid="ingest-empty">
                {t('teamContext.ingestEmpty')}
              </p>
            )}

            {status === 'done' && (
              <p className="text-xs text-kata-good" data-testid="ingest-done">
                {t('teamContext.ingestDone', { count: liveConcepts.length })}
              </p>
            )}

            {status === 'error' && (
              <p className="text-xs text-destructive" data-testid="ingest-error">
                {t('teamContext.ingestError', { message: errorMessage })}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Small per-line delay so STREAM lines fade in one after another instead
// of all at once — still a single shared fade duration/easing, just staggered.
const STREAM_STAGGER_MS = 70

/** Replays a handful of grounded facts about the curriculum as a streaming
 * log, on every mount — a decorative echo of what /me/concept-graph and
 * /topics actually returned, not a live feed. */
function StreamLog({
  nodeCount,
  edgeCount,
  relatedCount,
  reducedMotion,
}: {
  nodeCount: number
  edgeCount: number
  relatedCount: number
  reducedMotion: boolean
}) {
  const { t } = useTranslation()
  const lines = useMemo(
    () => [
      t('teamContext.streamLine1', { nodes: nodeCount, edges: edgeCount, related: relatedCount }),
      t('teamContext.streamLine2'),
      t('teamContext.streamLine3'),
      t('teamContext.streamLine4'),
      t('teamContext.streamLine5'),
    ],
    [t, nodeCount, edgeCount, relatedCount],
  )

  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {t('teamContext.streamTitle')}
      </p>
      <div className="rounded-lg bg-muted/60 px-3.5 py-3 font-mono text-xs leading-7 text-muted-foreground" data-testid="stream-log">
        {lines.map((line, i) => (
          <p
            key={i}
            className={cn(!reducedMotion && 'animate-in fade-in fill-mode-backwards ease-out duration-[250ms]')}
            style={!reducedMotion ? { animationDelay: `${i * STREAM_STAGGER_MS}ms` } : undefined}
          >
            <span className="text-kata-good">✓</span> {line}
          </p>
        ))}
      </div>
    </div>
  )
}

function TopicCard({ persona, topic }: { persona: (typeof BOTTOM_TOPIC_PERSONAS)[number]; topic?: Topic }) {
  const { t } = useTranslation()
  const langPath = useLangPath()
  if (!topic) {
    return (
      <Card className="border-dashed">
        <CardContent className="pt-5">
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    )
  }
  return (
    <Card data-testid={`topic-card-${persona.id}`}>
      <CardContent className="flex flex-col gap-2 pt-5">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span
            className="flex size-5 items-center justify-center rounded-full text-[10px] font-semibold text-white"
            style={{ backgroundColor: persona.avatarColor }}
          >
            {persona.name.slice(0, 2).toUpperCase()}
          </span>
          {persona.name} · {t(`personaBar.role.${persona.role}`)}
        </div>
        <p className="font-heading text-sm font-semibold leading-snug">{topic.title}</p>
        <div className="flex flex-wrap gap-1.5">
          {topic.concept_ids.slice(0, 3).map((id) => (
            <code key={id} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
              {conceptTitle(id)}
            </code>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground" data-testid="topic-grounded-in">
          {t('teamContext.groundedInLabel')}
          {topic.grounded_in.map((artifact) => (
            <Link
              key={artifact}
              to={langPath(`/source/${encodeURIComponent(artifact)}`)}
              className="rounded bg-muted px-1.5 py-0.5 font-mono text-kata-teal-3 hover:underline"
              data-testid={`source-chip-${artifact}`}
            >
              {artifact}
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

export function TeamContext() {
  const { t } = useTranslation()
  const active = usePersona()
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const themeRef = useRef<ThemeColors | null>(null)
  const stopPulseRef = useRef<(() => void) | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [pinnedId, setPinnedId] = useState<string | null>(null)
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number; flip: boolean } | null>(null)
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )

  // KATA-15 originally gated Team context on a Connect source being wired
  // up (empty state until then). Reverted per this ticket: Team context and
  // the rest of the learning content are grounded in the seeded curriculum
  // and each persona's real progress, never in whether a messaging platform
  // happens to be connected — Connect is its own, unrelated, localStorage-only
  // mock (`connect-store.ts`), so these queries always run.
  const graph = useApiQuery<{ nodes: GraphNode[]; edges: GraphEdge[] }>('concept-graph', '/me/concept-graph')
  const progress = useApiQuery<{ concepts: ProgressConcept[] }>('team-context-progress', '/me/progress')
  const nextItem = useApiQuery<{ items: { concept_id: string }[] }>('team-context-next', '/me/next?limit=1')

  // Acting persona's own topic — best-effort (not every persona has one);
  // errors are swallowed here, it's a highlight, not primary content.
  const ownTopics = useQuery({
    queryKey: ['own-topics', active.id],
    queryFn: () => apiFetch<{ topics: Topic[] }>('/topics', { persona: active }),
    retry: false,
  })
  const ownTopicConceptIds = useMemo(
    () => new Set(ownTopics.data?.topics.flatMap((topic) => topic.concept_ids) ?? []),
    [ownTopics.data],
  )

  const bottomTopicQueries = useQueries({
    queries: BOTTOM_TOPIC_PERSONAS.map((persona) => ({
      queryKey: ['bottom-topics', persona.id],
      queryFn: () => apiFetch<{ topics: Topic[] }>('/topics', { persona }),
      retry: false,
    })),
  })

  const dueByConcept = useMemo(
    () => new Map((progress.data?.concepts ?? []).map((c) => [c.concept_id, c.due_count])),
    [progress.data],
  )
  const nextConceptId = nextItem.data?.items[0]?.concept_id ?? null
  const focusedId = hoveredId ?? pinnedId

  const activeChain = useMemo(() => {
    if (!graph.data || !focusedId) return null
    return computeChain(focusedId, graph.data.edges)
  }, [graph.data, focusedId])

  useEffect(() => {
    if (!graph.data || !containerRef.current || cyRef.current) return
    const theme = resolveThemeColors()
    themeRef.current = theme
    const nodeInputs: GraphNodeInput[] = graph.data.nodes.map((n) => ({
      concept_id: n.concept_id,
      title: n.title,
      p_known: n.p_known,
      mastered: n.mastered,
      unlocked: n.unlocked,
      dueCount: dueByConcept.get(n.concept_id) ?? 0,
      topics: [],
    }))
    const edgeInputs: GraphEdgeInput[] = graph.data.edges.map((e) => ({
      from_concept_id: e.from_concept_id,
      to_concept_id: e.to_concept_id,
      kind: e.kind,
    }))
    const cy = cytoscape({
      container: containerRef.current,
      elements: buildElements(nodeInputs, edgeInputs),
      style: stylesheet(reducedMotion, theme),
      layout: {
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 34,
        rankSep: 90,
        fit: true,
        padding: 32,
        nodeDimensionsIncludeLabels: true,
      } as cytoscape.LayoutOptions,
      minZoom: 0.3,
      maxZoom: 2,
      wheelSensitivity: 0.2,
    })

    // No `animate` option above, so the dagre layout already ran
    // synchronously by the time the constructor returns — 'layoutstop'
    // has already fired, so don't wait on it. Graph renders straight
    // into its final layout — no position animation — and simply fades
    // in as a whole once ready.
    cy.fit(undefined, 32)
    if (!reducedMotion && containerRef.current) {
      const el = containerRef.current
      el.style.opacity = '0'
      requestAnimationFrame(() => {
        el.style.transition = `opacity ${FADE_MS}ms ${FADE_EASING}`
        el.style.opacity = '1'
      })
    }

    cy.on('mouseover', 'node', (evt) => setHoveredId(evt.target.id()))
    cy.on('mouseout', 'node', () => setHoveredId(null))
    cy.on('tap', 'node', (evt) => setPinnedId((cur) => (cur === evt.target.id() ? null : evt.target.id())))
    cy.on('tap', (evt) => {
      if (evt.target === cy) setPinnedId(null)
    })
    cyRef.current = cy
    setKataGraphDebug({ nodeCount: cy.nodes().length, edgeCount: cy.edges().length, highlighted: [] })
  }, [graph.data, dueByConcept, reducedMotion])

  useEffect(() => {
    return () => {
      cyRef.current?.destroy()
      cyRef.current = null
      clearKataGraphDebug()
    }
  }, [])

  // Highlight the acting persona's own topic concepts (mock: "hot" nodes).
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.nodes().removeClass('in-topic')
      cy.nodes().forEach((n) => {
        if (ownTopicConceptIds.has(n.id())) n.addClass('in-topic')
      })
    })
  }, [ownTopicConceptIds, graph.data])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.elements().removeClass('faded highlighted')
      if (activeChain) {
        cy.nodes().forEach((n) => {
          if (!activeChain.has(n.id())) n.addClass('faded')
          else n.addClass('highlighted')
        })
        cy.edges().forEach((e) => {
          const inChain = activeChain.has(e.data('source')) && activeChain.has(e.data('target'))
          if (!inChain) e.addClass('faded')
          else e.addClass('highlighted')
        })
      }
    })
    stopPulseRef.current?.()
    stopPulseRef.current = null
    if (nextConceptId) {
      const node = cy.getElementById(nextConceptId)
      if (!node.empty()) stopPulseRef.current = startNextPulse(node)
    }
    setKataGraphDebug({
      nodeCount: cy.nodes().length,
      edgeCount: cy.edges().length,
      highlighted: activeChain ? [...activeChain] : [],
    })
  }, [activeChain, nextConceptId, reducedMotion])

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    function updatePos() {
      if (!focusedId || !cy || !containerRef.current) return setTooltipPos(null)
      const node = cy.getElementById(focusedId)
      if (node.empty()) return setTooltipPos(null)
      const p = node.renderedPosition()
      const containerWidth = containerRef.current.clientWidth
      const halfNode = node.renderedOuterWidth() / 2 || NODE_SIZE_HALF_GUESS
      const gap = 14
      const flip = p.x + halfNode + gap + TOOLTIP_WIDTH > containerWidth
      setTooltipPos({ x: p.x + (flip ? -halfNode - gap : halfNode + gap), y: p.y, flip })
    }
    updatePos()
    cy.on('pan zoom position', updatePos)
    return () => {
      cy.removeListener('pan zoom position', updatePos)
    }
  }, [focusedId])

  const focusedNode = graph.data?.nodes.find((n) => n.concept_id === focusedId) ?? null
  const relatedCount = graph.data?.edges.filter((e) => e.kind === 'related').length ?? 0

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6 px-6 py-6">
      <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
        <div className="flex flex-col gap-4">
          <IngestionSourcesPanel />
          <ConnectPanel />
          <Card>
            <CardContent className="pt-5">
              <StreamLog
                nodeCount={graph.data?.nodes.length ?? 14}
                edgeCount={graph.data?.edges.length ?? 0}
                relatedCount={relatedCount}
                reducedMotion={reducedMotion}
              />
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardContent className="flex flex-col gap-3 pt-5">
            <h2 className="font-heading text-base font-semibold">{t('teamContext.graphTitle')}</h2>

            {graph.isLoading && <Skeleton className="h-[560px] w-full" />}
            {graph.isError && <ApiStatusBanner error={graph.error} />}

            <DataState query={graph} screen={t('teamContext.graphTitle')} isEmpty={() => false}>
              {() => (
                <div
                  className="relative rounded-lg border bg-card"
                  data-testid="concept-map-canvas"
                  style={{ minHeight: 560, ...DOT_GRID_STYLE }}
                >
                  <div ref={containerRef} className="size-full" style={{ minHeight: 560 }} />
                  {focusedNode && tooltipPos && (
                    <div
                      data-testid="concept-map-tooltip"
                      className={cn(
                        'pointer-events-none absolute z-10 w-72 max-w-72 -translate-y-1/2 rounded-lg border bg-popover p-3 text-xs shadow-lg',
                        tooltipPos.flip && '-translate-x-full',
                      )}
                      style={{ top: tooltipPos.y, left: tooltipPos.x }}
                    >
                      <p className="text-sm font-medium">{focusedNode.title}</p>
                      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-muted-foreground">
                        <span>p_known</span>
                        <span className="text-foreground" data-testid="tooltip-p-known">
                          {formatPercent(focusedNode.p_known)} ({masteryTier(focusedNode.p_known)})
                        </span>
                        <span>{t('conceptMap.dueLabel')}</span>
                        <span className="text-foreground">{dueByConcept.get(focusedNode.concept_id) ?? 0}</span>
                        <span>{t('conceptMap.masteredLabel')}</span>
                        <span className="text-foreground">{focusedNode.mastered ? t('nextUp.yes') : t('nextUp.no')}</span>
                        <span>{t('conceptMap.unlockedLabel')}</span>
                        <span className="text-foreground">{focusedNode.unlocked ? t('nextUp.yes') : t('nextUp.no')}</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </DataState>

            <p className="text-xs text-muted-foreground">{t('teamContext.graphCaption', { name: active.name })}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {BOTTOM_TOPIC_PERSONAS.map((persona, i) => (
          <TopicCard key={persona.id} persona={persona} topic={bottomTopicQueries[i].data?.topics[0]} />
        ))}
      </div>
    </div>
  )
}
