import { useTranslation } from 'react-i18next'
import { DataState } from '@/components/DataState'
import { PageScaffold } from '@/components/PageScaffold'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useApiQuery } from '@/hooks/useApiQuery'
import { formatDateTime } from '@/lib/format'
import { personName } from '@/lib/ferry-scenario'

interface AuditEntry {
  id: string
  actor_person_id: string
  subject_scope: string
  endpoint: string
  at: string
}

export function Audit() {
  const { t } = useTranslation()
  const query = useApiQuery<{ entries: AuditEntry[] }>('audit', '/team/audit')

  return (
    <PageScaffold title={t('audit.title')} description={t('audit.description')}>
      <DataState
        query={query}
        screen={t('audit.title')}
        isEmpty={(d) => d.entries.length === 0}
        emptyLabel={t('audit.emptyAudit')}
      >
        {(d) => (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('audit.colAt')}</TableHead>
                <TableHead>{t('audit.colActor')}</TableHead>
                <TableHead>{t('audit.colScope')}</TableHead>
                <TableHead>{t('audit.colEndpoint')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d.entries.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap text-xs">{formatDateTime(e.at)}</TableCell>
                  <TableCell>{personName(e.actor_person_id)}</TableCell>
                  <TableCell className="font-mono text-xs">{e.subject_scope}</TableCell>
                  <TableCell className="font-mono text-xs">{e.endpoint}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DataState>
    </PageScaffold>
  )
}
