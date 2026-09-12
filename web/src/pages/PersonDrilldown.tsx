import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { DataState } from '@/components/DataState'
import { MasteryBar } from '@/components/MasteryBar'
import { PageScaffold } from '@/components/PageScaffold'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useApiQuery } from '@/hooks/useApiQuery'
import { formatDateTime } from '@/lib/format'
import { conceptTitle, personName } from '@/lib/ferry-scenario'

interface PersonDetail {
  person_id: string
  concepts: { concept_id: string; p_known: number; mastered: boolean; due_count: number; unlocked: boolean }[]
  adherence: number
  velocity: number
  due_count: number
  last_active: string | null
}

export function PersonDrilldown() {
  const { t } = useTranslation()
  const { personId = '' } = useParams()
  const query = useApiQuery<PersonDetail>(`person-${personId}`, `/team/people/${personId}`)

  return (
    <PageScaffold
      title={t('personDrilldown.titlePrefix', { name: personName(personId) })}
      description={t('personDrilldown.description')}
    >
      <DataState
        query={query}
        screen={t('team.title')}
        isEmpty={(d) => d.concepts.length === 0}
        emptyLabel={t('personDrilldown.emptyConcepts')}
      >
        {(d) => (
          <div className="flex flex-col gap-4">
            <div className="flex gap-2">
              <Badge variant="secondary">{t('personDrilldown.adherenceBadge', { pct: Math.round(d.adherence * 100) })}</Badge>
              <Badge variant="outline">{t('personDrilldown.velocityBadge', { count: d.velocity })}</Badge>
              <Badge variant="outline">{t('personDrilldown.dueBadge', { count: d.due_count })}</Badge>
              <Badge variant="outline">{t('personDrilldown.lastActiveBadge', { date: formatDateTime(d.last_active) })}</Badge>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('personDrilldown.colConcept')}</TableHead>
                  <TableHead>{t('personDrilldown.colPKnown')}</TableHead>
                  <TableHead>{t('personDrilldown.colMastered')}</TableHead>
                  <TableHead>{t('personDrilldown.colDue')}</TableHead>
                  <TableHead>{t('personDrilldown.colUnlocked')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {d.concepts.map((c) => (
                  <TableRow key={c.concept_id}>
                    <TableCell className="font-medium">{conceptTitle(c.concept_id)}</TableCell>
                    <TableCell className="w-48">
                      <MasteryBar p={c.p_known} />
                    </TableCell>
                    <TableCell>{c.mastered ? t('personDrilldown.yes') : t('personDrilldown.no')}</TableCell>
                    <TableCell>{c.due_count}</TableCell>
                    <TableCell>{c.unlocked ? t('personDrilldown.yes') : t('personDrilldown.no')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </DataState>
    </PageScaffold>
  )
}
