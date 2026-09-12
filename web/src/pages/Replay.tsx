import { useMutation } from '@tanstack/react-query'
import { CheckCircle2, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ApiStatusBanner } from '@/components/ApiStatusBanner'
import { PageScaffold } from '@/components/PageScaffold'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { apiFetch } from '@/lib/api-client'
import { conceptTitle } from '@/lib/ferry-scenario'
import { PERSONAS } from '@/lib/personas'

interface ProgressConcept {
  concept_id: string
  p_known: number
  mastered: boolean
}

interface ReplayResponse {
  status: string
  replayed_reviews: number
  card_state_count: number
  concept_state_count: number
}

const HUGO = PERSONAS.find((p) => p.id === 'hugo')!

export function Replay() {
  const { t } = useTranslation()
  const replay = useMutation({
    mutationFn: async () => {
      const before = await apiFetch<{ concepts: ProgressConcept[] }>('/me/progress', { persona: HUGO })
      const result = await apiFetch<ReplayResponse>('/admin/replay', { persona: HUGO, method: 'POST' })
      const after = await apiFetch<{ concepts: ProgressConcept[] }>('/me/progress', { persona: HUGO })
      return { before: before.concepts, result, after: after.concepts }
    },
  })

  return (
    <PageScaffold title={t('replay.title')} description={t('replay.description')}>
      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="flex flex-col items-start gap-3 py-6">
            <Button disabled={replay.isPending} onClick={() => replay.mutate()}>
              {replay.isPending ? t('replay.runningButton') : t('replay.runButton')}
            </Button>
            {replay.isError && <ApiStatusBanner error={replay.error} />}
          </CardContent>
        </Card>

        {replay.isSuccess && (
          <>
            <div className="flex gap-2">
              <Badge variant="secondary">{t('replay.badgeReviewsReplayed', { count: replay.data.result.replayed_reviews })}</Badge>
              <Badge variant="outline">{t('replay.badgeCardStates', { count: replay.data.result.card_state_count })}</Badge>
              <Badge variant="outline">{t('replay.badgeConceptStates', { count: replay.data.result.concept_state_count })}</Badge>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('replay.colConcept')}</TableHead>
                  <TableHead>{t('replay.colBefore')}</TableHead>
                  <TableHead>{t('replay.colAfter')}</TableHead>
                  <TableHead>{t('replay.colFlag')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {replay.data.before.map((b) => {
                  const a = replay.data.after.find((x) => x.concept_id === b.concept_id)
                  const identical = a !== undefined && Math.abs(a.p_known - b.p_known) < 1e-9
                  return (
                    <TableRow key={b.concept_id}>
                      <TableCell className="font-medium">{conceptTitle(b.concept_id)}</TableCell>
                      <TableCell>{b.p_known.toFixed(4)}</TableCell>
                      <TableCell>{a ? a.p_known.toFixed(4) : '—'}</TableCell>
                      <TableCell>
                        {identical ? (
                          <span className="flex items-center gap-1 text-mastery-high">
                            <CheckCircle2 className="size-4" /> {t('replay.identical')}
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-mastery-low">
                            <XCircle className="size-4" /> {t('replay.differs')}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </>
        )}
      </div>
    </PageScaffold>
  )
}
