/**
 * Resolves one `Topic.grounded_in` citation (an issue key, or a
 * `file.md#heading-anchor`) to the excerpt it names — SCREENS.md #02's
 * "source chip -> cited excerpt": "clicking a source chip ... opens the
 * cited artifact's excerpt from the seed's `1-context/` files."
 *
 * There is no citation-resolution endpoint in `contracts/openapi.yaml`
 * (`docs/superpowers/specs/2026-09-07-web-app-design.md` contract change
 * #5: "citation storage is an addition on top of it [the topic table]...
 * that field is still undefined"). Until one exists, this reads the same
 * static `1-context/` files ingestion itself reads (vendored verbatim into
 * `data/seed-context/1-context/`, not invented) and resolves a citation
 * against them client-side. A miss renders as a stated "no excerpt found"
 * (`resolveCitationExcerpt` returns `null`) rather than fabricated text —
 * this module should move server-side once a real endpoint exists.
 */
import companyMd from '@/data/seed-context/1-context/company.md?raw'
import issuesJsonl from '@/data/seed-context/1-context/issues.jsonl?raw'
import releaseNotesMd from '@/data/seed-context/1-context/release-notes.md?raw'
import repoExcerptsMd from '@/data/seed-context/1-context/repo-excerpts.md?raw'
import slackThreadsMd from '@/data/seed-context/1-context/slack-threads.md?raw'
import sprintHistoryMd from '@/data/seed-context/1-context/sprint-history.md?raw'

export interface SeedIssue {
  key: string
  type: string
  status: string
  title: string
  assignee: string
  concepts: string[]
  body: string
}

export interface CitationExcerpt {
  /** The `1-context/` file the excerpt came from. */
  sourceFile: string
  /** The heading text for a file#anchor citation; the issue title for an
   * issue-key citation. */
  heading: string
  /** The excerpt text itself. */
  text: string
}

const MARKDOWN_FILES: Record<string, string> = {
  'company.md': companyMd,
  'release-notes.md': releaseNotesMd,
  'repo-excerpts.md': repoExcerptsMd,
  'slack-threads.md': slackThreadsMd,
  'sprint-history.md': sprintHistoryMd,
}

function parseIssues(jsonl: string): Map<string, SeedIssue> {
  const byKey = new Map<string, SeedIssue>()
  for (const line of jsonl.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const issue = JSON.parse(trimmed) as SeedIssue
    byKey.set(issue.key, issue)
  }
  return byKey
}

const ISSUES_BY_KEY = parseIssues(issuesJsonl)

/** GitHub's own heading-slug rule, reproduced exactly (not approximated) so
 * `file.md#anchor` citations resolve against real headings: lowercase,
 * drop everything but letters/digits/spaces/existing hyphens, then turn
 * each remaining space into a hyphen — no collapsing of doubled hyphens. */
export function slugifyHeading(heading: string): string {
  return heading
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, '')
    .split(' ')
    .join('-')
}

interface Heading {
  level: number
  text: string
  slug: string
  bodyStart: number
  bodyEnd: number
}

function headingsOf(markdown: string): Heading[] {
  const lines = markdown.split('\n')
  const headings: { level: number; text: string; line: number }[] = []
  lines.forEach((line, index) => {
    const match = /^(#{1,6})\s+(.*)$/.exec(line)
    if (match) headings.push({ level: match[1].length, text: match[2].trim(), line: index })
  })
  return headings.map((heading, index) => {
    // A section ends at the next heading of the same or shallower level,
    // matching how the file's own table of contents nests (e.g. a level-2
    // "## Reverted" section stops at the next "##", not at a "###" inside it).
    const end = headings.slice(index + 1).find((candidate) => candidate.level <= heading.level)?.line ?? lines.length
    return {
      level: heading.level,
      text: heading.text,
      slug: slugifyHeading(heading.text),
      bodyStart: heading.line + 1,
      bodyEnd: end,
    }
  })
}

function findAnchoredExcerpt(fileName: string, anchor: string): CitationExcerpt | null {
  const markdown = MARKDOWN_FILES[fileName]
  if (!markdown) return null
  const lines = markdown.split('\n')
  const heading = headingsOf(markdown).find((candidate) => candidate.slug === anchor)
  if (!heading) return null
  return {
    sourceFile: fileName,
    heading: heading.text,
    text: lines.slice(heading.bodyStart, heading.bodyEnd).join('\n').trim(),
  }
}

function findIssueExcerpt(key: string): CitationExcerpt | null {
  const issue = ISSUES_BY_KEY.get(key)
  if (!issue) return null
  return {
    sourceFile: 'issues.jsonl',
    heading: `${issue.key} — ${issue.title}`,
    text: issue.body,
  }
}

/**
 * `citation` is one `Topic.grounded_in` entry. Returns `null` when nothing
 * in the vendored `1-context/` mirror matches — a real "not found", not a
 * thrown error, since a citation the seed hasn't been regenerated to match
 * yet is an expected, statable case, not a bug.
 */
export function resolveCitationExcerpt(citation: string): CitationExcerpt | null {
  const hashIndex = citation.indexOf('#')
  if (hashIndex === -1) return findIssueExcerpt(citation)
  const fileName = citation.slice(0, hashIndex)
  const anchor = citation.slice(hashIndex + 1)
  return findAnchoredExcerpt(fileName, anchor)
}
