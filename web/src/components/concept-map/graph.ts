import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { masteryTier } from '@/lib/format'

cytoscape.use(dagre)

export const NODE_WIDTH = 172
export const NODE_HEIGHT = 42

/** Single fade duration/easing shared across the whole team-context page
 * (graph layout fade-in, hover/selection colour transitions, next-concept
 * highlight, STREAM log lines) — see PLAN request "simple fade in/out". */
export const FADE_MS = 250
export const FADE_EASING = 'ease-out' as const

/**
 * Cytoscape's style parser doesn't understand oklch() or CSS custom
 * properties (var(...)) — passing either silently falls back to black on
 * canvas. This resolves a `var(--token)` (or any CSS colour) to the
 * browser's own computed rgb() string by writing it to a throwaway
 * element and reading it back, so dark mode / theme changes are honoured
 * without hand-maintaining a second hex palette.
 */
function resolveCssColor(cssValue: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const probe = document.createElement('span')
  probe.style.color = cssValue
  probe.style.position = 'absolute'
  probe.style.visibility = 'hidden'
  document.body.appendChild(probe)
  const resolved = getComputedStyle(probe).color
  document.body.removeChild(probe)
  return resolved && resolved !== '' ? resolved : fallback
}

export interface ThemeColors {
  low: string
  mid: string
  high: string
  primary: string
  foreground: string
  mutedLine: string
  track: string
  paper: string
  topicTint: string
}

export function resolveThemeColors(): ThemeColors {
  return {
    low: resolveCssColor('var(--mastery-low)', '#e0524a'),
    mid: resolveCssColor('var(--mastery-mid)', '#f0a83c'),
    high: resolveCssColor('var(--mastery-high)', '#22a06b'),
    primary: resolveCssColor('var(--primary)', '#7c3aed'),
    foreground: resolveCssColor('var(--foreground)', '#111827'),
    mutedLine: resolveCssColor('var(--muted-foreground)', '#8a8a8a'),
    track: resolveCssColor('var(--border)', '#d4d4d8'),
    paper: resolveCssColor('var(--card)', '#ffffff'),
    topicTint: resolveCssColor('var(--secondary)', '#e3f2ee'),
  }
}

export interface GraphNodeInput {
  concept_id: string
  title: string
  p_known: number
  mastered: boolean
  unlocked: boolean
  dueCount: number
  topics: { role: string; label: string; title: string }[]
}

export interface GraphEdgeInput {
  from_concept_id: string
  to_concept_id: string
  kind: 'prerequisite' | 'related'
}

export function buildElements(nodes: GraphNodeInput[], edges: GraphEdgeInput[]): cytoscape.ElementDefinition[] {
  const nodeEls: cytoscape.ElementDefinition[] = nodes.map((n) => ({
    group: 'nodes',
    data: {
      id: n.concept_id,
      label: n.unlocked ? n.title : `🔒 ${n.title}`,
      title: n.title,
      p_known: n.p_known,
      mastered: n.mastered,
      unlocked: n.unlocked,
      dueCount: n.dueCount,
      tier: masteryTier(n.p_known),
      topics: n.topics,
    },
    classes: n.unlocked ? undefined : 'locked',
  }))
  const edgeEls: cytoscape.ElementDefinition[] = edges.map((e) => ({
    group: 'edges',
    data: {
      // A concept pair can have *both* a prerequisite and a related edge
      // (e.g. money-representation → fx-quote-lifecycle) — kind must be
      // part of the id or the second one silently overwrites the first.
      id: `${e.from_concept_id}-${e.to_concept_id}-${e.kind}`,
      source: e.from_concept_id,
      target: e.to_concept_id,
      kind: e.kind,
    },
    classes: e.kind,
  }))
  return [...nodeEls, ...edgeEls]
}

