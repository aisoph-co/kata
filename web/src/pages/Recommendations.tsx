import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataState } from '@/components/DataState'
import { PageScaffold } from '@/components/PageScaffold'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useApiQuery } from '@/hooks/useApiQuery'
import { conceptTitle } from '@/lib/ferry-scenario'

interface Recommendation {
  concept_id: string
  score: number
  mean_mastery: number
  dependents_count: number
}

interface Digest {
  period_start: string
  period_end: string
  at_risk: { person_id: string; concept_id: string }[]
  recommendations: Recommendation[]
}

const DAY_OPTIONS = [1, 7, 14, 30, 90]

function RecTable({ recs }: { recs: Recommendation[] }) {
  const { t } = useTranslation()
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t('recommendations.colConcept')}</TableHead>
          <TableHead>{t('recommendations.colScore')}</TableHead>
          <TableHead>{t('recommendations.colMeanMastery')}</TableHead>
          <TableHead>{t('recommendations.colDependents')}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {recs.map((r) => (
          <TableRow key={r.concept_id}>
            <TableCell className="font-medium">{conceptTitle(r.concept_id)}</TableCell>
            <TableCell>{r.score.toFixed(2)}</TableCell>
            <TableCell>{Math.round(r.mean_mastery * 100)}%</TableCell>
            <TableCell>{r.dependents_count}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function Recommendations() {
  const { t } = useTranslation()
  const [days, setDays] = useState('7')
  const recommendations = useApiQuery<{ recommendations: Recommendation[] }>('recommendations', '/team/recommendations')
  const digest = useApiQuery<Digest>(`digest-${days}`, `/team/digest?days=${days}`)

  return (
    <PageScaffold title={t('recommendations.title')} description={t('recommendations.description')}>
      <div className="flex flex-col gap-6">
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">{t('recommendations.topRecsHeading')}</h2>
          <DataState
            query={recommendations}
            screen={t('recommendations.title')}
            isEmpty={(d) => d.recommendations.length === 0}
            emptyLabel={t('recommendations.emptyRecs')}
          >
            {(d) => <RecTable recs={d.recommendations} />}
          </DataState>
        </div>

        <div className="rounded-lg border p-4">
          <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('recommendations.digestWindowLabel')}
          </Label>
          <div className="mt-2 flex items-center gap-3">
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DAY_OPTIONS.map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {t('recommendations.dayOption', { count: d })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="mt-4">
            <DataState query={digest} screen={t('recommendations.title')} isEmpty={() => false}>
              {(d) => (
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap gap-2">
                    {d.at_risk.length === 0 ? (
                      <Badge variant="outline">{t('recommendations.noAtRisk')}</Badge>
                    ) : (
                      d.at_risk.map((a, i) => (
                        <Badge key={i} variant="destructive">
                          {conceptTitle(a.concept_id)}
                        </Badge>
                      ))
                    )}
                  </div>
                  <Card>
                    <CardContent className="py-3">
                      <RecTable recs={d.recommendations} />
                    </CardContent>
                  </Card>
                </div>
              )}
            </DataState>
          </div>
        </div>
      </div>
    </PageScaffold>
  )
}
