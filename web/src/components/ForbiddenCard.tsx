import { ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError } from '@/lib/api-client'
import { usePersona } from '@/lib/persona-store'

const COPY_KEY: Record<string, string> = {
  unknown_identity: 'forbidden.unknownIdentity',
  not_a_manager: 'forbidden.notAManager',
  not_operator: 'forbidden.notOperator',
  outside_subtree: 'forbidden.outsideSubtree',
}

/**
 * Renders the service's real 403 as a friendly card — every route stays
 * reachable, but a mismatched persona sees why, not a blank error. The
 * code/message are the actual response, not a client-side guess.
 */
export function ForbiddenCard({ error, screen }: { error: ApiError; screen: string }) {
  const { t } = useTranslation()
  const persona = usePersona()
  const copyKey = error.code ? COPY_KEY[error.code] : undefined

  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldAlert className="size-4 text-muted-foreground" />
          {error.status} {error.code ?? t('forbidden.fallbackCode')}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        <p>
          {copyKey
            ? t(copyKey, { name: persona.name })
            : t('forbidden.genericBody', { screen, message: error.message })}
        </p>
      </CardContent>
    </Card>
  )
}