export function stylesheet(reducedMotion: boolean, theme: ThemeColors): cytoscape.StylesheetJson {
  return [
    {
      // Kata mock frame 02: white boxed nodes, plain border, label inside.
      selector: 'node',
      style: {
        shape: 'round-rectangle',
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
        'background-color': theme.paper,
        'border-width': 1.2,
        'border-color': theme.mutedLine,
        'border-style': 'solid',
        label: 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': 12,
        'font-weight': 500,
        color: theme.foreground,
        'text-wrap': 'wrap',
        'text-max-width': `${NODE_WIDTH - 16}px`,
        'transition-property': 'opacity, border-color, background-color, overlay-opacity',
        'transition-duration': reducedMotion ? 0 : FADE_MS,
        'transition-timing-function': FADE_EASING,
      } as cytoscape.Css.Node,
    },
    {
      // Locked / no-reps-yet concepts — dashed border, mock's "still arriving".
      selector: 'node.locked',
      style: {
        'border-style': 'dashed',
      } as cytoscape.Css.Node,
    },
    {
      // Acting persona's own topic — the mock's "hot" node.
      selector: 'node.in-topic',
      style: {
        'background-color': theme.topicTint,
        'border-color': theme.primary,
        'border-width': 2,
        'border-style': 'solid',
      } as cytoscape.Css.Node,
    },
    {
      selector: 'edge',
      style: {
        opacity: 1,
        'transition-property': 'opacity, line-color, width',
        'transition-duration': reducedMotion ? 0 : FADE_MS,
        'transition-timing-function': FADE_EASING,
      } as cytoscape.Css.Edge,
    },
    {
      selector: 'edge.prerequisite',
      style: {
        width: 2,
        'line-color': theme.mutedLine,
        'target-arrow-color': theme.mutedLine,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 1.1,
        'curve-style': 'bezier',
      } as cytoscape.Css.Edge,
    },
    {
      selector: 'edge.related',
      style: {
        width: 1.25,
        'line-color': theme.mutedLine,
        opacity: 0.45,
        'line-style': 'dotted',
        'target-arrow-shape': 'none',
        'curve-style': 'bezier',
      } as cytoscape.Css.Edge,
    },
    {
      // Never fades below 0.35 — dimmed elements stay legible.
      selector: '.faded',
      style: { opacity: 0.35 },
    },
    {
      selector: 'node.highlighted',
      style: {
        'border-width': 4,
        'border-color': theme.primary,
        'border-opacity': 1,
      },
    },
    {
      selector: 'edge.highlighted',
      style: {
        'line-color': theme.primary,
        'target-arrow-color': theme.primary,
        width: 3,
        opacity: 1,
        // A soft "glow" underlay, since Cytoscape edges have no box-shadow.
        'underlay-color': theme.primary,
        'underlay-opacity': 0.35,
        'underlay-padding': 4,
      },
    },
    {
      selector: 'node.next-pulse',
      style: {
        'overlay-color': theme.primary,
        'overlay-shape': 'ellipse',
      },
    },
  ]
}

/** Ancestors + descendants of `id` via prerequisite edges only, plus `id`
 * itself — the "whole prerequisite chain" a hover/tap highlights. */
export function computeChain(id: string, edges: GraphEdgeInput[]): Set<string> {
  const prereq = edges.filter((e) => e.kind === 'prerequisite')
  const parents = new Map<string, string[]>()
  const children = new Map<string, string[]>()
  for (const e of prereq) {
    parents.set(e.to_concept_id, [...(parents.get(e.to_concept_id) ?? []), e.from_concept_id])
    children.set(e.from_concept_id, [...(children.get(e.from_concept_id) ?? []), e.to_concept_id])
  }
  const chain = new Set<string>([id])
  for (const dir of [parents, children]) {
    const stack = [id]
    while (stack.length > 0) {
      const cur = stack.pop()!
      for (const next of dir.get(cur) ?? []) {
        if (!chain.has(next)) {
          chain.add(next)
          stack.push(next)
        }
      }
    }
  }
  return chain
}

/** Marks the "next" concept with a static highlight overlay that simply
 * fades in/out (via the node selector's shared `overlay-opacity`
 * transition) — no pulsing/breathing loop, no movement. */
export function startNextPulse(node: cytoscape.NodeSingular): () => void {
  node.style({ 'overlay-opacity': 0.22, 'overlay-padding': 10 })
  return () => node.style({ 'overlay-opacity': 0, 'overlay-padding': 0 })
}
