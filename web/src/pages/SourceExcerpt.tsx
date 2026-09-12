import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { PageScaffold } from '@/components/PageScaffold'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useLangPath } from '@/hooks/useLangPath'
import { resolveCitation } from '@/lib/citations'

/** W11 (KATA-14): the excerpt view a source chip opens — same route for the
 * web-side chip this issue wires (topic cards on Team context) and the
 * Slack-side chip G1 wires separately (frame 06), so both point at one
 * view. Reads local fixture excerpts (`@/lib/citations`), not the API. */
export function SourceExcerpt() {
  const { t } = useTranslation()
  const { ref = '' } = useParams()
  const langPath = useLangPath()
  const citation = resolveCitation(decodeURIComponent(ref))

  return (
    <PageScaffold title={t('sourceExcerpt.title', { ref: citation.ref })} description={t('sourceExcerpt.description')}>
      <Card data-testid="source-excerpt">
        <CardContent className="flex flex-col gap-3 pt-5">
          {citation.kind === 'issue' && (
            <>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="font-mono">
                  {citation.key}
                </Badge>
                <span>
                  {citation.type} · {citation.status}
                </span>
                <span className="ml-auto">{citation.assignee}</span>
              </div>
              <p className="font-heading text-base font-semibold" data-testid="source-excerpt-title">
                {citation.title}
              </p>
              <p className="text-sm leading-relaxed text-foreground/90" data-testid="source-excerpt-body">
                {citation.body}
              </p>
            </>
          )}
          {citation.kind === 'doc' && (
            <>
              <Badge variant="outline" className="w-fit font-mono">
                {citation.file}
              </Badge>
              <p className="font-heading text-base font-semibold" data-testid="source-excerpt-title">
                {citation.heading}
              </p>
              <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90" data-testid="source-excerpt-body">
                {citation.body}
              </p>
            </>
          )}
          {citation.kind === 'unavailable' && (
            <p className="text-sm text-muted-foreground" data-testid="source-excerpt-unavailable">
              {t('sourceExcerpt.unavailable', { ref: citation.ref })}
            </p>
          )}
        </CardContent>
      </Card>
      <Link
        to={langPath('/team-context')}
        className="text-xs font-medium text-primary hover:underline"
        data-testid="source-excerpt-back"
      >
        {t('sourceExcerpt.back')}
      </Link>
    </PageScaffold>
  )
}
