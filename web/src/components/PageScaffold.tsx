import type { ReactNode } from 'react'

/** Shared page shell: title + description. Access control is the real API's
 * 403 (see ForbiddenCard/DataState) — every route stays reachable. */
export function PageScaffold({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      </div>
      {children}
    </div>
  )
}
