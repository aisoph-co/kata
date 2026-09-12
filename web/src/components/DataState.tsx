import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiStatusBanner } from '@/components/ApiStatusBanner'
import { ForbiddenCard } from '@/components/ForbiddenCard'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/lib/api-client'

/**
 * Renders a query's states: loading skeleton, the real 403 as a friendly
 * card, any other error as the honest banner, an empty state, or the data
 * via `children` (render-prop) once it's there.
 */
export function DataState<T>({
  query,
  screen,
  emptyLabel,
  isEmpty,
  children,
}: {
  query: UseQueryResult<T>
  screen: string
  emptyLabel?: string
  isEmpty?: (data: T) => boolean
  children?: (data: T) => ReactNode
}) {
  const { t } = useTranslation()
  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    )
  }

  if (query.isError) {
    const error = query.error
    if (error instanceof ApiError && error.status === 403) {
      return <ForbiddenCard error={error} screen={screen} />
    }
    return <ApiStatusBanner error={error} />
  }

  const data = query.data as T
  const empty = isEmpty ? isEmpty(data) : data == null || (Array.isArray(data) && data.length === 0)
  if (empty) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-6 text-sm text-muted-foreground">{emptyLabel ?? t('dataState.noDataDefault')}</CardContent>
      </Card>
    )
  }

  if (children) return <>{children(data)}</>

  return (
    <Card>
      <CardContent className="py-4">
        <pre className="overflow-x-auto text-xs text-muted-foreground">{JSON.stringify(data, null, 2)}</pre>
      </CardContent>
    </Card>
  )
}
