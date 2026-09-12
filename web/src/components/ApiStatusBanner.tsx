import { AlertTriangle, WifiOff } from 'lucide-react'
import { Trans, useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/api-client'
import { errorExplanation } from '@/lib/error-explanations'

export function ApiStatusBanner({ error }: { error: unknown }) {
  const { t } = useTranslation()
  if (!error) return null

  if (error instanceof ApiError && error.isUnreachable) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        <WifiOff className="mt-0.5 size-4 shrink-0" />
        <div>
          <p className="font-medium">{t('apiStatus.unreachableTitle')}</p>
          <p className="text-destructive/80">
            <Trans
              i18nKey="apiStatus.unreachableBody"
              components={{ code: <code className="rounded bg-destructive/10 px-1 py-0.5 font-mono" /> }}
            />
          </p>
        </div>
      </div>
    )
  }

  const message = error instanceof ApiError ? error.message : (error as Error).message
  const code = error instanceof ApiError ? error.code : undefined
  const status = error instanceof ApiError ? error.status : undefined
  const explanation = errorExplanation(code)

  return (
    <div className="flex items-start gap-3 rounded-lg border border-secondary bg-secondary/60 px-4 py-3 text-sm text-secondary-foreground">
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div>
        <p className="font-medium">
          {status ? `${status} ` : ''}
          {code ?? t('apiStatus.fallbackCode')}
        </p>
        <p className="text-secondary-foreground/80">{message}</p>
        {explanation && <p className="mt-0.5 text-secondary-foreground/70">{explanation}</p>}
      </div>
    </div>
  )
}
