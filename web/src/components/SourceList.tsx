const SOURCES = [
  { id: 'repo', label: 'Repo' },
  { id: 'issues', label: 'Issues' },
  { id: 'releases', label: 'Releases' },
  { id: 'slack', label: 'Slack' },
  { id: 'exa', label: 'Exa' },
] as const

/**
 * The five ingestion sources (SCREENS.md #02) with their counts. There is
 * no ingestion-status endpoint in `contracts/openapi.yaml` yet — CI1 owns
 * wiring a live count/`ingesting · m:ss` badge on top of this same markup —
 * so counts render as an explicit "—" rather than an invented number,
 * matching this codebase's own convention for a value with nowhere to come
 * from yet (`build-day/issues.md` row R3a).
 */
export function SourceList() {
  return (
    <div className="source-list" data-testid="connections-source-list">
      {SOURCES.map((source) => (
        <div className="source-row" key={source.id} data-testid={`source-${source.id}`}>
          <span className="source-row-label">{source.label}</span>
          <span className="source-row-count" data-testid={`source-${source.id}-count`}>
            —
          </span>
        </div>
      ))}
    </div>
  )
}
